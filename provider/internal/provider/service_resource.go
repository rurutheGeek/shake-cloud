package provider

import (
	"context"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/int64default"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/int64planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/client"
)

var (
	_ resource.Resource                = (*serviceResource)(nil)
	_ resource.ResourceWithConfigure   = (*serviceResource)(nil)
	_ resource.ResourceWithImportState = (*serviceResource)(nil)
)

func NewServiceResource() resource.Resource { return &serviceResource{} }

type serviceResource struct {
	client *client.Client
}

type serviceResourceModel struct {
	ServiceID     types.String `tfsdk:"service_id"`
	Name          types.String `tfsdk:"name"`
	Image         types.String `tfsdk:"image"`
	Port          types.Int64  `tfsdk:"port"`
	MemoryMiB     types.Int64  `tfsdk:"memory_mib"`
	Env           types.Map    `tfsdk:"env"`
	Secrets       types.Map    `tfsdk:"secrets"`
	DiskSizeGiB   types.Int64  `tfsdk:"disk_size_gib"`
	DiskMountPath types.String `tfsdk:"disk_mount_path"`
	Status        types.String `tfsdk:"status"`
	URL           types.String `tfsdk:"url"`
	AccountID     types.String `tfsdk:"account_id"`
	OwnerUsername types.String `tfsdk:"owner_username"`
	CreatedAt     types.String `tfsdk:"created_at"`
}

func (r *serviceResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_service"
}

