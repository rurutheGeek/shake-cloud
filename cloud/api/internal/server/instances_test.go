package server

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/seed"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

// withInstances gives the server a compute service with no hypervisor behind
// it. Only the paths that never reach Proxmox are exercised here; the ones that
// do are covered in internal/compute against fakes.
func withInstances(t *testing.T, s *Server) {
	t.Helper()
	deployment := site.Site{
		Node: "apextox", Pool: "cloud", VMIDFrom: 5000, VMIDTo: 5999,
		Storage: site.Storage{VMDisks: "local-lvm", Images: "cloud-images"},
		Network: site.Network{Bridge: "vmbr0", Gateway: "192.168.10.1", DNSServers: []string{"192.168.10.1"}, IPRangeStart: "192.168.10.100/24"},
		Images:  map[string]site.Image{"img-debian13": {Name: "debian13", Volume: "cloud-images:import/debian-13.qcow2"}},
		InstanceTypes: map[string]site.InstanceType{
			"small":  {CPUCores: 2, MemoryMiB: 2048, MemoryMinMiB: 512},
			"medium": {CPUCores: 2, MemoryMiB: 4096, MemoryMinMiB: 1024},
		},
	}
	deployment.Limits.AccountQuota = site.Quota{Instances: 4, VCPUs: 8, MemoryMiB: 8192, RootDiskGiB: 200}
	deployment.Limits.RootDiskGiB.Min, deployment.Limits.RootDiskGiB.Default, deployment.Limits.RootDiskGiB.Max = 10, 20, 100
	deployment.Limits.Capacity.MemoryBudgetMiB = 8192
	s.Compute = compute.New(s.pool, nil, nil, deployment, slog.New(slog.DiscardHandler), t.TempDir())
}

// recorded numbers the instance IDs; the database only accepts i- and 17 hex digits.
var recorded int

// record puts an instance straight into the database, standing in for one a
// worker has already launched.
func record(t *testing.T, s *Server, accountID, name string) db.Instance {
	t.Helper()
	recorded++
	instance, err := db.InsertInstance(context.Background(), s.pool, db.Instance{
		ID: fmt.Sprintf("i-%017x", recorded), AccountID: accountID,
		Name: name, ImageID: "img-debian13", InstanceType: "small",
		CPUCores: 2, MemoryMiB: 2048, MemoryMinMiB: 512, Ballooning: true, RootDiskGiB: 20,
		MACAddress: seed.NewMACAddress(), Tags: map[string]string{"Name": name},
	})
	if err != nil {
		t.Fatal(err)
	}
	return instance
}

type instanceEnvelope struct {
	Instance instanceBody `json:"instance"`
}

type instanceList struct {
	Instances []instanceBody `json:"instances"`
}

func TestInstanceEndpointsAnswer503WhenNotConfigured(t *testing.T) {
	s := testServer(t, nil)
	_, cookie := session(t, s, "alice", false)
	for _, r := range []req{
		{method: "GET", path: "/v1/instances", cookies: []*http.Cookie{cookie}},
		{method: "GET", path: "/v1/images", cookies: []*http.Cookie{cookie}},
		{method: "POST", path: "/v1/instances", body: map[string]any{"image_id": "img-debian13", "instance_type": "small"}, cookies: []*http.Cookie{cookie}},
	} {
		expectStatus(t, do(t, s, r), http.StatusServiceUnavailable)
	}
}

