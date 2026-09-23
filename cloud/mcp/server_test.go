package main

import (
	"context"
	"io"
	"maps"
	"net/http"
	"net/http/httptest"
	"os"
	"slices"
	"strings"
	"testing"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
	"go.yaml.in/yaml/v3"
)

// testKey stands in for an access key. The API is faked in these tests, so no
// real credential is needed.
const testKey = "test-access-key"

// readToolNames maps each read-only API operation to the tool that exposes it.
// TestToolSurfaceMatchesOpenAPI checks this against the OpenAPI document in
// both directions, so a new read operation, or a tool for anything else,
// fails the test rather than drifting quietly.
var readToolNames = map[string]string{
	"GetCallerIdentity":      "shakecloud_get_caller_identity",
	"ListAccessKeys":         "shakecloud_list_access_keys",
	"LookupEvents":           "shakecloud_lookup_events",
	"DescribeInstances":      "shakecloud_describe_instances",
	"DescribeInstance":       "shakecloud_describe_instance",
	"DescribeInstanceTypes":  "shakecloud_describe_instance_types",
	"DescribeCapacity":       "shakecloud_describe_capacity",
	"DescribeLimits":         "shakecloud_describe_limits",
	"DescribeImages":         "shakecloud_describe_images",
	"DescribeISOs":           "shakecloud_describe_isos",
	"DescribeKeyPairs":       "shakecloud_describe_key_pairs",
	"DescribeVolumes":        "shakecloud_describe_volumes",
	"DescribeVolume":         "shakecloud_describe_volume",
	"DescribeSecurityGroups": "shakecloud_describe_security_groups",
	"DescribeSecurityGroup":  "shakecloud_describe_security_group",
	"DescribeBuckets":        "shakecloud_describe_buckets",
	"DescribeBucket":         "shakecloud_describe_bucket",
	"ListS3Keys":             "shakecloud_list_s3_keys",
	"DescribeDatabases":      "shakecloud_describe_databases",
	"DescribeDatabase":       "shakecloud_describe_database",
	"DescribeFunctions":      "shakecloud_describe_functions",
	"DescribeFunction":       "shakecloud_describe_function",
}

// GetDatabaseCredentials is read-only but returns a password, so it stays out
// of a model's context on purpose.
var excludedReadOperations = map[string]bool{"GetDatabaseCredentials": true}

// connect starts the server against the API at endpoint and returns a client
// session talking to it over in-memory transports.
func connect(t *testing.T, endpoint string) *mcp.ClientSession {
	t.Helper()
	s := newServer(client.NewWithUserAgent(endpoint, testKey, "shakecloud-mcp-test"))
	serverTransport, clientTransport := mcp.NewInMemoryTransports()
	ctx := context.Background()
	if _, err := s.Connect(ctx, serverTransport, nil); err != nil {
		t.Fatal(err)
	}
	session, err := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "0"}, nil).Connect(ctx, clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { session.Close() })
	return session
}

// readOperations returns the operationIds the OpenAPI document marks
// x-shakecloud-scope: read that need a credential. Public ones (health, help,
// login) are not tools, and neither is the credential endpoint above.
func readOperations(t *testing.T) []string {
	t.Helper()
	raw, err := os.ReadFile("../openapi/shakecloud.yaml")
	if err != nil {
		t.Fatal(err)
	}
	var spec struct {
		Security []map[string][]string `yaml:"security"`
		Paths    map[string]map[string]struct {
			OperationID string                 `yaml:"operationId"`
			Scope       string                 `yaml:"x-shakecloud-scope"`
			Security    *[]map[string][]string `yaml:"security"`
		} `yaml:"paths"`
	}
	if err := yaml.Unmarshal(raw, &spec); err != nil {
		t.Fatal(err)
	}
	methods := []string{"get", "put", "post", "delete", "patch", "head", "options"}
	var operations []string
	for _, path := range spec.Paths {
		for method, operation := range path {
			if !slices.Contains(methods, method) || operation.Scope != "read" {
				continue
			}
			security := spec.Security
			if operation.Security != nil {
				security = *operation.Security
			}
			if len(security) == 0 {
				continue // public: no access key involved
			}
			operations = append(operations, operation.OperationID)
		}
	}
	slices.Sort(operations)
	return operations
}

