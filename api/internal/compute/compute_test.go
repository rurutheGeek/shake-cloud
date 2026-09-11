package compute

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/dbtest"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/netbox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

// fakePVE is an in-memory Proxmox node that behaves like the real one where it
// matters: VMs outside the pool are invisible and make creation fail, per-VM
// calls on an unknown VMID answer 403, and work finishes through tasks.
type fakePVE struct {
	mu         sync.Mutex
	vms        map[int]*fakeVM
	outside    map[int]bool
	volumes    map[string]bool
	tasks      map[string]error
	n          int
	memory     proxmox.Memory
	storage    map[string]proxmox.StorageStatus
	failUpload int
	failCreate error
}

type fakeVM struct {
	status string
	config map[string]any
}

func newFakePVE() *fakePVE {
	return &fakePVE{
		vms: map[int]*fakeVM{}, outside: map[int]bool{}, volumes: map[string]bool{}, tasks: map[string]error{},
		memory: proxmox.Memory{Total: 64 << 30, Free: 30 << 30, Available: 30 << 30},
		storage: map[string]proxmox.StorageStatus{
			"local-lvm":    {Total: 1000, Used: 100, Avail: 900},
			"cloud-images": {Total: 100 << 30, Used: 1 << 30, Avail: 99 << 30},
		},
	}
}

func (f *fakePVE) task(err error) string {
	f.n++
	upid := fmt.Sprintf("UPID:fake:%d", f.n)
	f.tasks[upid] = err
	return upid
}

func forbidden(vmid int) error {
	return &proxmox.Error{Method: "GET", Path: fmt.Sprintf("/vms/%d", vmid), Status: http.StatusForbidden, Reason: "Permission check failed"}
}

func (f *fakePVE) ListVMs(ctx context.Context) ([]proxmox.VM, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	var vms []proxmox.VM
	for vmid, vm := range f.vms {
		vms = append(vms, proxmox.VM{VMID: vmid, Status: vm.status, Pool: "cloud", Node: "apextox"})
	}
	sort.Slice(vms, func(i, j int) bool { return vms[i].VMID < vms[j].VMID })
	return vms, nil
}

func (f *fakePVE) NodeStatus(ctx context.Context) (proxmox.NodeStatus, error) {
	return proxmox.NodeStatus{
		Memory:  f.memory,
		Usage:   0.25,
		CPUInfo: proxmox.CPUInfo{Model: "Fake CPU", Cores: 8, CPUs: 16, Sockets: 1},
	}, nil
}

func (f *fakePVE) StorageStatus(ctx context.Context, storage string) (proxmox.StorageStatus, error) {
	return f.storage[storage], nil
}

func (f *fakePVE) CreateVM(ctx context.Context, params url.Values) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	vmid, _ := strconv.Atoi(params.Get("vmid"))
	if f.outside[vmid] || f.vms[vmid] != nil {
		return "", &proxmox.Error{Method: "POST", Path: "/nodes/apextox/qemu", Status: 500, Reason: fmt.Sprintf("unable to create VM %d: config file already exists", vmid)}
	}
	if f.failCreate != nil {
		return f.task(f.failCreate), nil
	}
	config := map[string]any{"virtio0": "local-lvm:vm-" + params.Get("vmid") + "-disk-0,discard=on,size=3G"}
	for key := range params {
		if key != "virtio0" {
			config[key] = params.Get(key)
		}
	}
	f.vms[vmid] = &fakeVM{status: "stopped", config: config}
	return f.task(nil), nil
}

func (f *fakePVE) VMConfig(ctx context.Context, vmid int) (map[string]any, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	vm := f.vms[vmid]
	if vm == nil {
		return nil, forbidden(vmid)
	}
	copied := map[string]any{}
	for k, v := range vm.config {
		copied[k] = v
	}
	return copied, nil
}

