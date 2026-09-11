package provider

import (
	"context"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/diag"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/mapplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ resource.Resource                = (*volumeResource)(nil)
	_ resource.ResourceWithConfigure   = (*volumeResource)(nil)
	_ resource.ResourceWithImportState = (*volumeResource)(nil)
)

func NewVolumeResource() resource.Resource { return &volumeResource{} }

// volumeTimeout bounds how long a create waits for the worker to make the disk.
const volumeTimeout = 10 * time.Minute

type volumeResource struct {
	client *client.Client
}

type volumeResourceModel struct {
	ID            types.String `tfsdk:"id"`
	SizeGiB       types.Int64  `tfsdk:"size_gib"`
	Tags          types.Map    `tfsdk:"tags"`
	ClientToken   types.String `tfsdk:"client_token"`
	State         types.String `tfsdk:"state"`
	Serial        types.String `tfsdk:"serial"`
	OwnerUsername types.String `tfsdk:"owner_username"`
}

func (r *volumeResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_volume"
}

func (r *volumeResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "An extra disk. Mirrors `aws_ebs_volume`: it can be attached, detached and grown, " +
			"but never shrunk. The guest sees it at `/dev/disk/by-id/virtio-<serial>` once attached.",
		Attributes: map[string]schema.Attribute{
			"id": schema.StringAttribute{
				Computed:      true,
				Description:   "The volume ID (`vol-...`).",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"size_gib": schema.Int64Attribute{Required: true, Description: "Size in GiB. It can grow but never shrink."},
			"tags": schema.MapAttribute{
				ElementType:   types.StringType,
				Optional:      true,
				Description:   "Tags. `Name` is a readable label. There is no tag update API, so changing them replaces the volume.",
				PlanModifiers: []planmodifier.Map{mapplanmodifier.RequiresReplace()},
			},
			"client_token": schema.StringAttribute{
				Optional:      true,
				Description:   "Idempotency token.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"state":          schema.StringAttribute{Computed: true, Description: "creating, available, in-use, deleting, deleted or error."},
			"serial":         schema.StringAttribute{Computed: true, Description: "The serial the guest sees."},
			"owner_username": schema.StringAttribute{Computed: true, Description: "The owning account's username."},
		},
	}
}

func (r *volumeResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func (r *volumeResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan volumeResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	tags, diags := stringMapValues(ctx, plan.Tags)
	resp.Diagnostics.Append(diags...)
	volume, err := r.client.CreateVolume(ctx, client.CreateVolumeRequest{
		SizeGiB: int(plan.SizeGiB.ValueInt64()), ClientToken: plan.ClientToken.ValueString(), Tags: tags,
	})
	if err != nil {
		addError(&resp.Diagnostics, "create the volume", err)
		return
	}
	plan.ID = types.StringValue(volume.VolumeID)
	if _, err := waitVolumeState(ctx, r.client, volume.VolumeID, volumeTimeout, "available", "in-use", "error"); err != nil {
		addError(&resp.Diagnostics, "wait for the volume", err)
		return
	}
	r.refresh(ctx, &plan, &resp.Diagnostics)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *volumeResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state volumeResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	volume, err := r.client.DescribeVolume(ctx, state.ID.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the volume", err)
		return
	}
	r.fill(ctx, &state, volume, &resp.Diagnostics)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *volumeResource) Update(ctx context.Context, req resource.UpdateRequest, resp *resource.UpdateResponse) {
	var plan, state volumeResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if !plan.SizeGiB.Equal(state.SizeGiB) {
		if _, err := r.client.ModifyVolume(ctx, plan.ID.ValueString(), int(plan.SizeGiB.ValueInt64())); err != nil {
			addError(&resp.Diagnostics, "grow the volume", err)
			return
		}
	}
	r.refresh(ctx, &plan, &resp.Diagnostics)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *volumeResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state volumeResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if _, err := r.client.DeleteVolume(ctx, state.ID.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "delete the volume", err)
	}
}

func (r *volumeResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("id"), req, resp)
}

func (r *volumeResource) refresh(ctx context.Context, model *volumeResourceModel, diags *diag.Diagnostics) {
	volume, err := r.client.DescribeVolume(ctx, model.ID.ValueString())
	if err != nil {
		addError(diags, "read the volume back", err)
		return
	}
	r.fill(ctx, model, volume, diags)
}

func (r *volumeResource) fill(ctx context.Context, model *volumeResourceModel, volume client.Volume, diags *diag.Diagnostics) {
	model.ID = types.StringValue(volume.VolumeID)
	model.SizeGiB = types.Int64Value(int64(volume.SizeGiB))
	model.State = types.StringValue(volume.State)
	model.Serial = types.StringValue(volume.Serial)
	model.OwnerUsername = types.StringValue(volume.OwnerUsername)
	tags, tagDiags := stringMap(ctx, volume.Tags)
	diags.Append(tagDiags...)
	model.Tags = tags
}
