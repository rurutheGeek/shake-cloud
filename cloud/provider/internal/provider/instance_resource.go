package provider

import (
	"context"
	"errors"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/diag"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/boolplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/int64planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/mapplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/setplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ resource.Resource                = (*instanceResource)(nil)
	_ resource.ResourceWithConfigure   = (*instanceResource)(nil)
	_ resource.ResourceWithImportState = (*instanceResource)(nil)
)

// instanceTimeout bounds how long Create and Delete wait for the worker.
const instanceTimeout = 15 * time.Minute

func NewInstanceResource() resource.Resource { return &instanceResource{} }

type instanceResource struct {
	client *client.Client
}

type instanceResourceModel struct {
	ID               types.String `tfsdk:"id"`
	ImageID          types.String `tfsdk:"image_id"`
	InstanceType     types.String `tfsdk:"instance_type"`
	VCPUs            types.Int64  `tfsdk:"vcpus"`
	MemoryMiB        types.Int64  `tfsdk:"memory_mib"`
	MemoryMinMiB     types.Int64  `tfsdk:"memory_min_mib"`
	Ballooning       types.Bool   `tfsdk:"ballooning"`
	RootDiskGiB      types.Int64  `tfsdk:"root_disk_gib"`
	KeyName          types.String `tfsdk:"key_name"`
	SecurityGroupIDs types.Set    `tfsdk:"security_group_ids"`
	UserData         types.String `tfsdk:"user_data"`
	Tags             types.Map    `tfsdk:"tags"`
	ClientToken      types.String `tfsdk:"client_token"`

	PrivateIPAddress   types.String `tfsdk:"private_ip_address"`
	MACAddress         types.String `tfsdk:"mac_address"`
	State              types.String `tfsdk:"state"`
	FirewallState      types.String `tfsdk:"firewall_state"`
	Adopted            types.Bool   `tfsdk:"adopted"`
	OwnerUsername      types.String `tfsdk:"owner_username"`
	AccountID          types.String `tfsdk:"account_id"`
	LaunchTime         types.String `tfsdk:"launch_time"`
	TerminatedAt       types.String `tfsdk:"terminated_at"`
	SecurityGroupNames types.Set    `tfsdk:"security_group_names"`
}

func (r *instanceResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_instance"
}