// Visibility and authority are deliberately separate: the people sharing one
// host can all see what is running on it, but only an owner (or a cloud-admin)
// may touch it.
func TestEveryInstanceIsVisibleButOnlyItsOwnerMayActOnIt(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	alice, aliceCookie := session(t, s, "alice", false)
	_, bobCookie := session(t, s, "bob", false)
	_, adminCookie := session(t, s, "root", true)
	instance := record(t, s, alice.ID, "web")

	for who, cookie := range map[string]*http.Cookie{"alice": aliceCookie, "bob": bobCookie, "root": adminCookie} {
		seen := decode[instanceList](t, do(t, s, req{method: "GET", path: "/v1/instances", cookies: []*http.Cookie{cookie}}))
		if len(seen.Instances) != 1 || seen.Instances[0].InstanceID != instance.ID {
			t.Fatalf("%s sees %+v", who, seen.Instances)
		}
		if seen.Instances[0].OwnerUsername != "alice" || seen.Instances[0].ImageName != "debian13" {
			t.Errorf("%s: owner and image are not named: %+v", who, seen.Instances[0])
		}
	}
	// Anyone may narrow the list to one account; it is the same public listing.
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/instances?account_id=" + alice.ID, cookies: []*http.Cookie{bobCookie}}), http.StatusOK)

	// Bob can read it but not change it, and is told so rather than being lied to.
	seen := decode[instanceEnvelope](t, do(t, s, req{method: "GET", path: "/v1/instances/" + instance.ID, cookies: []*http.Cookie{bobCookie}}))
	if seen.Instance.InstanceID != instance.ID || seen.Instance.ClientToken != "" {
		t.Fatalf("bob's view: %+v", seen.Instance)
	}
	for _, r := range []req{
		{method: "DELETE", path: "/v1/instances/" + instance.ID, cookies: []*http.Cookie{bobCookie}},
		{method: "POST", path: "/v1/instances/" + instance.ID + "/stop", cookies: []*http.Cookie{bobCookie}},
	} {
		recorder := do(t, s, r)
		expectStatus(t, recorder, http.StatusForbidden)
		if got := decode[errorBody](t, recorder).Error.Code; got != "UnauthorizedOperation" {
			t.Errorf("%s %s: code %q", r.method, r.path, got)
		}
	}
	// An instance that really does not exist still answers 404.
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/instances/i-00000000000000000", cookies: []*http.Cookie{aliceCookie}}), http.StatusNotFound)
	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/instances/i-00000000000000000", cookies: []*http.Cookie{aliceCookie}}), http.StatusNotFound)

	mine := decode[instanceEnvelope](t, do(t, s, req{method: "GET", path: "/v1/instances/" + instance.ID, cookies: []*http.Cookie{aliceCookie}}))
	if mine.Instance.VCPUs != 2 || mine.Instance.MemoryMiB != 2048 || !mine.Instance.Ballooning || mine.Instance.Tags["Name"] != "web" {
		t.Fatalf("instance body: %+v", mine.Instance)
	}
}

func TestTerminateIsAcceptedAndRecorded(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	alice, cookie := session(t, s, "alice", false)
	instance := record(t, s, alice.ID, "web")

	body := decode[instanceEnvelope](t, do(t, s, req{method: "DELETE", path: "/v1/instances/" + instance.ID, cookies: []*http.Cookie{cookie}}))
	if body.Instance.State != db.StateShuttingDown {
		t.Fatalf("state %s", body.Instance.State)
	}
	// Terminating twice is not an error.
	expectStatus(t, do(t, s, req{method: "DELETE", path: "/v1/instances/" + instance.ID, cookies: []*http.Cookie{cookie}}), http.StatusAccepted)
	// A stop while it is shutting down is refused.
	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/instances/" + instance.ID + "/stop", cookies: []*http.Cookie{cookie}}), http.StatusConflict)

	found := events(t, s, req{path: "/v1/audit-events?event_name=TerminateInstance", cookies: []*http.Cookie{cookie}})
	if len(found.Events) != 2 || found.Events[0].ResourceID != instance.ID {
		t.Fatalf("audit: %+v", found.Events)
	}
}

