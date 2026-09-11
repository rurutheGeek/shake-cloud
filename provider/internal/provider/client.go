package provider

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/diag"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

// waitVolumeState polls a volume until it reaches one of the states, or the
// timeout elapses. Volumes are created and changed asynchronously by the API's
// worker, so a resource is not settled until this returns.
func waitVolumeState(ctx context.Context, c *client.Client, id string, timeout time.Duration, states ...string) (client.Volume, error) {
	deadline := time.Now().Add(timeout)
	for {
		volume, err := c.DescribeVolume(ctx, id)
		if err != nil {
			return volume, err
		}
		for _, state := range states {
			if volume.State == state {
				return volume, nil
			}
		}
		if time.Now().After(deadline) {
			return volume, fmt.Errorf("volume %s is still %s", id, volume.State)
		}
		select {
		case <-ctx.Done():
			return volume, ctx.Err()
		case <-time.After(3 * time.Second):
		}
	}
}

// providerData is what Configure hands to every resource and data source.
type providerData struct {
	Client *client.Client
}

// clientFrom pulls the configured client out of a Configure request, adding a
// diagnostic when the provider was not configured (which only happens if
// something is very wrong, since Configure refuses an empty access key).
func clientFrom(data any) (*client.Client, error) {
	if data == nil {
		return nil, errors.New("the provider is not configured yet")
	}
	configured, ok := data.(*providerData)
	if !ok {
		return nil, fmt.Errorf("unexpected provider data type %T", data)
	}
	return configured.Client, nil
}

// addError records an API refusal with its code and request id, so a Terraform
// run shows what the API said rather than a bare "500".
func addError(diags *diag.Diagnostics, action string, err error) {
	var apiError *client.APIError
	if errors.As(err, &apiError) {
		diags.AddError("shake-cloud: could not "+action, apiError.Error())
		return
	}
	diags.AddError("shake-cloud: could not "+action, err.Error())
}

// stringSetValues reads a Terraform set of strings.
func stringSetValues(ctx context.Context, set types.Set) ([]string, diag.Diagnostics) {
	if set.IsNull() || set.IsUnknown() {
		return nil, nil
	}
	var values []string
	diags := set.ElementsAs(ctx, &values, false)
	return values, diags
}

// stringMapValues reads a Terraform map of strings.
func stringMapValues(ctx context.Context, value types.Map) (map[string]string, diag.Diagnostics) {
	if value.IsNull() || value.IsUnknown() {
		return nil, nil
	}
	values := map[string]string{}
	diags := value.ElementsAs(ctx, &values, false)
	return values, diags
}

// optionalInt turns a Terraform int that may be null into a pointer the client
// treats as "not given".
func optionalInt(value types.Int64) *int {
	if value.IsNull() || value.IsUnknown() {
		return nil
	}
	number := int(value.ValueInt64())
	return &number
}

// stringSet builds a Terraform set from a slice.
func stringSet(ctx context.Context, values []string) (types.Set, diag.Diagnostics) {
	if values == nil {
		values = []string{}
	}
	return types.SetValueFrom(ctx, types.StringType, values)
}

// stringMap builds a Terraform map from a Go map, keeping null for empty.
func stringMap(ctx context.Context, values map[string]string) (types.Map, diag.Diagnostics) {
	if len(values) == 0 {
		return types.MapNull(types.StringType), nil
	}
	return types.MapValueFrom(ctx, types.StringType, values)
}
