package provider

import (
	"context"
	"slices"
	"testing"

	"github.com/hashicorp/terraform-plugin-framework/datasource"
	"github.com/hashicorp/terraform-plugin-framework/provider"
	"github.com/hashicorp/terraform-plugin-framework/resource"
)

func TestProviderSchemaAcceptsAnEndpointAndAccessKey(t *testing.T) {
	response := &provider.SchemaResponse{}
	New().Schema(context.Background(), provider.SchemaRequest{}, response)
	for _, name := range []string{"endpoint", "access_key"} {
		if _, ok := response.Schema.Attributes[name]; !ok {
			t.Fatalf("provider schema has no %q attribute", name)
		}
	}
}

func TestEveryResourceAndDataSourceHasItsOwnTypeName(t *testing.T) {
	ctx := context.Background()
	p := New()

	got := []string{}
	seen := map[string]bool{}
	for _, factory := range p.Resources(ctx) {
		response := &resource.MetadataResponse{}
		factory().Metadata(ctx, resource.MetadataRequest{ProviderTypeName: "shakecloud"}, response)
		if response.TypeName == "" {
			t.Fatal("a resource has no type name")
		}
		if seen[response.TypeName] {
			t.Fatalf("duplicate resource type name %q", response.TypeName)
		}
		seen[response.TypeName] = true
		got = append(got, response.TypeName)
	}
	slices.Sort(got)
	want := []string{
		"shakecloud_bucket", "shakecloud_database", "shakecloud_image", "shakecloud_instance",
		"shakecloud_key_pair", "shakecloud_security_group", "shakecloud_security_group_rule",
		"shakecloud_volume", "shakecloud_volume_attachment",
	}
	if !slices.Equal(got, want) {
		t.Fatalf("resources = %v, want %v", got, want)
	}

	dataSources := []string{}
	for _, factory := range p.DataSources(ctx) {
		response := &datasource.MetadataResponse{}
		factory().Metadata(ctx, datasource.MetadataRequest{ProviderTypeName: "shakecloud"}, response)
		dataSources = append(dataSources, response.TypeName)
	}
	if !slices.Equal(dataSources, []string{"shakecloud_caller_identity"}) {
		t.Fatalf("data sources = %v", dataSources)
	}
}
