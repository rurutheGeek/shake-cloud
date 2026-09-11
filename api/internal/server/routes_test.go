package server

import (
	"os"
	"slices"
	"sort"
	"strings"
	"testing"

	"go.yaml.in/yaml/v3"
)

type specOperation struct {
	OperationID string                 `yaml:"operationId"`
	Security    *[]map[string][]string `yaml:"security"`
}

// The OpenAPI document is the API's source of truth. This keeps the route
// table from drifting from it in either direction, including which endpoints
// accept which credentials.
func TestRoutesMatchOpenAPI(t *testing.T) {
	raw, err := os.ReadFile("../../../openapi/shakecloud.yaml")
	if err != nil {
		t.Fatal(err)
	}
	var spec struct {
		Security []map[string][]string               `yaml:"security"`
		Paths    map[string]map[string]specOperation `yaml:"paths"`
	}
	if err := yaml.Unmarshal(raw, &spec); err != nil {
		t.Fatal(err)
	}

	methods := []string{"get", "put", "post", "delete", "patch", "head", "options"}
	documented := map[string]string{}
	var ids []string
	for path, operations := range spec.Paths {
		for method, operation := range operations {
			if !slices.Contains(methods, method) {
				continue
			}
			security := spec.Security
			if operation.Security != nil {
				security = *operation.Security
			}
			documented[strings.ToUpper(method)+" "+path] = operation.OperationID + " " + specAuth(security)
			ids = append(ids, operation.OperationID)
		}
	}
	implemented := map[string]string{}
	for _, rt := range routes() {
		implemented[rt.method+" "+rt.pattern] = rt.operationID + " " + routeAuth(rt.auth)
	}

	for _, key := range sortedKeys(documented) {
		if got, ok := implemented[key]; !ok {
			t.Errorf("documented but not routed: %s (%s)", key, documented[key])
		} else if got != documented[key] {
			t.Errorf("%s: route says %q, OpenAPI says %q", key, got, documented[key])
		}
	}
	for _, key := range sortedKeys(implemented) {
		if _, ok := documented[key]; !ok {
			t.Errorf("routed but not documented: %s (%s)", key, implemented[key])
		}
	}
	sort.Strings(ids)
	if unique := slices.Compact(slices.Clone(ids)); len(unique) != len(ids) {
		t.Errorf("operationIds are not unique: %v", ids)
	}
}

func specAuth(security []map[string][]string) string {
	schemes := map[string]bool{}
	for _, requirement := range security {
		for name := range requirement {
			schemes[name] = true
		}
	}
	switch {
	case len(schemes) == 0:
		return "public"
	case len(schemes) == 2 && schemes["accessKey"] && schemes["session"]:
		return "any-credential"
	case len(schemes) == 1 && schemes["session"]:
		return "session-only"
	default:
		return "unsupported"
	}
}

func routeAuth(mode authMode) string {
	return map[authMode]string{public: "public", anyCredential: "any-credential", sessionOnly: "session-only"}[mode]
}

func sortedKeys(m map[string]string) []string {
	keys := make([]string, 0, len(m))
	for key := range m {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