func (r *instanceResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "A VM in the cloud. Mirrors `aws_instance`: `image_id` and `instance_type` are the " +
			"equivalents of an AMI and an instance type, and `user_data`, `key_name` and `security_group_ids` work " +
			"the same way. Size is free-form; `instance_type` only fills in the values you leave out.",
		Attributes: map[string]schema.Attribute{
			"id": schema.StringAttribute{
				Computed:      true,
				Description:   "The instance ID (`i-...`).",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"image_id": schema.StringAttribute{
				Required:      true,
				Description:   "The image to launch from (`img-...`). Changing it replaces the instance.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"instance_type": schema.StringAttribute{
				Optional:      true,
				Description:   "A size preset from the deployment. A starting point for the explicit fields.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"vcpus": schema.Int64Attribute{
				Optional:      true,
				Computed:      true,
				Description:   "vCPU count.",
				PlanModifiers: []planmodifier.Int64{int64planmodifier.UseStateForUnknown()},
			},
			"memory_mib": schema.Int64Attribute{
				Optional:      true,
				Computed:      true,
				Description:   "Memory ceiling in MiB.",
				PlanModifiers: []planmodifier.Int64{int64planmodifier.UseStateForUnknown()},
			},
			"memory_min_mib": schema.Int64Attribute{
				Optional:      true,
				Computed:      true,
				Description:   "Balloon floor in MiB; 0 when ballooning is off.",
				PlanModifiers: []planmodifier.Int64{int64planmodifier.UseStateForUnknown()},
			},
			"ballooning": schema.BoolAttribute{
				Optional:      true,
				Computed:      true,
				Description:   "Whether the memory balloon driver is enabled.",
				PlanModifiers: []planmodifier.Bool{boolplanmodifier.UseStateForUnknown()},
			},
			"root_disk_gib": schema.Int64Attribute{
				Optional:      true,
				Computed:      true,
				Description:   "Root disk in GiB. It can grow but never shrink.",
				PlanModifiers: []planmodifier.Int64{int64planmodifier.UseStateForUnknown()},
			},
			"key_name": schema.StringAttribute{
				Optional:      true,
				Description:   "An SSH key pair whose public key is written into the instance at launch.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"security_group_ids": schema.SetAttribute{
				ElementType:   types.StringType,
				Optional:      true,
				Computed:      true,
				Description:   "Security groups to attach. Omitted means the account's default group.",
				PlanModifiers: []planmodifier.Set{setplanmodifier.UseStateForUnknown()},
			},
			"user_data": schema.StringAttribute{
				Optional:      true,
				Description:   "cloud-init user data, readable from inside the guest, so not a place for secrets.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"tags": schema.MapAttribute{
				ElementType:   types.StringType,
				Optional:      true,
				Description:   "Tags. `Name` is the guest hostname. There is no tag update API, so changing them replaces the instance.",
				PlanModifiers: []planmodifier.Map{mapplanmodifier.RequiresReplace()},
			},
			"client_token": schema.StringAttribute{
				Optional:      true,
				Description:   "Idempotency token; a retry with the same one returns the same instance.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"private_ip_address": schema.StringAttribute{Computed: true, Description: "The address the cloud allocated."},
			"mac_address":        schema.StringAttribute{Computed: true, Description: "The NIC's MAC address."},
			"state": schema.StringAttribute{
				Computed:      true,
				Description:   "pending, running, stopping, stopped, shutting-down or terminated.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"firewall_state": schema.StringAttribute{Computed: true, Description: "in-sync or applying."},
			"adopted":        schema.BoolAttribute{Computed: true, Description: "True for a VM registered into the cloud rather than launched by it."},
			"owner_username": schema.StringAttribute{Computed: true, Description: "The owning account's username."},
			"account_id":     schema.StringAttribute{Computed: true, Description: "The owning account's id."},
			"launch_time":    schema.StringAttribute{Computed: true, Description: "RFC3339 time the instance was recorded."},
			"terminated_at":  schema.StringAttribute{Computed: true, Description: "RFC3339 time the instance was terminated, if it was."},
			"security_group_names": schema.SetAttribute{
				ElementType: types.StringType,
				Computed:    true,
				Description: "Names of the attached security groups, for readable plans.",
			},
		},
	}
}

func (r *instanceResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func (r *instanceResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan instanceResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}

	tags, diags := stringMapValues(ctx, plan.Tags)
	resp.Diagnostics.Append(diags...)
	groups, diags := stringSetValues(ctx, plan.SecurityGroupIDs)
	resp.Diagnostics.Append(diags...)
	if resp.Diagnostics.HasError() {
		return
	}

	request := client.RunRequest{
		ImageID:          plan.ImageID.ValueString(),
		InstanceType:     plan.InstanceType.ValueString(),
		KeyName:          plan.KeyName.ValueString(),
		VCPUs:            optionalInt(plan.VCPUs),
		MemoryMiB:        optionalInt(plan.MemoryMiB),
		MemoryMinMiB:     optionalInt(plan.MemoryMinMiB),
		Ballooning:       optionalBool(plan.Ballooning),
		RootDiskGiB:      int(plan.RootDiskGiB.ValueInt64()),
		UserData:         plan.UserData.ValueString(),
		ClientToken:      plan.ClientToken.ValueString(),
		Tags:             tags,
		SecurityGroupIDs: groups,
	}

	instance, err := r.client.RunInstances(ctx, request)
	if err != nil {
		addError(&resp.Diagnostics, "launch the instance", err)
		return
	}
	if _, err := r.client.WaitInstance(ctx, instance.InstanceID, instanceTimeout, "running", "terminated"); err != nil {
		resp.Diagnostics.AddError("shake-cloud: the instance did not settle",
			err.Error()+"\nThe instance exists (id "+instance.InstanceID+"); use `terraform import` if the state is out of step.")
		return
	}
	plan.ID = types.StringValue(instance.InstanceID)
	r.refresh(ctx, &plan, &resp.Diagnostics)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *instanceResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state instanceResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	instance, err := r.client.DescribeInstance(ctx, state.ID.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the instance", err)
		return
	}
	r.fill(ctx, &state, instance, &resp.Diagnostics)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *instanceResource) Update(ctx context.Context, req resource.UpdateRequest, resp *resource.UpdateResponse) {
	var plan, state instanceResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}

	// Size, via the admin resize endpoint. The API refuses cpu and memory
	// changes while the instance is running, and says so.
	modify := client.ModifyInstanceRequest{
		VCPUs:        changedInt(plan.VCPUs, state.VCPUs),
		MemoryMiB:    changedInt(plan.MemoryMiB, state.MemoryMiB),
		MemoryMinMiB: changedInt(plan.MemoryMinMiB, state.MemoryMinMiB),
		Ballooning:   changedBool(plan.Ballooning, state.Ballooning),
		RootDiskGiB:  changedInt(plan.RootDiskGiB, state.RootDiskGiB),
	}
	if modify.VCPUs != nil || modify.MemoryMiB != nil || modify.MemoryMinMiB != nil || modify.Ballooning != nil || modify.RootDiskGiB != nil {
		if _, err := r.client.ModifyInstance(ctx, plan.ID.ValueString(), modify); err != nil {
			addError(&resp.Diagnostics, "resize the instance", err)
			return
		}
	}

	// Security groups, which the API replaces wholesale.
	if !plan.SecurityGroupIDs.Equal(state.SecurityGroupIDs) {
		groups, diags := stringSetValues(ctx, plan.SecurityGroupIDs)
		resp.Diagnostics.Append(diags...)
		if resp.Diagnostics.HasError() {
			return
		}
		if len(groups) == 0 {
			resp.Diagnostics.AddError("shake-cloud: security_group_ids is empty",
				"an instance must keep at least one security group; the default group is the unfiltered one")
			return
		}
		if _, err := r.client.SetInstanceSecurityGroups(ctx, plan.ID.ValueString(), groups); err != nil {
			addError(&resp.Diagnostics, "change the instance's security groups", err)
			return
		}
	}

	r.refresh(ctx, &plan, &resp.Diagnostics)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *instanceResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state instanceResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	instance, err := r.client.TerminateInstance(ctx, state.ID.ValueString())
	if isNotFound(err) {
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "terminate the instance", err)
		return
	}
	if _, err := r.client.WaitInstance(ctx, instance.InstanceID, instanceTimeout, "terminated"); err != nil {
		addError(&resp.Diagnostics, "wait for the instance to terminate", err)
	}
}

