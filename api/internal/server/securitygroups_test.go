package server

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

type groupEnvelope struct {
	SecurityGroup securityGroupBody `json:"security_group"`
}

type groupList struct {
	SecurityGroups []securityGroupBody `json:"security_groups"`
}

type volumeEnvelope struct {
	Volume volumeBody `json:"volume"`
}

type volumeList struct {
	Volumes []volumeBody `json:"volumes"`
}

// A group's rules say where someone's VM is open, so unlike instances groups
// are not listed to other accounts; admins see them all.
func TestSecurityGroupsArePrivateToTheirAccount(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	_, alice := session(t, s, "alice", false)
	_, bob := session(t, s, "bob", false)
	_, admin := session(t, s, "root", true)

	created := do(t, s, req{method: "POST", path: "/v1/security-groups", cookies: []*http.Cookie{alice},
		body: map[string]any{"group_name": "web", "description": "front"}})
	expectStatus(t, created, http.StatusCreated)
	web := decode[groupEnvelope](t, created).SecurityGroup
	if web.IsDefault || len(web.Ingress) != 0 || len(web.Egress) != 2 {
		t.Fatalf("a new group starts with egress all and no ingress: %+v", web)
	}

	listed := decode[groupList](t, do(t, s, req{method: "GET", path: "/v1/security-groups", cookies: []*http.Cookie{alice}}))
	if len(listed.SecurityGroups) != 2 || !listed.SecurityGroups[0].IsDefault || len(listed.SecurityGroups[0].Ingress) != 2 {
		t.Fatalf("alice's groups: %+v", listed.SecurityGroups)
	}
	bobs := decode[groupList](t, do(t, s, req{method: "GET", path: "/v1/security-groups", cookies: []*http.Cookie{bob}}))
	for _, group := range bobs.SecurityGroups {
		if group.GroupID == web.GroupID {
			t.Fatal("bob can list alice's group")
		}
	}
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/security-groups/" + web.GroupID, cookies: []*http.Cookie{bob}}), http.StatusNotFound)
	rule := map[string]any{"rules": []map[string]any{{"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr": "0.0.0.0/0"}}}
	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/security-groups/" + web.GroupID + "/ingress", cookies: []*http.Cookie{bob}, body: rule}), http.StatusNotFound)
	all := decode[groupList](t, do(t, s, req{method: "GET", path: "/v1/security-groups", cookies: []*http.Cookie{admin}}))
	if len(all.SecurityGroups) < 3 {
		t.Fatalf("admin sees %d groups", len(all.SecurityGroups))
	}

	added := do(t, s, req{method: "POST", path: "/v1/security-groups/" + web.GroupID + "/ingress", cookies: []*http.Cookie{alice}, body: rule})
	expectStatus(t, added, http.StatusOK)
	web = decode[groupEnvelope](t, added).SecurityGroup
	if len(web.Ingress) != 1 || *web.Ingress[0].FromPort != 22 || web.Ingress[0].CIDR != "0.0.0.0/0" {
		t.Fatalf("after authorizing: %+v", web.Ingress)
	}
	duplicate := do(t, s, req{method: "POST", path: "/v1/security-groups/" + web.GroupID + "/ingress", cookies: []*http.Cookie{alice}, body: rule})
	expectError(t, duplicate, http.StatusConflict, "InvalidPermission.Duplicate")

	revoked := do(t, s, req{method: "DELETE", path: "/v1/security-groups/" + web.GroupID + "/rules/" + web.Ingress[0].RuleID, cookies: []*http.Cookie{alice}})
	expectStatus(t, revoked, http.StatusOK)
	if got := decode[groupEnvelope](t, revoked).SecurityGroup; len(got.Ingress) != 0 {
		t.Fatalf("after revoking: %+v", got.Ingress)
	}

	expectError(t, do(t, s, req{method: "DELETE", path: "/v1/security-groups/" + listed.SecurityGroups[0].GroupID, cookies: []*http.Cookie{alice}}),
		http.StatusConflict, "CannotDelete")
	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/security-groups/" + web.GroupID, cookies: []*http.Cookie{alice}}), http.StatusNoContent)
}

