package provider

import (
	"context"
	"os"
	"path/filepath"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ resource.Resource                = (*imageResource)(nil)
	_ resource.ResourceWithConfigure   = (*imageResource)(nil)
	_ resource.ResourceWithImportState = (*imageResource)(nil)
)

func NewImageResource() resource.Resource { return &imageResource{} }

type imageResource struct {
	client *client.Client
}

type imageResourceModel struct {
	ID            types.String `tfsdk:"id"`
	Name          types.String `tfsdk:"name"`
	File          types.String `tfsdk:"file"`
	Format        types.String `tfsdk:"format"`
	SizeMiB       types.Int64  `tfsdk:"size_mib"`
	Public        types.Bool   `tfsdk:"public"`
	AccountID     types.String `tfsdk:"account_id"`
	OwnerUsername types.String `tfsdk:"owner_username"`
	State         types.String `tfsdk:"state"`
	CreatedAt     types.String `tfsdk:"created_at"`
}

func (r *imageResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_image"
}

func (r *imageResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "A boot disk image uploaded from a local file. The file is streamed to the API at " +
			"create time; only the returned image ID is kept. Shared images declared in Terraform are read-only " +
			"and cannot be managed by this resource.",
		Attributes: map[string]schema.Attribute{
			"id": schema.StringAttribute{
				Computed:      true,
				Description:   "The image ID (`img-...`).",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"name": schema.StringAttribute{
				Required:      true,
				Description:   "The image name shown to users.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"file": schema.StringAttribute{
				Required: true,
				Description: "Local path to the disk image. `.qcow2`, `.raw`, `.img` and `.vmdk` are accepted. " +
					"Changing the path replaces the image.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"format":         schema.StringAttribute{Computed: true, Description: "The format read back from the uploaded disk."},
			"size_mib":       schema.Int64Attribute{Computed: true, Description: "The uploaded size in MiB."},
			"public":         schema.BoolAttribute{Computed: true, Description: "Whether every account can launch from it."},
			"account_id":     schema.StringAttribute{Computed: true, Description: "The owning account."},
			"owner_username": schema.StringAttribute{Computed: true, Description: "The owning account's username."},
			"state":          schema.StringAttribute{Computed: true, Description: "always `available` for an uploaded image."},
			"created_at":     schema.StringAttribute{Computed: true, Description: "RFC3339 creation time."},
		},
	}
}

func (r *imageResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
	if req.ProviderData == nil {
		return
	}
	c, err := clientFrom(req.ProviderData)
	if err != nil {
		resp.Diagnostics.AddError("shake-cloud: provider not configured", err.Error())
		return
	}
	r.client = c
}

func (r *imageResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan imageResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	file, err := os.Open(plan.File.ValueString())
	if err != nil {
		resp.Diagnostics.AddError("shake-cloud: cannot open the image file", err.Error())
		return
	}
	defer file.Close()
	image, err := r.client.ImportImage(ctx, plan.Name.ValueString(), filepath.Base(plan.File.ValueString()), file)
	if err != nil {
		addError(&resp.Diagnostics, "upload the image", err)
		return
	}
	fillImage(&plan, image)
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *imageResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state imageResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	images, err := r.client.DescribeImages(ctx)
	if err != nil {
		addError(&resp.Diagnostics, "read the images", err)
		return
	}
	for _, image := range images {
		if image.ImageID == state.ID.ValueString() {
			fillImage(&state, image)
			resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
			return
		}
	}
	resp.State.RemoveResource(ctx)
}

func (r *imageResource) Update(_ context.Context, _ resource.UpdateRequest, _ *resource.UpdateResponse) {
	// Every attribute forces replacement, so Update is never called.
}

func (r *imageResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state imageResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if _, err := r.client.DeleteImage(ctx, state.ID.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "delete the image", err)
	}
}

func (r *imageResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("id"), req, resp)
}

func fillImage(model *imageResourceModel, image client.Image) {
	model.ID = types.StringValue(image.ImageID)
	model.Name = types.StringValue(image.Name)
	model.Format = types.StringValue(image.Format)
	model.SizeMiB = types.Int64Value(int64(image.SizeMiB))
	model.Public = types.BoolValue(image.Public)
	model.AccountID = types.StringValue(image.AccountID)
	model.OwnerUsername = types.StringValue(image.OwnerUsername)
	model.State = types.StringValue(image.State)
	if image.CreatedAt.IsZero() {
		model.CreatedAt = types.StringNull()
	} else {
		model.CreatedAt = types.StringValue(image.CreatedAt.Format(time.RFC3339))
	}
}
