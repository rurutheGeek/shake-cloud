package provider

import (
	"context"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/diag"
	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/int64planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/setplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ resource.Resource                = (*bucketResource)(nil)
	_ resource.ResourceWithConfigure   = (*bucketResource)(nil)
	_ resource.ResourceWithImportState = (*bucketResource)(nil)
)

func NewBucketResource() resource.Resource { return &bucketResource{} }

type bucketResource struct {
	client *client.Client
}

type bucketResourceModel struct {
	BucketName    types.String `tfsdk:"bucket_name"`
	S3Endpoint    types.String `tfsdk:"s3_endpoint"`
	S3Region      types.String `tfsdk:"s3_region"`
	AccountID     types.String `tfsdk:"account_id"`
	OwnerUsername types.String `tfsdk:"owner_username"`
	Objects       types.Int64  `tfsdk:"objects"`
	Bytes         types.Int64  `tfsdk:"bytes"`
	KeyIDs        types.Set    `tfsdk:"key_ids"`
	CreatedAt     types.String `tfsdk:"created_at"`
}

func (r *bucketResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_bucket"
}

func (r *bucketResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "An S3 bucket in the cloud's Garage object store, mirroring `aws_s3_bucket`. " +
			"The bucket's name is a global alias, unique across the cloud. Objects are transferred directly " +
			"between the client and `s3_endpoint`; they never pass through the cloud API.\n\n" +
			"S3 access keys are **not** managed here: creating one returns a secret, and putting that in " +
			"Terraform state would leak it. Issue keys from the portal or the shakecloud CLI instead, then " +
			"grant them on the bucket there.",
		Attributes: map[string]schema.Attribute{
			"bucket_name": schema.StringAttribute{
				Required:      true,
				Description:   "3-63 characters of lower case letters, digits, dots and hyphens.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"s3_endpoint": schema.StringAttribute{
				Computed:    true,
				Description: "The S3 API URL to point a client at.",
			},
			"s3_region":      schema.StringAttribute{Computed: true, Description: "The S3 region to use."},
			"account_id":     schema.StringAttribute{Computed: true, Description: "The owning account's id."},
			"owner_username": schema.StringAttribute{Computed: true, Description: "The owning account's username."},
			"objects":        schema.Int64Attribute{Computed: true, Description: "Objects in the bucket, from Garage. Best effort.", PlanModifiers: []planmodifier.Int64{int64planmodifier.UseStateForUnknown()}},
			"bytes":          schema.Int64Attribute{Computed: true, Description: "Bytes stored, from Garage. Best effort.", PlanModifiers: []planmodifier.Int64{int64planmodifier.UseStateForUnknown()}},
			"key_ids":        schema.SetAttribute{ElementType: types.StringType, Computed: true, Description: "S3 key ids allowed on the bucket.", PlanModifiers: []planmodifier.Set{setplanmodifier.UseStateForUnknown()}},
			"created_at":     schema.StringAttribute{Computed: true, Description: "RFC3339 creation time."},
		},
	}
}

func (r *bucketResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func (r *bucketResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan bucketResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	bucket, err := r.client.CreateBucket(ctx, plan.BucketName.ValueString())
	if err != nil {
		addError(&resp.Diagnostics, "create the bucket", err)
		return
	}
	r.fill(ctx, &plan, bucket, &resp.Diagnostics)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *bucketResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state bucketResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	bucket, err := r.client.DescribeBucket(ctx, state.BucketName.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the bucket", err)
		return
	}
	r.fill(ctx, &state, bucket, &resp.Diagnostics)
	if resp.Diagnostics.HasError() {
		return
	}
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *bucketResource) Update(_ context.Context, _ resource.UpdateRequest, _ *resource.UpdateResponse) {
	// Every attribute forces replacement, so Update is never called.
}

func (r *bucketResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state bucketResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if err := r.client.DeleteBucket(ctx, state.BucketName.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "delete the bucket", err)
	}
}

func (r *bucketResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resource.ImportStatePassthroughID(ctx, path.Root("bucket_name"), req, resp)
}

func (r *bucketResource) fill(ctx context.Context, model *bucketResourceModel, bucket client.Bucket, diags *diag.Diagnostics) {
	model.BucketName = types.StringValue(bucket.BucketName)
	model.S3Endpoint = types.StringValue(bucket.S3Endpoint)
	model.S3Region = types.StringValue(bucket.S3Region)
	model.AccountID = types.StringValue(bucket.AccountID)
	model.OwnerUsername = types.StringValue(bucket.OwnerUsername)
	model.Objects = types.Int64Value(bucket.Objects)
	model.Bytes = types.Int64Value(bucket.Bytes)
	model.CreatedAt = types.StringValue(bucket.CreatedAt.Format(time.RFC3339))
	keyIDs := make([]string, 0, len(bucket.Keys))
	for _, key := range bucket.Keys {
		keyIDs = append(keyIDs, key.KeyID)
	}
	set, setDiags := stringSet(ctx, keyIDs)
	diags.Append(setDiags...)
	model.KeyIDs = set
}
