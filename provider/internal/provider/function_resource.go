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
	_ resource.Resource                = (*functionResource)(nil)
	_ resource.ResourceWithConfigure   = (*functionResource)(nil)
	_ resource.ResourceWithImportState = (*functionResource)(nil)
)

func NewFunctionResource() resource.Resource { return &functionResource{} }

type functionResource struct {
	client *client.Client
}

type functionResourceModel struct {
	FunctionID    types.String `tfsdk:"function_id"`
	Name          types.String `tfsdk:"name"`
	Image         types.String `tfsdk:"image"`
	Status        types.String `tfsdk:"status"`
	URL           types.String `tfsdk:"url"`
	AccountID     types.String `tfsdk:"account_id"`
	OwnerUsername types.String `tfsdk:"owner_username"`
	CreatedAt     types.String `tfsdk:"created_at"`
}

func (r *functionResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_function"
}

func (r *functionResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "A serverless HTTP function backed by Knative, in the spirit of `aws_lambda_function`. " +
			"Creating one makes a Knative Service in the Kubernetes cluster; the function's traffic never passes " +
			"through the cloud API.",
		Attributes: map[string]schema.Attribute{
			"function_id": schema.StringAttribute{
				Computed:      true,
				Description:   "The function id (`fn-...`), also the Knative Service name.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"name": schema.StringAttribute{
				Required:      true,
				Description:   "2-30 characters of lower case letters, digits and hyphens, starting with a letter.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"image": schema.StringAttribute{
				Required:      true,
				Description:   "The container image to run.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"status":         schema.StringAttribute{Computed: true, Description: "`Provisioning` until the Knative Service is Ready, then `Ready`."},
			"url":            schema.StringAttribute{Computed: true, Description: "The function URL once Knative assigns it."},
			"account_id":     schema.StringAttribute{Computed: true, Description: "The owning account's id."},
			"owner_username": schema.StringAttribute{Computed: true, Description: "The owning account's username."},
			"created_at":     schema.StringAttribute{Computed: true, Description: "RFC3339 creation time."},
		},
	}
}

func (r *functionResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func (r *functionResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan functionResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	function, err := r.client.CreateFunction(ctx, plan.Name.ValueString(), plan.Image.ValueString())
	if err != nil {
		addError(&resp.Diagnostics, "create the function", err)
		return
	}
	r.fill(&plan, function)
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *functionResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state functionResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	function, err := r.client.DescribeFunction(ctx, state.FunctionID.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the function", err)
		return
	}
	r.fill(&state, function)
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *functionResource) Update(_ context.Context, _ resource.UpdateRequest, _ *resource.UpdateResponse) {
	// Every attribute forces replacement, so Update is never called.
}

func (r *functionResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state functionResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if err := r.client.DeleteFunction(ctx, state.FunctionID.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "delete the function", err)
	}
}

func (r *functionResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("function_id"), req, resp)
}

func (r *functionResource) fill(model *functionResourceModel, function client.Function) {
	model.FunctionID = types.StringValue(function.FunctionID)
	model.Name = types.StringValue(function.Name)
	model.Image = types.StringValue(function.Image)
	model.Status = types.StringValue(function.Status)
	model.URL = types.StringValue(function.URL)
	model.AccountID = types.StringValue(function.AccountID)
	model.OwnerUsername = types.StringValue(function.OwnerUsername)
	model.CreatedAt = types.StringValue(function.CreatedAt.Format(time.RFC3339))
}