func (f *fakePVE) UpdateVMConfig(ctx context.Context, vmid int, params url.Values) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	vm := f.vms[vmid]
	if vm == nil {
		return forbidden(vmid)
	}
	for key := range params {
		vm.config[key] = params.Get(key)
	}
	return nil
}

func (f *fakePVE) VMStatus(ctx context.Context, vmid int) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if vm := f.vms[vmid]; vm != nil {
		return vm.status, nil
	}
	return "", forbidden(vmid)
}

func (f *fakePVE) Power(ctx context.Context, vmid int, action string, params url.Values) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	vm := f.vms[vmid]
	if vm == nil {
		return "", forbidden(vmid)
	}
	switch action {
	case "start", "reboot":
		vm.status = "running"
	case "stop", "shutdown":
		vm.status = "stopped"
	}
	return f.task(nil), nil
}

var sizeField = regexp.MustCompile(`size=[^,]+`)

func (f *fakePVE) ResizeDisk(ctx context.Context, vmid int, disk, size string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	vm := f.vms[vmid]
	if vm == nil {
		return forbidden(vmid)
	}
	vm.config[disk] = sizeField.ReplaceAllString(vm.config[disk].(string), "size="+size)
	return nil
}

func (f *fakePVE) DeleteVM(ctx context.Context, vmid int) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.vms[vmid] == nil {
		return "", forbidden(vmid)
	}
	delete(f.vms, vmid)
	return f.task(nil), nil
}

func (f *fakePVE) UploadISO(ctx context.Context, storage, filename string, content []byte) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.failUpload > 0 {
		f.failUpload--
		return "", errors.New("upload interrupted")
	}
	f.volumes[storage+":iso/"+filename] = true
	return f.task(nil), nil
}

func (f *fakePVE) ListVolumes(ctx context.Context, storage, content string) ([]proxmox.Volume, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	var volumes []proxmox.Volume
	for volid := range f.volumes {
		if strings.HasPrefix(volid, storage+":"+content+"/") {
			volumes = append(volumes, proxmox.Volume{VolID: volid})
		}
	}
	return volumes, nil
}

func (f *fakePVE) DeleteVolume(ctx context.Context, storage, volid string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	delete(f.volumes, volid)
	return nil
}

func (f *fakePVE) WaitTask(ctx context.Context, upid string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.tasks[upid]
}

type fakeIPAM struct {
	mu        sync.Mutex
	next      int
	addresses map[int]netbox.IPAddress
	allocated int
}

func newFakeIPAM() *fakeIPAM { return &fakeIPAM{addresses: map[int]netbox.IPAddress{}} }

func (f *fakeIPAM) IPRangeID(ctx context.Context, start string) (int, error) { return 2, nil }

func (f *fakeIPAM) IPAddressesByDescription(ctx context.Context, description string) ([]netbox.IPAddress, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	var found []netbox.IPAddress
	for _, address := range f.addresses {
		if address.Description == description {
			found = append(found, address)
		}
	}
	return found, nil
}

func (f *fakeIPAM) AllocateIP(ctx context.Context, rangeID int, a netbox.Allocation) (netbox.IPAddress, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.next++
	f.allocated++
	address := netbox.IPAddress{ID: f.next, Address: fmt.Sprintf("192.168.10.%d/24", 99+f.next), Description: a.Description, DNSName: a.DNSName}
	f.addresses[address.ID] = address
	return address, nil
}

func (f *fakeIPAM) DeleteIPAddress(ctx context.Context, id int) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	delete(f.addresses, id)
	return nil
}

