package compute

import (
	"context"
	"errors"
	"net"
	"net/http"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
)

// ConsoleTicket is one VNC connection's worth of access to an instance's VM.
type ConsoleTicket struct {
	InstanceID string
	VMID       int
	VNC        proxmox.VNCTicket
}

// ConsoleAvailable reports whether an instance can have a console right now,
// without asking the node for one. The node's VNC proxy gives up within
// seconds of being started, so a ticket is only requested when a browser is
// about to connect; handing out a console URL must not start that clock.
func (s *Service) ConsoleAvailable(ctx context.Context, instanceID string) (db.Instance, error) {
	instance, err := db.GetInstance(ctx, s.Pool, instanceID)
	if errors.Is(err, db.ErrNotFound) {
		return db.Instance{}, refuse(http.StatusNotFound, "InvalidInstanceID.NotFound", "instance %s does not exist", instanceID)
	}
	if err != nil {
		return db.Instance{}, err
	}
	switch {
	case instance.State != db.StateRunning || instance.PendingAction != "":
		return db.Instance{}, refuse(http.StatusConflict, "IncorrectInstanceState",
			"a console needs a running instance; %s is %s", instanceID, describeState(instance))
	case instance.VMID == nil || !instance.VMCreated:
		return db.Instance{}, refuse(http.StatusConflict, "IncorrectInstanceState", "instance %s has no VM yet", instanceID)
	}
	return instance, nil
}

// OpenConsole asks the node for a VNC ticket to a running instance.
func (s *Service) OpenConsole(ctx context.Context, instanceID string) (db.Instance, ConsoleTicket, error) {
	instance, err := s.ConsoleAvailable(ctx, instanceID)
	if err != nil {
		return db.Instance{}, ConsoleTicket{}, err
	}
	vmid := *instance.VMID
	// The same rule as every other action: a VM on this VMID that does not
	// carry the instance's ID is someone else's, and a console is a way in.
	owned, err := s.owns(ctx, vmid, instance.ID)
	if err != nil {
		return db.Instance{}, ConsoleTicket{}, s.unavailable(err)
	}
	if !owned {
		return db.Instance{}, ConsoleTicket{}, refuse(http.StatusConflict, "IncorrectInstanceState",
			"VM %d does not belong to %s", vmid, instance.ID)
	}
	vnc, err := s.PVE.VNCProxy(ctx, vmid)
	if err != nil {
		return db.Instance{}, ConsoleTicket{}, s.unavailable(err)
	}
	return instance, ConsoleTicket{InstanceID: instance.ID, VMID: vmid, VNC: vnc}, nil
}

// DialConsole connects to the VNC websocket a ticket opens.
func (s *Service) DialConsole(ctx context.Context, ticket ConsoleTicket) (net.Conn, error) {
	return s.PVE.DialVNC(ctx, ticket.VMID, ticket.VNC)
}
