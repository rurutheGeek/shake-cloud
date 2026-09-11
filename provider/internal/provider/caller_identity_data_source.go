package provider

import (
	"context"

	"github.com/hashicorp/terraform-plugin-framework/datasource"
	"github.com/hashicorp/terraform-plugin-framework/datasource/schema"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ datasource.DataSource              = (*callerIdentityDataSource)(nil)
	_ datasource.DataSourceWithConfigure = (*callerIdentityDataSource)(nil)
)

func NewCallerIdentityDataSource() datasource.DataSource { return &callerIdentityDataSource{} }

type callerIdentityDataSource struct {
	client *client.Client
}

type callerIdentityModel struct {
	AccountID      types.String `tfsdk:"account_id"`
	Username       types.String `tfsdk:"username"`
	IsAdmin        types.Bool   `tfsdk:"is_admin"`
	CredentialType types.String `tfsdk:"credential_type"`
	AccessKeyID    types.String `tfsdk:"access_key_id"`
}

func (d *callerIdentityDataSource) Metadata(_ context.Context, req datasource.MetadataRequest, resp *datasource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_caller_identity"
}

func (d *callerIdentityDataSource) Schema(_ context.Context, _ datasource.SchemaRequest, resp *datasource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "Who the configured access key belongs to. Useful for wiring account ids into other " +
			"resources without hard-coding them.",
		Attributes: map[string]schema.Attribute{
			"account_id":      schema.StringAttribute{Computed: true, Description: "The account id (12 digits)."},
			"username":        schema.StringAttribute{Computed: true, Description: "The account's username."},
			"is_admin":        schema.BoolAttribute{Computed: true, Description: "Whether the account is a cloud-admin."},
			"credential_type": schema.StringAttribute{Computed: true, Description: "session or access_key."},
			"access_key_id":   schema.StringAttribute{Computed: true, Description: "The key id, when one was used."},
		},
	}
}

func (d *callerIdentityDataSource) Configure(_ context.Context, req datasource.ConfigureRequest, resp *datasource.ConfigureResponse) {
	if req.ProviderData == nil {
		return
	}
	c, err := clientFrom(req.ProviderData)
	if err != nil {
		resp.Diagnostics.AddError("shake-cloud: provider not configured", err.Error())
		return
	}
	d.client = c
}

func (d *callerIdentityDataSource) Read(ctx context.Context, req datasource.ReadRequest, resp *datasource.ReadResponse) {
	var config callerIdentityModel
	resp.Diagnostics.Append(req.Config.Get(ctx, &config)...)
	if resp.Diagnostics.HasError() {
		return
	}
	identity, err := d.client.CallerIdentity(ctx)
	if err != nil {
		addError(&resp.Diagnostics, "read the caller identity", err)
		return
	}
	config.AccountID = types.StringValue(identity.AccountID)
	config.Username = types.StringValue(identity.Username)
	config.IsAdmin = types.BoolValue(identity.IsAdmin)
	config.CredentialType = types.StringValue(identity.CredentialType)
	config.AccessKeyID = stringOrNull(identity.AccessKeyID)
	resp.Diagnostics.Append(resp.State.Set(ctx, &config)...)
}