func sampleSite() site.Site {
	s := site.Site{
		Node: "apextox", Pool: "cloud", VMIDFrom: 5000, VMIDTo: 5999, ProbeVMIDs: []int{5998, 5999},
		Storage: site.Storage{VMDisks: "local-lvm", Images: "cloud-images"},
		Network: site.Network{Bridge: "vmbr0", Gateway: "192.168.10.1", DNSServers: []string{"192.168.10.1"}, IPRangeStart: "192.168.10.100/24"},
		Images:  map[string]site.Image{"img-debian13": {Name: "debian13", Volume: "cloud-images:import/debian-13.qcow2"}},
		InstanceTypes: map[string]site.InstanceType{
			"small":   {CPUCores: 2, MemoryMiB: 2048, MemoryMinMiB: 512},
			"large":   {CPUCores: 4, MemoryMiB: 8192, MemoryMinMiB: 2048},
			"2xlarge": {CPUCores: 8, MemoryMiB: 16384, MemoryMinMiB: 4096},
		},
	}
	s.Limits.AccountQuota = site.Quota{Instances: 4, VCPUs: 8, MemoryMiB: 8192, RootDiskGiB: 200}
	s.Limits.RootDiskGiB.Min, s.Limits.RootDiskGiB.Default, s.Limits.RootDiskGiB.Max = 10, 20, 100
	s.Limits.Capacity.MemoryBudgetMiB = 8192
	s.Limits.Capacity.NodeMemoryReserveMiB = 4096
	s.Limits.Capacity.VMDiskMaxUsedPercent = 80
	s.Limits.Capacity.ImageStoreMinFreeMiB = 2048
	return s
}

func testService(t *testing.T) (*Service, *fakePVE, *fakeIPAM) {
	t.Helper()
	pool := dbtest.Pool(t)
	pve, ipam := newFakePVE(), newFakeIPAM()
	s := New(pool, pve, ipam, sampleSite(), slog.New(slog.DiscardHandler), t.TempDir())
	s.RetryDelay = 0
	return s, pve, ipam
}

func newAccount(t *testing.T, s *Service, name string) string {
	t.Helper()
	account, _, err := db.RecordLogin(context.Background(), s.Pool, "sub-"+name, name, name+"@example.test", false)
	if err != nil {
		t.Fatal(err)
	}
	return account.ID
}

var small = RunRequest{ImageID: "img-debian13", InstanceType: "small", Tags: map[string]string{"Name": "web"}}

func run(t *testing.T, s *Service, accountID string, r RunRequest) db.Instance {
	t.Helper()
	instance, created, err := s.Run(context.Background(), accountID, r, nil)
	if err != nil || !created {
		t.Fatalf("Run = %v, created %v", err, created)
	}
	return instance
}

// work processes due work up to n times.
func work(t *testing.T, s *Service, n int) {
	t.Helper()
	for range n {
		if !s.WorkOnce(context.Background()) {
			return
		}
	}
}

func get(t *testing.T, s *Service, id string) db.Instance {
	t.Helper()
	instance, err := db.GetInstance(context.Background(), s.Pool, id)
	if err != nil {
		t.Fatal(err)
	}
	return instance
}

func owner(accountID string) func(db.Instance) bool {
	return func(i db.Instance) bool { return i.AccountID == accountID }
}

func request(t *testing.T, s *Service, id, action, accountID string) (db.Instance, error) {
	t.Helper()
	return s.Request(context.Background(), id, action, owner(accountID), nil)
}

func code(err error) string {
	var e *Error
	if errors.As(err, &e) {
		return e.Code
	}
	return ""
}

