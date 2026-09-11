package server

import (
	"net/http"
	"testing"
)

// The limits and capacity endpoints need the instance settings, which this test
// deployment does not have, so what is checked here is the part that runs
// before them: who is allowed to change a limit, and that the refusal is
// recorded. Whether an override actually changes an admission is checked
// against a real database in internal/compute.
func TestOnlyAdministratorsMayChangeLimits(t *testing.T) {
	s := testServer(t, nil)
	_, alice := session(t, s, "alice", false)
	_, admin := session(t, s, "root", true)
	cookies := func(c *http.Cookie) []*http.Cookie { return []*http.Cookie{c} }

	// A user is refused before the deployment's configuration is consulted, so
	// the answer cannot be used to probe how the cloud is set up.
	expectStatus(t, do(t, s, req{method: "PUT", path: "/v1/limits", body: map[string]any{}, cookies: cookies(alice)}), http.StatusForbidden)
	// An administrator gets as far as needing instances configured.
	expectStatus(t, do(t, s, req{method: "PUT", path: "/v1/limits", body: map[string]any{}, cookies: cookies(admin)}), http.StatusServiceUnavailable)
	for _, path := range []string{"/v1/limits", "/v1/capacity"} {
		expectStatus(t, do(t, s, req{method: "GET", path: path, cookies: cookies(alice)}), http.StatusServiceUnavailable)
	}

	// A typo in a limit name is refused rather than silently ignored, but only
	// once there is a deployment to apply it to: the configuration check runs
	// first, so that case belongs to the compute tests.

	found := events(t, s, req{path: "/v1/audit-events?event_name=UpdateLimits", cookies: cookies(admin)})
	if len(found.Events) != 1 || found.Events[0].ErrorCode != "UnauthorizedOperation" {
		t.Fatalf("the refusal was not audited: %+v", found.Events)
	}
}
