package compute

import (
	"context"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
)

func TestAConsoleNeedsARunningInstance(t *testing.T) {
	s, pve, _ := testService(t)
	ctx := context.Background()
	alice := newAccount(t, s, "alice")
	instance := run(t, s, alice, small)

	// Still launching: there is no VM to look at yet.
	if _, err := s.ConsoleAvailable(ctx, instance.ID); code(err) != "IncorrectInstanceState" {
		t.Fatalf("while launching: %v", err)
	}
	work(t, s, 5)

	got, ticket, err := s.OpenConsole(ctx, instance.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.ID != instance.ID || ticket.VMID != *got.VMID || ticket.VNC.Password != "fake-password" || ticket.VNC.Port == 0 {
		t.Fatalf("ticket %+v for %+v", ticket, got)
	}
	// Every page load gets its own ticket.
	if _, again, err := s.OpenConsole(ctx, instance.ID); err != nil || again.VNC.Ticket == ticket.VNC.Ticket {
		t.Fatalf("second ticket %+v (%v)", again, err)
	}

	if _, err := request(t, s, instance.ID, db.ActionStop, alice); err != nil {
		t.Fatal(err)
	}
	work(t, s, 3)
	if _, _, err := s.OpenConsole(ctx, instance.ID); code(err) != "IncorrectInstanceState" {
		t.Fatalf("stopped: %v", err)
	}
	if _, err := s.ConsoleAvailable(ctx, "i-0000000000000dead"); code(err) != "InvalidInstanceID.NotFound" {
		t.Fatalf("missing: %v", err)
	}
	if pve.consoles != 2 {
		t.Fatalf("the node was asked for %d consoles, want 2", pve.consoles)
	}
}

func TestAConsoleIsNeverOpenedToAVMTheInstanceDidNotCreate(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")
	instance := run(t, s, alice, small)
	work(t, s, 5)
	vmid := *get(t, s, instance.ID).VMID

	// Someone replaced the VM on this VMID by hand.
	pve.vms[vmid].config["description"] = "hand-made"
	if _, _, err := s.OpenConsole(context.Background(), instance.ID); code(err) != "IncorrectInstanceState" {
		t.Fatalf("foreign VM: %v", err)
	}
	if pve.consoles != 0 {
		t.Fatal("a console ticket was requested for a VM the instance does not own")
	}
}