func (r *serviceResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	replaceInt := []planmodifier.Int64{int64planmodifier.RequiresReplace()}
	resp.Schema = schema.Schema{
		MarkdownDescription: "An always-on container, in the spirit of an ECS service: one Kubernetes Deployment " +
			"that never scales to zero, with an optional persistent disk, secrets and a LAN address. " +
			"Changing `image`, `memory_mib`, `env` or `secrets` replaces the pod; the other settings replace the service.",
		Attributes: map[string]schema.Attribute{
			"service_id": schema.StringAttribute{
				Computed:      true,
				Description:   "The service id (`svc-...`), also the Kubernetes object name.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"name": schema.StringAttribute{
				Required:      true,
				Description:   "2-30 characters of lower case letters, digits and hyphens, starting with a letter.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"image": schema.StringAttribute{Required: true, Description: "The container image to run. Pin it by digest."},
			"port": schema.Int64Attribute{
				Optional: true, Description: "The port the container listens on. Gives the service a LAN address (`url`).",
				PlanModifiers: replaceInt,
			},
			"memory_mib": schema.Int64Attribute{
				Optional: true, Computed: true, Default: int64default.StaticInt64(128),
				Description: "Memory in MiB, both requested and the limit (32-512).",
			},
			"env": schema.MapAttribute{
				Optional: true, ElementType: types.StringType, Description: "Environment variables that are not secret.",
			},
			"secrets": schema.MapAttribute{
				Optional: true, Sensitive: true, ElementType: types.StringType,
				Description: "Environment variables kept in a Kubernetes Secret. The API never returns the values, " +
					"so a change made outside Terraform is not detected.",
			},
			"disk_size_gib": schema.Int64Attribute{
				Optional: true, Description: "Size of a persistent disk (1-32 GiB). It is deleted with the service.",
				PlanModifiers: replaceInt,
			},
			"disk_mount_path": schema.StringAttribute{
				Optional: true, Description: "Where the disk is mounted, e.g. `/data`.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"status":         schema.StringAttribute{Computed: true, Description: "`Provisioning` until the pod is ready, then `Running`."},
			"url":            schema.StringAttribute{Computed: true, Description: "`http://<LAN address>:<port>` once the LoadBalancer has an address."},
			"account_id":     schema.StringAttribute{Computed: true, Description: "The owning account's id."},
			"owner_username": schema.StringAttribute{Computed: true, Description: "The owning account's username."},
			"created_at": schema.StringAttribute{
				Computed: true, Description: "RFC3339 creation time.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
		},
	}
}

func (r *serviceResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func serviceMap(ctx context.Context, m types.Map) (map[string]string, bool) {
	if m.IsNull() || m.IsUnknown() {
		return nil, false
	}
	out := map[string]string{}
	m.ElementsAs(ctx, &out, false)
	return out, true
}

func (r *serviceResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan serviceResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	env, _ := serviceMap(ctx, plan.Env)
	secrets, _ := serviceMap(ctx, plan.Secrets)
	input := client.CreateServiceInput{
		Name: plan.Name.ValueString(), Image: plan.Image.ValueString(), Port: int(plan.Port.ValueInt64()),
		MemoryMiB: int(plan.MemoryMiB.ValueInt64()), Env: env, Secrets: secrets,
	}
	if plan.DiskSizeGiB.ValueInt64() > 0 {
		input.Disk = &client.ServiceDisk{SizeGiB: int(plan.DiskSizeGiB.ValueInt64()), MountPath: plan.DiskMountPath.ValueString()}
	}
	service, err := r.client.CreateService(ctx, input)
	if err != nil {
		addError(&resp.Diagnostics, "create the service", err)
		return
	}
	r.fill(&plan, service)
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *serviceResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state serviceResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	service, err := r.client.DescribeService(ctx, state.ServiceID.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the service", err)
		return
	}
	r.fill(&state, service)
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *serviceResource) Update(ctx context.Context, req resource.UpdateRequest, resp *resource.UpdateResponse) {
	var plan, state serviceResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	image := plan.Image.ValueString()
	memory := int(plan.MemoryMiB.ValueInt64())
	input := client.ModifyServiceInput{Image: &image, MemoryMiB: &memory}
	env, ok := serviceMap(ctx, plan.Env)
	if !ok {
		env = map[string]string{}
	}
	input.Env = &env
	secrets, ok := serviceMap(ctx, plan.Secrets)
	if !ok {
		secrets = map[string]string{}
	}
	input.Secrets = &secrets
	service, err := r.client.ModifyService(ctx, state.ServiceID.ValueString(), input)
	if err != nil {
		addError(&resp.Diagnostics, "update the service", err)
		return
	}
	r.fill(&plan, service)
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *serviceResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state serviceResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if err := r.client.DeleteService(ctx, state.ServiceID.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "delete the service", err)
	}
}

func (r *serviceResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("service_id"), req, resp)
}

// fill copies what the API returns. Secrets keep the configured values: the
// API returns only their names.
func (r *serviceResource) fill(model *serviceResourceModel, service client.Service) {
	model.ServiceID = types.StringValue(service.ServiceID)
	model.Name = types.StringValue(service.Name)
	model.Image = types.StringValue(service.Image)
	model.MemoryMiB = types.Int64Value(int64(service.MemoryMiB))
	if service.Port > 0 {
		model.Port = types.Int64Value(int64(service.Port))
	} else {
		model.Port = types.Int64Null()
	}
	if len(service.Env) > 0 {
		env, _ := types.MapValueFrom(context.Background(), types.StringType, service.Env)
		model.Env = env
	} else if !model.Env.IsNull() {
		// Keep an empty map written in the configuration as it is.
		model.Env, _ = types.MapValueFrom(context.Background(), types.StringType, map[string]string{})
	}
	if service.Disk != nil {
		model.DiskSizeGiB = types.Int64Value(int64(service.Disk.SizeGiB))
		model.DiskMountPath = types.StringValue(service.Disk.MountPath)
	} else {
		model.DiskSizeGiB = types.Int64Null()
		model.DiskMountPath = types.StringNull()
	}
	model.Status = types.StringValue(service.Status)
	model.URL = types.StringValue(service.URL)
	model.AccountID = types.StringValue(service.AccountID)
	model.OwnerUsername = types.StringValue(service.OwnerUsername)
	model.CreatedAt = types.StringValue(service.CreatedAt.Format(time.RFC3339))
}
