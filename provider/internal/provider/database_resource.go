package provider

import (
	"context"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/int64planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ resource.Resource                = (*databaseResource)(nil)
	_ resource.ResourceWithConfigure   = (*databaseResource)(nil)
	_ resource.ResourceWithImportState = (*databaseResource)(nil)
)

func NewDatabaseResource() resource.Resource { return &databaseResource{} }

type databaseResource struct {
	client *client.Client
}

type databaseResourceModel struct {
	DatabaseID     types.String `tfsdk:"database_id"`
	Name           types.String `tfsdk:"name"`
	StorageGiB     types.Int64  `tfsdk:"storage_gib"`
	Engine         types.String `tfsdk:"engine"`
	EngineVersion  types.String `tfsdk:"engine_version"`
	Status         types.String `tfsdk:"status"`
	Instances      types.Int64  `tfsdk:"instances"`
	ReadyInstances types.Int64  `tfsdk:"ready_instances"`
	Host           types.String `tfsdk:"host"`
	Port           types.Int64  `tfsdk:"port"`
	AccountID      types.String `tfsdk:"account_id"`
	OwnerUsername  types.String `tfsdk:"owner_username"`
	CreatedAt      types.String `tfsdk:"created_at"`
}

func (r *databaseResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_database"
}

func (r *databaseResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "A PostgreSQL database appliance backed by CloudNativePG, mirroring `aws_db_instance`. " +
			"Creating one makes a Cluster in the Kubernetes cluster; the database's traffic never passes through " +
			"the cloud API.\n\n" +
			"Connection credentials are **not** managed here: they live in a Kubernetes Secret and leak nothing to " +
			"Terraform state. Read them from the portal or `shakecloud database credentials`.",
		Attributes: map[string]schema.Attribute{
			"database_id": schema.StringAttribute{
				Computed:      true,
				Description:   "The database id (`db-...`), also the CloudNativePG cluster name.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"name": schema.StringAttribute{
				Required:      true,
				Description:   "2-30 characters of lower case letters, digits and hyphens, starting with a letter.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"storage_gib": schema.Int64Attribute{
				Required:      true,
				Description:   "Disk size in GiB (1-50).",
				PlanModifiers: []planmodifier.Int64{int64planmodifier.RequiresReplace()},
			},
			"engine":          schema.StringAttribute{Computed: true, Description: "The engine, always `postgres`."},
			"engine_version":  schema.StringAttribute{Computed: true, Description: "The PostgreSQL major version."},
			"status":          schema.StringAttribute{Computed: true, Description: "The CloudNativePG phase, e.g. `Cluster in healthy state`."},
			"instances":       schema.Int64Attribute{Computed: true, Description: "Instances in the cluster."},
			"ready_instances": schema.Int64Attribute{Computed: true, Description: "Instances that are ready."},
			"host":            schema.StringAttribute{Computed: true, Description: "The read-write service host."},
			"port":            schema.Int64Attribute{Computed: true, Description: "The PostgreSQL port."},
			"account_id":      schema.StringAttribute{Computed: true, Description: "The owning account's id."},
			"owner_username":  schema.StringAttribute{Computed: true, Description: "The owning account's username."},
			"created_at":      schema.StringAttribute{Computed: true, Description: "RFC3339 creation time."},
		},
	}
}

func (r *databaseResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func (r *databaseResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan databaseResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	database, err := r.client.CreateDatabase(ctx, plan.Name.ValueString(), int(plan.StorageGiB.ValueInt64()))
	if err != nil {
		addError(&resp.Diagnostics, "create the database", err)
		return
	}
	r.fill(&plan, database)
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *databaseResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state databaseResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	database, err := r.client.DescribeDatabase(ctx, state.DatabaseID.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the database", err)
		return
	}
	r.fill(&state, database)
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *databaseResource) Update(_ context.Context, _ resource.UpdateRequest, _ *resource.UpdateResponse) {
	// Every attribute forces replacement, so Update is never called.
}

func (r *databaseResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state databaseResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if err := r.client.DeleteDatabase(ctx, state.DatabaseID.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "delete the database", err)
	}
}

func (r *databaseResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("database_id"), req, resp)
}

func (r *databaseResource) fill(model *databaseResourceModel, database client.Database) {
	model.DatabaseID = types.StringValue(database.DatabaseID)
	model.Name = types.StringValue(database.Name)
	model.StorageGiB = types.Int64Value(int64(database.StorageGiB))
	model.Engine = types.StringValue(database.Engine)
	model.EngineVersion = types.StringValue(database.EngineVersion)
	model.Status = types.StringValue(database.Status)
	model.Instances = types.Int64Value(int64(database.Instances))
	model.ReadyInstances = types.Int64Value(int64(database.ReadyInstances))
	model.Host = types.StringValue(database.Host)
	model.Port = types.Int64Value(int64(database.Port))
	model.AccountID = types.StringValue(database.AccountID)
	model.OwnerUsername = types.StringValue(database.OwnerUsername)
	model.CreatedAt = types.StringValue(database.CreatedAt.Format(time.RFC3339))
}