func TestLaunchCreatesEverythingAndTerminateRemovesIt(t *testing.T) {
	s, pve, ipam := testService(t)
	accountID := newAccount(t, s, "alice")
	instance := run(t, s, accountID, RunRequest{ImageID: "img-debian13", InstanceType: "small", RootDiskGiB: 30, UserData: "#cloud-config\n", Tags: map[string]string{"Name": "Web 1"}})
	if instance.State != db.StatePending || *instance.VMID != 5000 {
		t.Fatalf("admitted instance: %+v", instance)
	}
	work(t, s, 5)

	launched := get(t, s, instance.ID)
	if launched.State != db.StateRunning || launched.PendingAction != "" || launched.IPAddress != "192.168.10.100/24" {
		t.Fatalf("launched: state=%s action=%s ip=%s err=%s", launched.State, launched.PendingAction, launched.IPAddress, launched.LastError)
	}
	vm := pve.vms[5000]
	if vm == nil || vm.status != "running" || !strings.Contains(vm.config["description"].(string), instance.ID) ||
		vm.config["ide2"] != "cloud-images:iso/shakecloud-"+instance.ID+".iso,media=cdrom" ||
		!strings.Contains(vm.config["net0"].(string), instance.MACAddress) || !strings.Contains(vm.config["virtio0"].(string), "size=30G") ||
		vm.config["pool"] != "cloud" || vm.config["balloon"] != "512" {
		t.Fatalf("VM: %+v", vm)
	}
	if !pve.volumes[launched.SeedVolume] || len(ipam.addresses) != 1 {
		t.Fatalf("seed %q present=%v, addresses %v", launched.SeedVolume, pve.volumes[launched.SeedVolume], ipam.addresses)
	}

	if _, err := request(t, s, instance.ID, db.ActionTerminate, accountID); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	terminated := get(t, s, instance.ID)
	if terminated.State != db.StateTerminated || terminated.TerminatedAt == nil {
		t.Fatalf("terminated: %+v", terminated)
	}
	if len(pve.vms) != 0 || len(pve.volumes) != 0 || len(ipam.addresses) != 0 {
		t.Fatalf("left behind: vms=%v volumes=%v addresses=%v", pve.vms, pve.volumes, ipam.addresses)
	}
	// The VMID is free again.
	if next := run(t, s, accountID, small); *next.VMID != 5000 {
		t.Fatalf("VMID not reused: %d", *next.VMID)
	}
}

func TestALaunchResumesWithoutDuplicatingWork(t *testing.T) {
	s, pve, ipam := testService(t)
	accountID := newAccount(t, s, "alice")
	instance := run(t, s, accountID, small)
	pve.failUpload = 1
	work(t, s, 1)
	interrupted := get(t, s, instance.ID)
	if interrupted.State != db.StatePending || interrupted.Attempts != 1 || interrupted.NetBoxIPID == nil {
		t.Fatalf("after the failed attempt: %+v", interrupted)
	}
	work(t, s, 3)
	if got := get(t, s, instance.ID); got.State != db.StateRunning || ipam.allocated != 1 {
		t.Fatalf("state %s, %d addresses allocated", got.State, ipam.allocated)
	}
}

func TestClientTokenMakesRunIdempotent(t *testing.T) {
	s, _, _ := testService(t)
	accountID := newAccount(t, s, "alice")
	r := small
	r.ClientToken = "deploy-42"
	first := run(t, s, accountID, r)
	again, created, err := s.Run(context.Background(), accountID, r, nil)
	if err != nil || created || again.ID != first.ID {
		t.Fatalf("retry: %v created=%v id=%s", err, created, again.ID)
	}
	r.InstanceType = "large"
	if _, _, err := s.Run(context.Background(), accountID, r, nil); code(err) != "IdempotentParameterMismatch" {
		t.Fatalf("changed parameters: %v", err)
	}
	// Another account may use the same token.
	if _, created, err := s.Run(context.Background(), newAccount(t, s, "bob"), small, nil); err != nil || !created {
		t.Fatalf("bob: %v", err)
	}
}