func TestToolSurfaceMatchesOpenAPI(t *testing.T) {
	result, err := connect(t, "http://127.0.0.1:1").ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	got := map[string]bool{}
	for _, tool := range result.Tools {
		got[tool.Name] = true
		if tool.Annotations == nil || !tool.Annotations.ReadOnlyHint {
			t.Errorf("%s is not marked read-only", tool.Name)
		}
	}

	operations := readOperations(t)
	want := map[string]bool{}
	for _, operation := range operations {
		if excludedReadOperations[operation] {
			continue
		}
		name, ok := readToolNames[operation]
		if !ok {
			t.Errorf("read operation %s has no tool; add one and a name here", operation)
			continue
		}
		want[name] = true
	}
	for operation, name := range readToolNames {
		if !slices.Contains(operations, operation) {
			t.Errorf("%s is a tool for %s, which is not a read-only operation", name, operation)
		}
	}
	if !maps.Equal(got, want) {
		t.Errorf("registered tools %v, want %v", slices.Sorted(maps.Keys(got)), slices.Sorted(maps.Keys(want)))
	}
}

func TestInputSchemasSayWhatIsRequired(t *testing.T) {
	result, err := connect(t, "http://127.0.0.1:1").ListTools(context.Background(), nil)
	if err != nil {
		t.Fatal(err)
	}
	schemas := map[string]map[string]any{}
	for _, tool := range result.Tools {
		schemas[tool.Name], _ = tool.InputSchema.(map[string]any)
	}
	required := func(name string) []string {
		t.Helper()
		var names []string
		fields, _ := schemas[name]["required"].([]any)
		for _, field := range fields {
			text, _ := field.(string)
			names = append(names, text)
		}
		return names
	}

	if !slices.Contains(required("shakecloud_describe_instance"), "instance_id") {
		t.Errorf("describe_instance must require instance_id: %v", required("shakecloud_describe_instance"))
	}
	if slices.Contains(required("shakecloud_describe_instances"), "account_id") {
		t.Error("account_id is an optional filter but the schema requires it")
	}
	if names := required("shakecloud_get_caller_identity"); len(names) != 0 {
		t.Errorf("get_caller_identity takes no arguments, schema requires %v", names)
	}
}

func TestToolsCallTheAPI(t *testing.T) {
	api := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer "+testKey {
			t.Errorf("Authorization %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/v1/instances":
			if got := r.URL.Query().Get("account_id"); got != "123456789012" {
				t.Errorf("account_id filter %q", got)
			}
			io.WriteString(w, `{"instances":[{"instance_id":"i-0123456789abcdef0","account_id":"123456789012",`+
				`"owner_username":"alice","state":"running","mac_address":"bc:24:11:00:00:01","vcpus":2,`+
				`"memory_mib":2048,"root_disk_gib":20,"ballooning":false,"launch_time":"2026-09-23T00:00:00Z",`+
				`"security_groups":[],"firewall_state":"enabled"}]}`)
		case "/v1/volumes":
			w.WriteHeader(http.StatusForbidden)
			io.WriteString(w, `{"error":{"code":"AccessDenied","message":"this access key is read-only"},`+
				`"request_id":"req-1"}`)
		default:
			t.Errorf("unexpected request %s", r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	defer api.Close()

	session := connect(t, api.URL)
	ctx := context.Background()

	result, err := session.CallTool(ctx, &mcp.CallToolParams{
		Name:      "shakecloud_describe_instances",
		Arguments: map[string]any{"account_id": "123456789012"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.IsError {
		t.Fatalf("tool error: %s", textOf(result))
	}
	instances, ok := result.StructuredContent.([]any)
	if !ok || len(instances) != 1 {
		t.Fatalf("structured content %#v", result.StructuredContent)
	}
	if got := instances[0].(map[string]any)["instance_id"]; got != "i-0123456789abcdef0" {
		t.Errorf("instance_id %v", got)
	}
	if text := textOf(result); !strings.Contains(text, "i-0123456789abcdef0") {
		t.Errorf("text content %q", text)
	}

	// An API refusal is a tool error the model can read and correct from, not
	// a protocol error.
	result, err = session.CallTool(ctx, &mcp.CallToolParams{Name: "shakecloud_describe_volumes"})
	if err != nil {
		t.Fatal(err)
	}
	if !result.IsError {
		t.Fatal("a refused call did not come back as a tool error")
	}
	if text := textOf(result); !strings.Contains(text, "AccessDenied") {
		t.Errorf("error text %q", text)
	}
}

func textOf(result *mcp.CallToolResult) string {
	var b strings.Builder
	for _, content := range result.Content {
		if text, ok := content.(*mcp.TextContent); ok {
			b.WriteString(text.Text)
		}
	}
	return b.String()
}
