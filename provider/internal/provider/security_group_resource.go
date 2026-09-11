package provider

import (
	"context"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/diag"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/boolplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/setplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ resource.Resource                = (*securityGroupResource)(nil)
	_ resource.ResourceWithConfigure   = (*securityGroupResource)(nil)
	_ resource.ResourceWithImportState = (*securityGroupResource)(nil)
)

func NewSecurityGroupResource() resource.Resource { return &securityGroupResource{} }

type securityGroupResource struct {
	client *client.Client
}

type securityGroupResourceModel struct {
	ID            types.String `tfsdk:"id"`
	GroupName     types.String `tfsdk:"group_name"`
	Description   types.String `tfsdk:"description"`
	OwnerUsername types.String `tfsdk:"owner_username"`
	IsDefault     types.Bool   `tfsdk:"is_default"`
	InstanceIDs   types.Set    `tfsdk:"instance_ids"`
	CreatedAt     types.String `tfsdk:"created_at"`
}

func (r *securityGroupResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_security_group"
}

func (r *securityGroupResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "A named set of firewall rules. Mirrors `aws_security_group`, but the rules are managed " +
			"by `shakecloud_security_group_rule` resources, because the API adds and revokes rules one at a time.",
		Attributes: map[string]schema.Attribute{
			"id": schema.StringAttribute{
				Computed:      true,
				Description:   "The group ID (`sg-...`).",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"group_name": schema.StringAttribute{
				Required:      true,
				Description:   "The group name. Changing it replaces the group.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"description": schema.StringAttribute{
				Optional:      true,
				Description:   "A description.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"owner_username": schema.StringAttribute{Computed: true, Description: "The owning account's username."},
			"is_default":     schema.BoolAttribute{Computed: true, Description: "True for the account's default group, which cannot be deleted.", PlanModifiers: []planmodifier.Bool{boolplanmodifier.UseStateForUnknown()}},
			"instance_ids":   schema.SetAttribute{ElementType: types.StringType, Computed: true, Description: "Instances using this group.", PlanModifiers: []planmodifier.Set{setplanmodifier.UseStateForUnknown()}},
			"created_at":     schema.StringAttribute{Computed: true, Description: "RFC3339 creation time."},
		},
	}
}

func (r *securityGroupResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func (r *securityGroupResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan securityGroupResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	group, err := r.client.CreateSecurityGroup(ctx, client.CreateSecurityGroupRequest{
		GroupName:   plan.GroupName.ValueString(),
		Description: plan.Description.ValueString(),
	})
	if err != nil {
		addError(&resp.Diagnostics, "create the security group", err)
		return
	}
	resp.Diagnostics.Append(fillSecurityGroup(ctx, &plan, group)...)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *securityGroupResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state securityGroupResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	group, err := r.client.DescribeSecurityGroup(ctx, state.ID.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the security group", err)
		return
	}
	resp.Diagnostics.Append(fillSecurityGroup(ctx, &state, group)...)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *securityGroupResource) Update(_ context.Context, _ resource.UpdateRequest, _ *resource.UpdateResponse) {
	// Every attribute forces replacement, so Update is never called.
}

func (r *securityGroupResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state securityGroupResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if err := r.client.DeleteSecurityGroup(ctx, state.ID.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "delete the security group", err)
	}
}

func (r *securityGroupResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("id"), req, resp)
}

func fillSecurityGroup(ctx context.Context, model *securityGroupResourceModel, group client.SecurityGroup) diag.Diagnostics {
	model.ID = types.StringValue(group.GroupID)
	model.GroupName = types.StringValue(group.GroupName)
	model.Description = types.StringValue(group.Description)
	model.OwnerUsername = types.StringValue(group.OwnerUsername)
	model.IsDefault = types.BoolValue(group.IsDefault)
	model.CreatedAt = types.StringValue(group.CreatedAt.Format(time.RFC3339))
	instanceIDs, diags := stringSet(ctx, group.InstanceIDs)
	model.InstanceIDs = instanceIDs
	return diags
}