func TestQuotasAndCapacityAreEnforced(t *testing.T) {
	s, pve, _ := testService(t)
	alice := newAccount(t, s, "alice")
	for range 4 {
		run(t, s, alice, small)
	}
	if _, _, err := s.Run(context.Background(), alice, small, nil); code(err) != "InstanceLimitExceeded" {
		t.Fatalf("fifth instance: %v", err)
	}
	// Alice's four smalls use the whole 8 GiB budget; Bob is within his quota but the cloud is full.
	bob := newAccount(t, s, "bob")
	if _, _, err := s.Run(context.Background(), bob, small, nil); code(err) != "InsufficientInstanceCapacity" {
		t.Fatalf("over budget: %v", err)
	}

	s2, pve2, _ := testService(t)
	carol := newAccount(t, s2, "carol")
	pve2.memory.Available = 5 << 30
	if _, _, err := s2.Run(context.Background(), carol, small, nil); code(err) != "InsufficientInstanceCapacity" {
		t.Fatalf("host short of memory: %v", err)
	}
	_ = pve
	for name, r := range map[string]RunRequest{
		"unknown image": {ImageID: "img-nope", InstanceType: "small"},
		"unknown type":  {ImageID: "img-debian13", InstanceType: "huge"},
		"disk too big":  {ImageID: "img-debian13", InstanceType: "small", RootDiskGiB: 500},
		"reserved tag":  {ImageID: "img-debian13", InstanceType: "small", Tags: map[string]string{"shakecloud:owner": "x"}},
	} {
		if _, _, err := s2.Run(context.Background(), carol, r, nil); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
}

func TestATakenVMIDIsQuarantinedAndTheLaunchMovesOn(t *testing.T) {
	s, pve, _ := testService(t)
	accountID := newAccount(t, s, "alice")
	pve.outside[5000] = true // a VM in another pool, invisible to the token
	instance := run(t, s, accountID, small)
	work(t, s, 5)
	got := get(t, s, instance.ID)
	if got.State != db.StateRunning || *got.VMID != 5001 {
		t.Fatalf("state %s on VMID %d (%s)", got.State, *got.VMID, got.LastError)
	}
	var quarantined bool
	if err := s.Pool.QueryRow(context.Background(), `SELECT EXISTS (SELECT 1 FROM vmid_quarantine WHERE vmid = 5000)`).Scan(&quarantined); err != nil || !quarantined {
		t.Fatalf("5000 not quarantined (%v)", err)
	}
}

func TestAForeignVMIsNeverTouched(t *testing.T) {
	s, pve, _ := testService(t)
	accountID := newAccount(t, s, "alice")
	instance := run(t, s, accountID, small)
	// Someone puts a VM on the allocated VMID before the worker gets there.
	pve.vms[5000] = &fakeVM{status: "running", config: map[string]any{"description": "hand-made"}}
	work(t, s, 5)
	got := get(t, s, instance.ID)
	if got.State != db.StateRunning || *got.VMID == 5000 {
		t.Fatalf("state %s on VMID %d", got.State, *got.VMID)
	}
	if _, err := request(t, s, instance.ID, db.ActionTerminate, accountID); err != nil {
		t.Fatal(err)
	}
	work(t, s, 5)
	if pve.vms[5000] == nil || pve.vms[5000].status != "running" {
		t.Fatal("the hand-made VM was touched")
	}
}

func TestAFailedLaunchIsCleanedUpAndExplained(t *testing.T) {
	s, pve, ipam := testService(t)
	s.MaxAttempts = 2
	accountID := newAccount(t, s, "alice")
	pve.failCreate = errors.New("storage 'local-lvm' does not have enough space")
	instance := run(t, s, accountID, small)
	work(t, s, 10)
	got := get(t, s, instance.ID)
	if got.State != db.StateTerminated || !strings.HasPrefix(got.StateReason, "Server.InternalError") || !strings.Contains(got.StateReason, "enough space") {
		t.Fatalf("state %s reason %q", got.State, got.StateReason)
	}
	if len(pve.volumes) != 0 || len(ipam.addresses) != 0 {
		t.Fatalf("left behind: volumes=%v addresses=%v", pve.volumes, ipam.addresses)
	}
}

func TestTerminateDuringLaunchWins(t *testing.T) {
	s, pve, ipam := testService(t)
	accountID := newAccount(t, s, "alice")
	instance := run(t, s, accountID, small)
	if got, err := request(t, s, instance.ID, db.ActionTerminate, accountID); err != nil || got.State != db.StateShuttingDown {
		t.Fatalf("terminate: %v %+v", err, got)
	}
	work(t, s, 5)
	if got := get(t, s, instance.ID); got.State != db.StateTerminated || len(pve.vms) != 0 || ipam.allocated != 0 {
		t.Fatalf("state %s, vms %d, allocated %d", got.State, len(pve.vms), ipam.allocated)
	}
}

func TestPowerActionsFollowTheStateRules(t *testing.T) {
	s, pve, _ := testService(t)
	alice, bob := newAccount(t, s, "alice"), newAccount(t, s, "bob")
	instance := run(t, s, alice, small)
	if _, err := request(t, s, instance.ID, db.ActionStop, alice); code(err) != "IncorrectInstanceState" {
		t.Fatalf("stop while launching: %v", err)
	}
	work(t, s, 5)
	if _, err := request(t, s, instance.ID, db.ActionStop, bob); code(err) != "InvalidInstanceID.NotFound" {
		t.Fatalf("another account: %v", err)
	}
	if got, err := request(t, s, instance.ID, db.ActionStop, alice); err != nil || got.State != db.StateStopping {
		t.Fatalf("stop: %v %s", err, got.State)
	}
	work(t, s, 2)
	if got := get(t, s, instance.ID); got.State != db.StateStopped || pve.vms[5000].status != "stopped" {
		t.Fatalf("after stop: %s / %s", got.State, pve.vms[5000].status)
	}
	if got, err := request(t, s, instance.ID, db.ActionStop, alice); err != nil || got.State != db.StateStopped {
		t.Fatalf("stopping a stopped instance should be a no-op: %v", err)
	}
	if _, err := request(t, s, instance.ID, db.ActionReboot, alice); code(err) != "IncorrectInstanceState" {
		t.Fatalf("reboot while stopped: %v", err)
	}
	if _, err := request(t, s, instance.ID, db.ActionStart, alice); err != nil {
		t.Fatal(err)
	}
	work(t, s, 2)
	if got := get(t, s, instance.ID); got.State != db.StateRunning {
		t.Fatalf("after start: %s", got.State)
	}
}

func TestReconcileFollowsOutsideChangesButNeverDeletes(t *testing.T) {
	s, pve, ipam := testService(t)
	accountID := newAccount(t, s, "alice")
	a, b := run(t, s, accountID, small), run(t, s, accountID, small)
	work(t, s, 10)
	ctx := context.Background()

	pve.vms[*get(t, s, a.ID).VMID].status = "stopped"
	delete(pve.vms, *get(t, s, b.ID).VMID)
	if err := s.Reconcile(ctx); err != nil {
		t.Fatal(err)
	}
	if got := get(t, s, a.ID); got.State != db.StateStopped || !strings.HasPrefix(got.StateReason, "Client.InstanceInitiatedShutdown") {
		t.Fatalf("a: %s %q", got.State, got.StateReason)
	}
	if got := get(t, s, b.ID); got.State != db.StateRunning || got.StateReason != missingReason {
		t.Fatalf("b: %s %q", got.State, got.StateReason)
	}
	if len(ipam.addresses) != 2 {
		t.Fatal("reconcile released an address")
	}

	// Every VM gone at once looks like a broken token, not a mass deletion.
	delete(pve.vms, *get(t, s, a.ID).VMID)
	if err := s.Reconcile(ctx); err != nil {
		t.Fatal(err)
	}
	if got := get(t, s, a.ID); got.StateReason == missingReason {
		t.Fatal("reconcile acted although nothing was visible")
	}
}

func TestSizeParsing(t *testing.T) {
	for disk, want := range map[string]float64{
		"local-lvm:vm-5000-disk-0,discard=on,size=3G": 3,
		"local-lvm:vm-5000-disk-0,size=2252M":         2252.0 / 1024,
		"local-lvm:vm-5000-disk-0,size=1T":            1024,
		"local-lvm:vm-5000-disk-0":                    0,
	} {
		if got := sizeGiB(disk); got != want {
			t.Errorf("sizeGiB(%q) = %v, want %v", disk, got, want)
		}
	}
}