func TestAnInstancesGroupsAreChangedByItsOwner(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	aliceAccount, alice := session(t, s, "alice", false)
	_, bob := session(t, s, "bob", false)
	instance := record(t, s, aliceAccount.ID, "web")

	described := decode[instanceEnvelope](t, do(t, s, req{method: "GET", path: "/v1/instances/" + instance.ID, cookies: []*http.Cookie{alice}}))
	if described.Instance.SecurityGroups == nil || len(described.Instance.SecurityGroups) != 0 || described.Instance.FirewallState != "in-sync" {
		t.Fatalf("an instance with no groups: %+v", described.Instance)
	}

	web := decode[groupEnvelope](t, do(t, s, req{method: "POST", path: "/v1/security-groups", cookies: []*http.Cookie{alice},
		body: map[string]any{"group_name": "web"}})).SecurityGroup
	path := "/v1/instances/" + instance.ID + "/security-groups"
	body := map[string]any{"security_group_ids": []string{web.GroupID}}
	expectError(t, do(t, s, req{method: "PUT", path: path, cookies: []*http.Cookie{bob}, body: body}), http.StatusForbidden, "UnauthorizedOperation")

	changed := do(t, s, req{method: "PUT", path: path, cookies: []*http.Cookie{alice}, body: body})
	expectStatus(t, changed, http.StatusOK)
	got := decode[instanceEnvelope](t, changed).Instance
	if len(got.SecurityGroups) != 1 || got.SecurityGroups[0].GroupName != "web" || got.FirewallState != "applying" {
		t.Fatalf("after the change: %+v", got)
	}
	listed := decode[instanceList](t, do(t, s, req{method: "GET", path: "/v1/instances", cookies: []*http.Cookie{bob}}))
	if len(listed.Instances) != 1 || len(listed.Instances[0].SecurityGroups) != 1 {
		t.Fatalf("listing: %+v", listed.Instances)
	}
	expectError(t, do(t, s, req{method: "DELETE", path: "/v1/security-groups/" + web.GroupID, cookies: []*http.Cookie{alice}}),
		http.StatusConflict, "DependencyViolation")
}

// Volumes are visible like instances; changing one takes owning it.
func TestEveryVolumeIsVisibleButOnlyItsOwnerMayChangeIt(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	aliceAccount, alice := session(t, s, "alice", false)
	_, bob := session(t, s, "bob", false)
	volume, err := db.InsertVolume(context.Background(), s.pool, db.Volume{
		ID: fmt.Sprintf("vol-%017x", 1), AccountID: aliceAccount.ID, ClientToken: "mine", SizeGiB: 20, Tags: map[string]string{"Name": "data"},
	})
	if err != nil {
		t.Fatal(err)
	}

	listed := decode[volumeList](t, do(t, s, req{method: "GET", path: "/v1/volumes", cookies: []*http.Cookie{bob}}))
	if len(listed.Volumes) != 1 || listed.Volumes[0].OwnerUsername != "alice" || listed.Volumes[0].ClientToken != "" {
		t.Fatalf("bob's view: %+v", listed.Volumes)
	}
	mine := decode[volumeEnvelope](t, do(t, s, req{method: "GET", path: "/v1/volumes/" + volume.ID, cookies: []*http.Cookie{alice}})).Volume
	if mine.ClientToken != "mine" || mine.Serial != "vol00000000000000001" || mine.State != "creating" || mine.Attachment != nil {
		t.Fatalf("alice's view: %+v", mine)
	}

	path := "/v1/volumes/" + volume.ID
	for _, r := range []req{
		{method: "PATCH", path: path, body: map[string]any{"size_gib": 40}},
		{method: "DELETE", path: path},
		{method: "POST", path: path + "/detach"},
		{method: "POST", path: path + "/attach", body: map[string]any{"instance_id": "i-00000000000000001"}},
	} {
		r.cookies = []*http.Cookie{bob}
		expectError(t, do(t, s, r), http.StatusForbidden, "UnauthorizedOperation")
	}
	expectError(t, do(t, s, req{method: "GET", path: "/v1/volumes/vol-00000000000000099", cookies: []*http.Cookie{bob}}),
		http.StatusNotFound, "InvalidVolume.NotFound")
	// Still being created: nothing may be done to it yet.
	expectError(t, do(t, s, req{method: "DELETE", path: path, cookies: []*http.Cookie{alice}}), http.StatusConflict, "IncorrectState")
}

// expectError checks both the status and the EC2-style code of a refusal.
func expectError(t *testing.T, recorder *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	expectStatus(t, recorder, status)
	var body struct {
		Error struct {
			Code string `json:"code"`
		} `json:"error"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil || body.Error.Code != code {
		t.Fatalf("code %q, want %s: %s", body.Error.Code, code, recorder.Body.String())
	}
}
