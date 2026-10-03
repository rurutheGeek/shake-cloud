package compute

import (
	"context"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

func anyone(db.Instance) bool { return true }

func TestTagsAreReplacedAndARenameReachesTheHypervisor(t *testing.T) {
	s, pve, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	instance := run(t, s, alice, RunRequest{ImageID: "img-debian13", InstanceType: "small",
		Tags: map[string]string{"Name": "win11pro", "Team": "home"}})
	work(t, s, 10)
	vmid := *get(t, s, instance.ID).VMID

	updated, err := s.SetInstanceTags(ctx, instance.ID, map[string]string{"Name": "win-01", "Purpose": "dev"}, anyone, nil)
	if err != nil {
		t.Fatal(err)
	}
	// The whole set is replaced: Team is gone, Purpose is new.
	if updated.Name != "win-01" || updated.Tags["Purpose"] != "dev" || len(updated.Tags) != 2 {
		t.Fatalf("after replacing: name %q tags %v", updated.Name, updated.Tags)
	}
	config, err := pve.VMConfig(ctx, vmid)
	if err != nil {
		t.Fatal(err)
	}
	if config["name"] != "win-01" {
		t.Fatalf("the VM is still called %v", config["name"])
	}

	// Tags alone do not touch the hypervisor's name.
	if _, err := s.SetInstanceTags(ctx, instance.ID, map[string]string{"Name": "win-01"}, anyone, nil); err != nil {
		t.Fatal(err)
	}
	if got := get(t, s, instance.ID); len(got.Tags) != 1 || got.Name != "win-01" {
		t.Fatalf("after dropping Purpose: %v", got.Tags)
	}
}

func TestTagsFollowTheLaunchRulesAndTheOwner(t *testing.T) {
	s, _, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	instance := run(t, s, alice, RunRequest{ImageID: "img-debian13", InstanceType: "small"})
	work(t, s, 10)

	if _, err := s.SetInstanceTags(ctx, instance.ID, map[string]string{"shakecloud:owner": "x"}, anyone, nil); code(err) != "InvalidParameterValue" {
		t.Fatalf("a reserved key: %v", err)
	}
	nobody := func(db.Instance) bool { return false }
	if _, err := s.SetInstanceTags(ctx, instance.ID, map[string]string{"Name": "x"}, nobody, nil); code(err) != "InvalidInstanceID.NotFound" {
		t.Fatalf("someone else's instance: %v", err)
	}
	// nil clears every tag, the name with them.
	cleared, err := s.SetInstanceTags(ctx, instance.ID, nil, anyone, nil)
	if err != nil || len(cleared.Tags) != 0 || cleared.Name != "" {
		t.Fatalf("clearing: %v %v", cleared.Tags, err)
	}
}
