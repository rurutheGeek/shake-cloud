package client

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// Health calls the unauthenticated health endpoint.
func (c *Client) Health(ctx context.Context) error {
	return c.do(ctx, http.MethodGet, "/healthz", nil, nil, nil)
}

// CallerIdentity answers "who am I" for the configured credential.
func (c *Client) CallerIdentity(ctx context.Context) (CallerIdentity, error) {
	var identity CallerIdentity
	err := c.do(ctx, http.MethodGet, "/v1/caller-identity", nil, nil, &identity)
	return identity, err
}

// --- instances -------------------------------------------------------------

func (c *Client) RunInstances(ctx context.Context, request RunRequest) (Instance, error) {
	var out struct {
		Instance Instance `json:"instance"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/instances", nil, request, &out)
	return out.Instance, err
}

func (c *Client) DescribeInstances(ctx context.Context, accountID string) ([]Instance, error) {
	query := url.Values{}
	if accountID != "" {
		query.Set("account_id", accountID)
	}
	var out struct {
		Instances []Instance `json:"instances"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/instances", query, nil, &out)
	return out.Instances, err
}

func (c *Client) DescribeInstance(ctx context.Context, id string) (Instance, error) {
	var out struct {
		Instance Instance `json:"instance"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/instances/"+url.PathEscape(id), nil, nil, &out)
	return out.Instance, err
}

func (c *Client) AdoptInstance(ctx context.Context, request AdoptRequest) (Instance, error) {
	var out struct {
		Instance Instance `json:"instance"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/instances/adopt", nil, request, &out)
	return out.Instance, err
}

func (c *Client) ModifyInstance(ctx context.Context, id string, request ModifyInstanceRequest) (Instance, error) {
	var out struct {
		Instance Instance `json:"instance"`
	}
	err := c.do(ctx, http.MethodPatch, "/v1/instances/"+url.PathEscape(id), nil, request, &out)
	return out.Instance, err
}

func (c *Client) instanceAction(ctx context.Context, id, action string) (Instance, error) {
	var out struct {
		Instance Instance `json:"instance"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/instances/"+url.PathEscape(id)+"/"+action, nil, struct{}{}, &out)
	return out.Instance, err
}

func (c *Client) StartInstance(ctx context.Context, id string) (Instance, error) {
	return c.instanceAction(ctx, id, "start")
}

func (c *Client) StopInstance(ctx context.Context, id string) (Instance, error) {
	return c.instanceAction(ctx, id, "stop")
}

func (c *Client) RebootInstance(ctx context.Context, id string) (Instance, error) {
	return c.instanceAction(ctx, id, "reboot")
}

// TerminateInstance starts a terminate; the instance is shutting-down until the
// worker has removed the VM, its disk and its address.
func (c *Client) TerminateInstance(ctx context.Context, id string) (Instance, error) {
	var out struct {
		Instance Instance `json:"instance"`
	}
	err := c.do(ctx, http.MethodDelete, "/v1/instances/"+url.PathEscape(id), nil, nil, &out)
	return out.Instance, err
}

// CreateConsoleSession returns a short-lived URL to open in a browser.
func (c *Client) CreateConsoleSession(ctx context.Context, id string) (ConsoleSession, error) {
	var out struct {
		Console ConsoleSession `json:"console"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/instances/"+url.PathEscape(id)+"/console", nil, struct{}{}, &out)
	return out.Console, err
}

func (c *Client) SetInstanceSecurityGroups(ctx context.Context, id string, groupIDs []string) (Instance, error) {
	var out struct {
		Instance Instance `json:"instance"`
	}
	body := map[string]any{"security_group_ids": groupIDs}
	err := c.do(ctx, http.MethodPut, "/v1/instances/"+url.PathEscape(id)+"/security-groups", nil, body, &out)
	return out.Instance, err
}

func (c *Client) DescribeInstanceTypes(ctx context.Context) ([]InstanceType, error) {
	var out struct {
		InstanceTypes []InstanceType `json:"instance_types"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/instance-types", nil, nil, &out)
	return out.InstanceTypes, err
}

// WaitInstance polls until the instance reaches one of the wanted states, or
// the context ends. It returns the last instance seen with a timeout error.
func (c *Client) WaitInstance(ctx context.Context, id string, timeout time.Duration, wanted ...string) (Instance, error) {
	deadline := time.Now().Add(timeout)
	for {
		instance, err := c.DescribeInstance(ctx, id)
		if err != nil {
			return Instance{}, err
		}
		for _, state := range wanted {
			if instance.State == state {
				return instance, nil
			}
		}
		if time.Now().After(deadline) {
			return instance, fmt.Errorf("instance %s is still %s after %s", id, instance.State, timeout)
		}
		select {
		case <-ctx.Done():
			return instance, ctx.Err()
		case <-time.After(3 * time.Second):
		}
	}
}

// --- volumes ---------------------------------------------------------------

func (c *Client) DescribeVolumes(ctx context.Context, accountID string) ([]Volume, error) {
	query := url.Values{}
	if accountID != "" {
		query.Set("account_id", accountID)
	}
	var out struct {
		Volumes []Volume `json:"volumes"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/volumes", query, nil, &out)
	return out.Volumes, err
}

func (c *Client) DescribeVolume(ctx context.Context, id string) (Volume, error) {
	var out struct {
		Volume Volume `json:"volume"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/volumes/"+url.PathEscape(id), nil, nil, &out)
	return out.Volume, err
}

func (c *Client) CreateVolume(ctx context.Context, request CreateVolumeRequest) (Volume, error) {
	var out struct {
		Volume Volume `json:"volume"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/volumes", nil, request, &out)
	return out.Volume, err
}

func (c *Client) ModifyVolume(ctx context.Context, id string, sizeGiB int) (Volume, error) {
	var out struct {
		Volume Volume `json:"volume"`
	}
	err := c.do(ctx, http.MethodPatch, "/v1/volumes/"+url.PathEscape(id), nil, map[string]int{"size_gib": sizeGiB}, &out)
	return out.Volume, err
}

func (c *Client) DeleteVolume(ctx context.Context, id string) (Volume, error) {
	var out struct {
		Volume Volume `json:"volume"`
	}
	err := c.do(ctx, http.MethodDelete, "/v1/volumes/"+url.PathEscape(id), nil, nil, &out)
	return out.Volume, err
}

func (c *Client) AttachVolume(ctx context.Context, id string, request AttachVolumeRequest) (Volume, error) {
	var out struct {
		Volume Volume `json:"volume"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/volumes/"+url.PathEscape(id)+"/attach", nil, request, &out)
	return out.Volume, err
}

func (c *Client) DetachVolume(ctx context.Context, id string) (Volume, error) {
	var out struct {
		Volume Volume `json:"volume"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/volumes/"+url.PathEscape(id)+"/detach", nil, struct{}{}, &out)
	return out.Volume, err
}

// --- security groups -------------------------------------------------------

func (c *Client) DescribeSecurityGroups(ctx context.Context) ([]SecurityGroup, error) {
	var out struct {
		SecurityGroups []SecurityGroup `json:"security_groups"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/security-groups", nil, nil, &out)
	return out.SecurityGroups, err
}

func (c *Client) DescribeSecurityGroup(ctx context.Context, id string) (SecurityGroup, error) {
	var out struct {
		SecurityGroup SecurityGroup `json:"security_group"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/security-groups/"+url.PathEscape(id), nil, nil, &out)
	return out.SecurityGroup, err
}

func (c *Client) CreateSecurityGroup(ctx context.Context, request CreateSecurityGroupRequest) (SecurityGroup, error) {
	var out struct {
		SecurityGroup SecurityGroup `json:"security_group"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/security-groups", nil, request, &out)
	return out.SecurityGroup, err
}

func (c *Client) DeleteSecurityGroup(ctx context.Context, id string) error {
	return c.do(ctx, http.MethodDelete, "/v1/security-groups/"+url.PathEscape(id), nil, nil, nil)
}

func (c *Client) authorizeRules(ctx context.Context, id, direction string, rules []SecurityGroupRuleRequest) (SecurityGroup, error) {
	var out struct {
		SecurityGroup SecurityGroup `json:"security_group"`
	}
	body := map[string]any{"rules": rules}
	err := c.do(ctx, http.MethodPost, "/v1/security-groups/"+url.PathEscape(id)+"/"+direction, nil, body, &out)
	return out.SecurityGroup, err
}

func (c *Client) AuthorizeIngress(ctx context.Context, id string, rules []SecurityGroupRuleRequest) (SecurityGroup, error) {
	return c.authorizeRules(ctx, id, "ingress", rules)
}

func (c *Client) AuthorizeEgress(ctx context.Context, id string, rules []SecurityGroupRuleRequest) (SecurityGroup, error) {
	return c.authorizeRules(ctx, id, "egress", rules)
}

func (c *Client) RevokeSecurityGroupRule(ctx context.Context, groupID, ruleID string) (SecurityGroup, error) {
	var out struct {
		SecurityGroup SecurityGroup `json:"security_group"`
	}
	path := "/v1/security-groups/" + url.PathEscape(groupID) + "/rules/" + url.PathEscape(ruleID)
	err := c.do(ctx, http.MethodDelete, path, nil, nil, &out)
	return out.SecurityGroup, err
}

// --- images ----------------------------------------------------------------

func (c *Client) DescribeImages(ctx context.Context) ([]Image, error) {
	var out struct {
		Images []Image `json:"images"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/images", nil, nil, &out)
	return out.Images, err
}

// DescribeISOs lists installation media: the caller's uploads plus the
// administrator's shared ones.
func (c *Client) DescribeISOs(ctx context.Context) ([]ISO, error) {
	var out struct {
		ISOs []ISO `json:"isos"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/isos", nil, nil, &out)
	return out.ISOs, err
}

// ImportImage uploads a disk image. The name part must precede the file part,
// which is why this streams the multipart body rather than buffering it: an
// image can be gigabytes.
func (c *Client) ImportImage(ctx context.Context, name, filename string, body io.Reader) (Image, error) {
	pipeReader, pipeWriter := io.Pipe()
	writer := multipart.NewWriter(pipeWriter)
	go func() {
		defer pipeWriter.Close()
		if err := writer.WriteField("name", name); err != nil {
			pipeWriter.CloseWithError(err)
			return
		}
		part, err := writer.CreateFormFile("file", filename)
		if err != nil {
			pipeWriter.CloseWithError(err)
			return
		}
		if _, err := io.Copy(part, body); err != nil {
			pipeWriter.CloseWithError(err)
			return
		}
		if err := writer.Close(); err != nil {
			pipeWriter.CloseWithError(err)
		}
	}()
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/images", pipeReader)
	if err != nil {
		return Image{}, err
	}
	request.Header.Set("Content-Type", writer.FormDataContentType())
	request.Header.Set("User-Agent", c.userAgent)
	if c.accessKey != "" {
		request.Header.Set("Authorization", "Bearer "+c.accessKey)
	}
	response, err := c.httpClient.Do(request)
	if err != nil {
		return Image{}, err
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, 4<<20))
	if err != nil {
		return Image{}, err
	}
	if response.StatusCode >= 400 {
		return Image{}, parseAPIError(response.StatusCode, data)
	}
	var out struct {
		Image Image `json:"image"`
	}
	if err := json.Unmarshal(data, &out); err != nil {
		return Image{}, err
	}
	return out.Image, nil
}

func (c *Client) DeleteImage(ctx context.Context, id string) (Image, error) {
	var out struct {
		Image Image `json:"image"`
	}
	err := c.do(ctx, http.MethodDelete, "/v1/images/"+url.PathEscape(id), nil, nil, &out)
	return out.Image, err
}

// --- key pairs -------------------------------------------------------------

func (c *Client) DescribeKeyPairs(ctx context.Context) ([]KeyPair, error) {
	var out struct {
		KeyPairs []KeyPair `json:"key_pairs"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/key-pairs", nil, nil, &out)
	return out.KeyPairs, err
}

func (c *Client) ImportKeyPair(ctx context.Context, name, publicKey string) (KeyPair, error) {
	var out struct {
		KeyPair KeyPair `json:"key_pair"`
	}
	body := map[string]string{"key_name": name, "public_key": publicKey}
	err := c.do(ctx, http.MethodPost, "/v1/key-pairs", nil, body, &out)
	return out.KeyPair, err
}

func (c *Client) DeleteKeyPair(ctx context.Context, name string) error {
	return c.do(ctx, http.MethodDelete, "/v1/key-pairs/"+url.PathEscape(name), nil, nil, nil)
}

// --- access keys -----------------------------------------------------------

func (c *Client) ListAccessKeys(ctx context.Context) ([]AccessKey, error) {
	var out struct {
		AccessKeys []AccessKey `json:"access_keys"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/access-keys", nil, nil, &out)
	return out.AccessKeys, err
}

// CreateAccessKey needs a portal session cookie, not an access key, so the CLI
// cannot use it. It is here for the provider and tests. An empty scope means
// ScopeReadWrite, the API's default.
func (c *Client) CreateAccessKey(ctx context.Context, description string, expiresInDays *int, scope string) (CreatedAccessKey, error) {
	body := map[string]any{"description": description}
	if expiresInDays != nil {
		body["expires_in_days"] = *expiresInDays
	}
	if scope != "" {
		body["scope"] = scope
	}
	var out CreatedAccessKey
	err := c.do(ctx, http.MethodPost, "/v1/access-keys", nil, body, &out)
	return out, err
}

func (c *Client) DeleteAccessKey(ctx context.Context, id string) error {
	return c.do(ctx, http.MethodDelete, "/v1/access-keys/"+url.PathEscape(id), nil, nil, nil)
}

// --- capacity and limits ---------------------------------------------------

func (c *Client) DescribeCapacity(ctx context.Context) (Capacity, error) {
	var out Capacity
	err := c.do(ctx, http.MethodGet, "/v1/capacity", nil, nil, &out)
	return out, err
}

func (c *Client) DescribeLimits(ctx context.Context) (LimitsResponse, error) {
	var out LimitsResponse
	err := c.do(ctx, http.MethodGet, "/v1/limits", nil, nil, &out)
	return out, err
}

// UpdateLimits replaces every override at once; see the OpenAPI description.
func (c *Client) UpdateLimits(ctx context.Context, overrides LimitOverrides) (LimitsResponse, error) {
	var out LimitsResponse
	err := c.do(ctx, http.MethodPut, "/v1/limits", nil, overrides, &out)
	return out, err
}

// --- audit -----------------------------------------------------------------

// LookupEvents reads the audit log, newest first. accountID and eventName are
// optional filters; maxResults 0 uses the API default.
func (c *Client) LookupEvents(ctx context.Context, accountID, eventName string, maxResults int) ([]AuditEvent, error) {
	query := url.Values{}
	if accountID != "" {
		query.Set("account_id", accountID)
	}
	if eventName != "" {
		query.Set("event_name", eventName)
	}
	if maxResults > 0 {
		query.Set("max_results", strconv.Itoa(maxResults))
	}
	var out struct {
		Events []AuditEvent `json:"events"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/audit-events", query, nil, &out)
	return out.Events, err
}
