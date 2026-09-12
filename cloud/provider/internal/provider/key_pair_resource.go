package provider

import (
	"context"
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
	_ resource.Resource                = (*keyPairResource)(nil)
	_ resource.ResourceWithConfigure   = (*keyPairResource)(nil)
	_ resource.ResourceWithImportState = (*keyPairResource)(nil)
)

func NewKeyPairResource() resource.Resource { return &keyPairResource{} }

type keyPairResource struct {
	client *client.Client
}

type keyPairResourceModel struct {
	KeyName     types.String `tfsdk:"key_name"`
	PublicKey   types.String `tfsdk:"public_key"`
	Fingerprint types.String `tfsdk:"fingerprint"`
	CreatedAt   types.String `tfsdk:"created_at"`
}

func (r *keyPairResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_key_pair"
}

func (r *keyPairResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "An SSH key pair. Mirrors `aws_key_pair`: only the public key is sent, and it is " +
			"written into instances that name it at launch.",
		Attributes: map[string]schema.Attribute{
			"key_name": schema.StringAttribute{
				Required:      true,
				Description:   "The key pair name.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"public_key": schema.StringAttribute{
				Required:      true,
				Description:   "The OpenSSH public key, as in `~/.ssh/id_ed25519.pub`.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"fingerprint": schema.StringAttribute{Computed: true, Description: "The `ssh-keygen -lf` fingerprint."},
			"created_at":  schema.StringAttribute{Computed: true, Description: "RFC3339 creation time."},
		},
	}
}

func (r *keyPairResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func (r *keyPairResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan keyPairResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	key, err := r.client.ImportKeyPair(ctx, plan.KeyName.ValueString(), plan.PublicKey.ValueString())
	if err != nil {
		addError(&resp.Diagnostics, "import the key pair", err)
		return
	}
	fillKeyPair(&plan, key)
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *keyPairResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state keyPairResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	keys, err := r.client.DescribeKeyPairs(ctx)
	if err != nil {
		addError(&resp.Diagnostics, "read the key pairs", err)
		return
	}
	for _, key := range keys {
		if key.KeyName == state.KeyName.ValueString() {
			fillKeyPair(&state, key)
			resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
			return
		}
	}
	resp.State.RemoveResource(ctx)
}

func (r *keyPairResource) Update(_ context.Context, _ resource.UpdateRequest, _ *resource.UpdateResponse) {
	// Every attribute forces replacement, so Update is never called.
}

func (r *keyPairResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state keyPairResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if err := r.client.DeleteKeyPair(ctx, state.KeyName.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "delete the key pair", err)
	}
}

func (r *keyPairResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("key_name"), req, resp)
}

func fillKeyPair(model *keyPairResourceModel, key client.KeyPair) {
	model.KeyName = types.StringValue(key.KeyName)
	model.Fingerprint = types.StringValue(key.Fingerprint)
	model.CreatedAt = types.StringValue(key.CreatedAt.Format(time.RFC3339))
}