func TestRunInstancesReportsBadParametersWithAWSCodes(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	_, cookie := session(t, s, "alice", false)
	for name, tc := range map[string]struct {
		body map[string]any
		code string
	}{
		"unknown image":   {map[string]any{"image_id": "img-nope", "instance_type": "small"}, "InvalidImageID.NotFound"},
		"unknown type":    {map[string]any{"image_id": "img-debian13", "instance_type": "huge"}, "InvalidParameterValue"},
		"disk too big":    {map[string]any{"image_id": "img-debian13", "instance_type": "small", "root_disk_gib": 500}, "InvalidParameterValue"},
		"no size at all":  {map[string]any{"image_id": "img-debian13"}, "InvalidParameterValue"},
		"memory only":     {map[string]any{"image_id": "img-debian13", "memory_mib": 2048}, "InvalidParameterValue"},
		"memory too smal": {map[string]any{"image_id": "img-debian13", "vcpus": 1, "memory_mib": 64}, "InvalidParameterValue"},
		"floor over top":  {map[string]any{"image_id": "img-debian13", "vcpus": 1, "memory_mib": 1024, "memory_min_mib": 2048}, "InvalidParameterValue"},
	} {
		recorder := do(t, s, req{method: "POST", path: "/v1/instances", body: tc.body, cookies: []*http.Cookie{cookie}})
		expectStatus(t, recorder, http.StatusBadRequest)
		if got := decode[errorBody](t, recorder).Error.Code; got != tc.code {
			t.Errorf("%s: code %q, want %q", name, got, tc.code)
		}
	}
	// An unknown field is a typo, not a default.
	expectStatus(t, do(t, s, req{method: "POST", path: "/v1/instances",
		body: map[string]any{"image_id": "img-debian13", "instance_type": "small", "root_disk_gb": 20}, cookies: []*http.Cookie{cookie}}), http.StatusBadRequest)
}

func TestOnlyAdministratorsMayResizeAnInstance(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	alice, aliceCookie := session(t, s, "alice", false)
	_, adminCookie := session(t, s, "root", true)
	instance := record(t, s, alice.ID, "web")
	body := map[string]any{"memory_mib": 4096}

	// The owner is not enough: a resize re-checks a quota that is not theirs to spend.
	recorder := do(t, s, req{method: "PATCH", path: "/v1/instances/" + instance.ID, body: body, cookies: []*http.Cookie{aliceCookie}})
	expectStatus(t, recorder, http.StatusForbidden)
	if got := decode[errorBody](t, recorder).Error.Code; got != "UnauthorizedOperation" {
		t.Fatalf("code %q", got)
	}
	// An administrator gets as far as the instance's state: it is still launching.
	admin := do(t, s, req{method: "PATCH", path: "/v1/instances/" + instance.ID, body: body, cookies: []*http.Cookie{adminCookie}})
	expectStatus(t, admin, http.StatusConflict)
	if got := decode[errorBody](t, admin).Error.Code; got != "IncorrectInstanceState" {
		t.Fatalf("code %q", got)
	}
	// An empty body says nothing to do.
	expectStatus(t, do(t, s, req{method: "PATCH", path: "/v1/instances/" + instance.ID, body: map[string]any{}, cookies: []*http.Cookie{adminCookie}}), http.StatusBadRequest)

	found := events(t, s, req{path: "/v1/audit-events?event_name=ModifyInstance", cookies: []*http.Cookie{adminCookie}})
	if len(found.Events) == 0 || found.Events[len(found.Events)-1].ErrorCode != "UnauthorizedOperation" {
		t.Fatalf("the refusal was not audited: %+v", found.Events)
	}
}

func TestImagesAndInstanceTypesAreListed(t *testing.T) {
	s := testServer(t, nil)
	withInstances(t, s)
	_, cookie := session(t, s, "alice", false)

	images := decode[struct {
		Images []struct {
			ImageID string `json:"image_id"`
			State   string `json:"state"`
		} `json:"images"`
	}](t, do(t, s, req{method: "GET", path: "/v1/images", cookies: []*http.Cookie{cookie}}))
	if len(images.Images) != 1 || images.Images[0].ImageID != "img-debian13" || images.Images[0].State != "available" {
		t.Fatalf("images: %+v", images.Images)
	}

	types := decode[struct {
		InstanceTypes []struct {
			InstanceType string `json:"instance_type"`
			VCPUs        int    `json:"vcpus"`
			MemoryMiB    int    `json:"memory_mib"`
		} `json:"instance_types"`
	}](t, do(t, s, req{method: "GET", path: "/v1/instance-types", cookies: []*http.Cookie{cookie}}))
	if len(types.InstanceTypes) != 2 || types.InstanceTypes[0].InstanceType != "small" || types.InstanceTypes[1].MemoryMiB != 4096 {
		t.Fatalf("instance types: %+v", types.InstanceTypes)
	}
	// An access key may read them too.
	key := createKey(t, s, cookie)
	expectStatus(t, do(t, s, req{method: "GET", path: "/v1/instance-types", bearer: key.Secret}), http.StatusOK)
}