func (r *instanceResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("id"), req, resp)
}

// refresh re-reads an instance into the plan after a create or update.
func (r *instanceResource) refresh(ctx context.Context, model *instanceResourceModel, diags *diag.Diagnostics) {
	instance, err := r.client.DescribeInstance(ctx, model.ID.ValueString())
	if err != nil {
		addError(diags, "read the instance back", err)
		return
	}
	r.fill(ctx, model, instance, diags)
}

// fill copies an API instance into the Terraform model. Configurable fields are
// only filled when the plan left them unset, so a null that means "let the API
// decide" stays consistent with what the API decided.
func (r *instanceResource) fill(ctx context.Context, model *instanceResourceModel, instance client.Instance, diags *diag.Diagnostics) {
	model.ID = types.StringValue(instance.InstanceID)
	model.PrivateIPAddress = types.StringValue(instance.PrivateIPAddress)
	model.MACAddress = types.StringValue(instance.MACAddress)
	model.State = types.StringValue(instance.State)
	model.FirewallState = types.StringValue(instance.FirewallState)
	model.Adopted = types.BoolValue(instance.Adopted)
	model.OwnerUsername = types.StringValue(instance.OwnerUsername)
	model.AccountID = types.StringValue(instance.AccountID)
	model.LaunchTime = types.StringValue(instance.LaunchTime.Format(time.RFC3339))
	if instance.TerminatedAt != nil {
		model.TerminatedAt = types.StringValue(instance.TerminatedAt.Format(time.RFC3339))
	} else {
		model.TerminatedAt = types.StringNull()
	}
	model.VCPUs = types.Int64Value(int64(instance.VCPUs))
	model.MemoryMiB = types.Int64Value(int64(instance.MemoryMiB))
	model.MemoryMinMiB = types.Int64Value(int64(instance.MemoryMinMiB))
	model.Ballooning = types.BoolValue(instance.Ballooning)
	model.RootDiskGiB = types.Int64Value(int64(instance.RootDiskGiB))
	if instance.InstanceType != "" {
		model.InstanceType = types.StringValue(instance.InstanceType)
	}
	model.KeyName = stringOrNull(instance.KeyName)
	// user_data is not returned by the API (it is readable from the guest), so
	// it stays whatever the configuration had.

	groupIDs := make([]string, 0, len(instance.SecurityGroups))
	names := make([]string, 0, len(instance.SecurityGroups))
	for _, group := range instance.SecurityGroups {
		groupIDs = append(groupIDs, group.GroupID)
		names = append(names, group.GroupName)
	}
	ids, idDiags := stringSet(ctx, groupIDs)
	diags.Append(idDiags...)
	model.SecurityGroupIDs = ids
	nameSet, nameDiags := stringSet(ctx, names)
	diags.Append(nameDiags...)
	model.SecurityGroupNames = nameSet

	tags, tagDiags := stringMap(ctx, instance.Tags)
	diags.Append(tagDiags...)
	model.Tags = tags
}

func isNotFound(err error) bool {
	var apiError *client.APIError
	return errors.As(err, &apiError) && apiError.NotFound()
}

func optionalBool(value types.Bool) *bool {
	if value.IsNull() || value.IsUnknown() {
		return nil
	}
	result := value.ValueBool()
	return &result
}

func changedInt(plan, state types.Int64) *int {
	if plan.Equal(state) || plan.IsNull() || plan.IsUnknown() {
		return nil
	}
	number := int(plan.ValueInt64())
	return &number
}

func changedBool(plan, state types.Bool) *bool {
	if plan.Equal(state) || plan.IsNull() || plan.IsUnknown() {
		return nil
	}
	result := plan.ValueBool()
	return &result
}

func stringOrNull(value string) types.String {
	if value == "" {
		return types.StringNull()
	}
	return types.StringValue(value)
}
