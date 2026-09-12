// Package provider implements the Terraform provider for the shake-cloud API.
//
// The resources mirror the API's own shapes: shakecloud_instance is
// aws_instance, shakecloud_volume is aws_ebs_volume, and so on. Every resource
// can be imported, waits for asynchronous work, and treats a 403 as "still
// there" rather than "deleted".
package provider

import (
	"context"
	"os"

	"github.com/hashicorp/terraform-plugin-framework/datasource"
	"github.com/hashicorp/terraform-plugin-framework/provider"
	"github.com/hashicorp/terraform-plugin-framework/provider/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var _ provider.Provider = (*shakecloudProvider)(nil)

// New is the provider factory that main hands to providerserver.Serve.
func New() provider.Provider { return &shakecloudProvider{} }

type shakecloudProvider struct{}

type providerModel struct {
	Endpoint  types.String `tfsdk:"endpoint"`
	AccessKey types.String `tfsdk:"access_key"`
}

func (p *shakecloudProvider) Metadata(_ context.Context, _ provider.MetadataRequest, resp *provider.MetadataResponse) {
	resp.TypeName = "shakecloud"
	resp.Version = "0.1.0"
}

func (p *shakecloudProvider) Schema(_ context.Context, _ provider.SchemaRequest, resp *provider.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "Operate a [shake-cloud](https://github.com/rurutheGeek/shake-cloud) deployment: " +
			"Proxmox-backed instances, volumes and security groups, with EC2's vocabulary.",
		Attributes: map[string]schema.Attribute{
			"endpoint": schema.StringAttribute{
				Optional:    true,
				Description: "API endpoint. Defaults to $SHAKECLOUD_ENDPOINT, then " + client.DefaultEndpoint + ".",
			},
			"access_key": schema.StringAttribute{
				Optional:    true,
				Sensitive:   true,
				Description: "Access key issued by the portal. Defaults to $SHAKECLOUD_ACCESS_KEY.",
			},
		},
	}
}

func (p *shakecloudProvider) Configure(ctx context.Context, req provider.ConfigureRequest, resp *provider.ConfigureResponse) {
	var config providerModel
	resp.Diagnostics.Append(req.Config.Get(ctx, &config)...)
	if resp.Diagnostics.HasError() {
		return
	}

	endpoint := os.Getenv("SHAKECLOUD_ENDPOINT")
	if !config.Endpoint.IsNull() && !config.Endpoint.IsUnknown() {
		endpoint = config.Endpoint.ValueString()
	}
	accessKey := os.Getenv("SHAKECLOUD_ACCESS_KEY")
	if !config.AccessKey.IsNull() && !config.AccessKey.IsUnknown() {
		accessKey = config.AccessKey.ValueString()
	}
	if accessKey == "" {
		resp.Diagnostics.AddError(
			"Missing shake-cloud access key",
			"Set the provider's access_key argument or the SHAKECLOUD_ACCESS_KEY environment variable. "+
				"Issue a key from the portal at the deployment's address.",
		)
		return
	}

	data := &providerData{Client: client.New(endpoint, accessKey)}
	resp.ResourceData = data
	resp.DataSourceData = data
}

func (p *shakecloudProvider) Resources(_ context.Context) []func() resource.Resource {
	return []func() resource.Resource{
		NewInstanceResource,
		NewSecurityGroupResource,
		NewSecurityGroupRuleResource,
		NewVolumeResource,
		NewVolumeAttachmentResource,
		NewKeyPairResource,
		NewBucketResource,
		NewImageResource,
		NewDatabaseResource,
	}
}

func (p *shakecloudProvider) DataSources(_ context.Context) []func() datasource.DataSource {
	return []func() datasource.DataSource{
		NewCallerIdentityDataSource,
	}
}
