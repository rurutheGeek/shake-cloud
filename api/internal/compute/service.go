// Package compute runs instances. Requests are admitted here (validation,
// quota, capacity) and recorded; a worker then turns each recorded action into
// NetBox addresses, seed ISOs and Proxmox VMs, one idempotent step at a time.
package compute

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/netbox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/seed"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

// Hypervisor is the part of *proxmox.Client the service uses.
type Hypervisor interface {
	ListVMs(ctx context.Context) ([]proxmox.VM, error)
	NodeStatus(ctx context.Context) (proxmox.NodeStatus, error)
	StorageStatus(ctx context.Context, storage string) (proxmox.StorageStatus, error)
	CreateVM(ctx context.Context, params url.Values) (string, error)
	VMConfig(ctx context.Context, vmid int) (map[string]any, error)
	UpdateVMConfig(ctx context.Context, vmid int, params url.Values) error
	VMStatus(ctx context.Context, vmid int) (string, error)
	Power(ctx context.Context, vmid int, action string, params url.Values) (string, error)
	ResizeDisk(ctx context.Context, vmid int, disk, size string) error
	DeleteVM(ctx context.Context, vmid int) (string, error)
	UploadISO(ctx context.Context, storage, filename string, content []byte) (string, error)
	UploadISOStream(ctx context.Context, storage, filename string, body io.Reader, size int64) (string, error)
	UploadImage(ctx context.Context, storage, filename string, body io.Reader, size int64) (string, error)
	ListVolumes(ctx context.Context, storage, content string) ([]proxmox.Volume, error)
	DeleteVolume(ctx context.Context, storage, volid string) error
	WaitTask(ctx context.Context, upid string) error
	VNCProxy(ctx context.Context, vmid int) (proxmox.VNCTicket, error)
	DialVNC(ctx context.Context, vmid int, ticket proxmox.VNCTicket) (net.Conn, error)
	ConfigureVM(ctx context.Context, vmid int, params url.Values) (string, error)
	UnlinkDisks(ctx context.Context, vmid int, keys []string, force bool) error
	MoveDisk(ctx context.Context, vmid int, disk string, targetVMID int, targetDisk string) (string, error)
	VMPending(ctx context.Context, vmid int) ([]proxmox.PendingChange, error)
	FirewallRules(ctx context.Context, vmid int) ([]proxmox.FirewallRule, error)
	InsertFirewallRule(ctx context.Context, vmid int, rule proxmox.FirewallRule) error
	DeleteFirewallRule(ctx context.Context, vmid, pos int) error
	FirewallOptions(ctx context.Context, vmid int) (map[string]any, error)
	SetFirewallOptions(ctx context.Context, vmid int, params url.Values) error
	IPSets(ctx context.Context, vmid int) ([]string, error)
	CreateIPSet(ctx context.Context, vmid int, name string) error
	IPSetEntries(ctx context.Context, vmid int, name string) ([]string, error)
	AddIPSetEntry(ctx context.Context, vmid int, name, cidr string) error
	DeleteIPSetEntry(ctx context.Context, vmid int, name, cidr string) error
}

// IPAM is the part of *netbox.Client the service uses.
type IPAM interface {
	IPRangeID(ctx context.Context, startAddress string) (int, error)
	IPAddressesByDescription(ctx context.Context, description string) ([]netbox.IPAddress, error)
	AllocateIP(ctx context.Context, rangeID int, allocation netbox.Allocation) (netbox.IPAddress, error)
	DeleteIPAddress(ctx context.Context, id int) error
}

// Error is a refusal the HTTP layer reports with an EC2-style code.
type Error struct {
	Status  int
	Code    string
	Message string
}

func (e *Error) Error() string { return e.Code + ": " + e.Message }

func refuse(status int, code, format string, args ...any) *Error {
	return &Error{Status: status, Code: code, Message: fmt.Sprintf(format, args...)}
}

// NetBoxTag marks addresses the cloud API allocated (platform/terraform/tags.yaml).
const NetBoxTag = "managed-by-cloud-api"

type Service struct {
	Pool    *pgxpool.Pool
	PVE     Hypervisor
	IPAM    IPAM
	Site    site.Site
	Log     *slog.Logger
	WorkDir string
	// UploadDir is disk-backed space for an image on its way to the node. It
	// cannot be WorkDir: that is a tmpfs, and an image does not fit in RAM.
	// Empty means this deployment refuses uploads rather than filling memory.
	UploadDir string
	// Garage is the object store's administration API. Nil when this
	// deployment has no object storage, and the bucket endpoints answer 503.
	Garage BucketStore
	// S3Endpoint and S3Region are what a bucket's owner points a client at.
	S3Endpoint string
	S3Region   string
	// MaxAttempts is how often a launch or power action is tried before it is
	// abandoned. Terminates are retried until they succeed: giving up would
	// leak a VM, an address or an ISO.
	MaxAttempts int
	// RetryDelay is the first backoff; it doubles up to five minutes.
	RetryDelay time.Duration

	wake    chan struct{}
	rangeMu sync.Mutex
	rangeID int
	now     func() time.Time
}

func New(pool *pgxpool.Pool, pve Hypervisor, ipam IPAM, s site.Site, log *slog.Logger, workDir string) *Service {
	return &Service{
		Pool: pool, PVE: pve, IPAM: ipam, Site: s, Log: log, WorkDir: workDir,
		MaxAttempts: 6, RetryDelay: 5 * time.Second,
		wake: make(chan struct{}, 1), now: time.Now,
	}
}

// Wake nudges the worker to look for work now rather than at its next poll.
func (s *Service) Wake() {
	select {
	case s.wake <- struct{}{}:
	default:
	}
}

// RunRequest is the body of RunInstances. The size fields are pointers so that
// "not given" is distinguishable from zero: a named instance_type fills in
// whatever the caller left out, and nothing forces the caller to use one.
type RunRequest struct {
	ImageID      string `json:"image_id"`
	InstanceType string `json:"instance_type"`
	KeyName      string `json:"key_name"`
	VCPUs        *int   `json:"vcpus"`
	MemoryMiB    *int   `json:"memory_mib"`
	MemoryMinMiB *int   `json:"memory_min_mib"`
	Ballooning   *bool  `json:"ballooning"`
	RootDiskGiB  int    `json:"root_disk_gib"`
	UserData     string `json:"user_data"`
	ClientToken  string `json:"client_token"`
	// InstallISOID turns the launch into an installation: instead of copying an
	// image to the root disk, the VM boots this ISO and the guest installs
	// itself. DriverISOID is an optional second CD (the virtio-win disc).
	// GuestOS is "windows" or "linux" and defaults from the ISO's own os.
	InstallISOID string            `json:"install_iso_id,omitempty"`
	DriverISOID  string            `json:"driver_iso_id,omitempty"`
	GuestOS      string            `json:"guest_os,omitempty"`
	Tags         map[string]string `json:"tags"`
	// SecurityGroupIDs omitted means the account's default group. omitempty
	// keeps the request hash of a launch that names none what it was before
	// groups existed, so a retried client token still matches.
	SecurityGroupIDs []string `json:"security_group_ids,omitempty"`
}

// Spec is the size an instance actually gets. TypeName is the preset it came
// from, and empty when the numbers were given directly.
type Spec struct {
	CPUCores     int
	MemoryMiB    int
	MemoryMinMiB int
	Ballooning   bool
	TypeName     string
}

const maxUserData = 16 * 1024

// A guest below this cannot boot the cloud images, and Proxmox itself refuses
// very small values, so it is checked before anything is created.
const minMemoryMiB = 512

// balloonFloor is the default reclaim floor when ballooning is on and the
// caller did not name one: a quarter of the ceiling, never below the minimum.
func balloonFloor(memoryMiB int) int {
	return max(minMemoryMiB, memoryMiB/4)
}

var clientToken = regexp.MustCompile(`^[\x21-\x7e]{1,64}$`)

// EffectiveLimits returns the deployment's declared limits with the
// administrator's overrides applied, and the overrides themselves so a caller
// can tell a changed limit from a default one.
func (s *Service) EffectiveLimits(ctx context.Context, q db.Querier) (site.Limits, db.LimitOverrides, error) {
	if q == nil {
		q = s.Pool
	}
	overrides, err := db.GetLimitOverrides(ctx, q)
	if err != nil {
		return site.Limits{}, db.LimitOverrides{}, err
	}
	return WithOverrides(s.Site.Limits, overrides), overrides, nil
}

// WithOverrides is where the two halves of a limit meet: the default declared
// in platform/terraform/cloud.yaml and the change an administrator made.
func WithOverrides(l site.Limits, o db.LimitOverrides) site.Limits {
	set := func(target, override *int) {
		if override != nil {
			*target = *override
		}
	}
	set(&l.AccountQuota.Instances, o.AccountInstances)
	set(&l.AccountQuota.VCPUs, o.AccountVCPUs)
	set(&l.AccountQuota.MemoryMiB, o.AccountMemoryMiB)
	set(&l.AccountQuota.RootDiskGiB, o.AccountRootDiskGiB)
	set(&l.RootDiskGiB.Min, o.RootDiskMinGiB)
	set(&l.RootDiskGiB.Default, o.RootDiskDefaultGiB)
	set(&l.RootDiskGiB.Max, o.RootDiskMaxGiB)
	set(&l.Capacity.MemoryBudgetMiB, o.MemoryBudgetMiB)
	set(&l.Capacity.NodeMemoryReserveMiB, o.NodeMemoryReserveMiB)
	set(&l.Capacity.VMDiskMaxUsedPercent, o.VMDiskMaxUsedPercent)
	set(&l.Capacity.ImageStoreMinFreeMiB, o.ImageStoreMinFreeMiB)
	set(&l.Capacity.MaxImageGiB, o.MaxImageGiB)
	set(&l.AccountQuota.Volumes, o.AccountVolumes)
	set(&l.AccountQuota.VolumeGiB, o.AccountVolumeGiB)
	set(&l.VolumeSizeGiB.Min, o.VolumeMinGiB)
	set(&l.VolumeSizeGiB.Max, o.VolumeMaxGiB)
	return l
}

// resolveSpec turns a request into the size the instance gets. A named preset
// is a starting point the caller may override field by field; without one, the
// cpu and memory have to be given outright.
func (s *Service) resolveSpec(r *RunRequest) (Spec, error) {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
	}
	var spec Spec
	if r.InstanceType != "" {
		preset, ok := s.Site.InstanceTypes[r.InstanceType]
		if !ok {
			return Spec{}, bad("instance type %q does not exist; see GET /v1/instance-types, or give vcpus and memory_mib instead", r.InstanceType)
		}
		spec = Spec{CPUCores: preset.CPUCores, MemoryMiB: preset.MemoryMiB, MemoryMinMiB: preset.MemoryMinMiB, TypeName: r.InstanceType}
	} else if r.VCPUs == nil || r.MemoryMiB == nil {
		return Spec{}, bad("give an instance_type, or both vcpus and memory_mib")
	}

	memoryGiven := r.MemoryMiB != nil
	if r.VCPUs != nil {
		spec.CPUCores = *r.VCPUs
	}
	if memoryGiven {
		spec.MemoryMiB = *r.MemoryMiB
	}
	// Any explicit number means this is no longer that preset.
	if r.VCPUs != nil || memoryGiven || r.MemoryMinMiB != nil || r.Ballooning != nil {
		spec.TypeName = ""
	}

	spec.Ballooning = r.Ballooning == nil || *r.Ballooning
	switch {
	case !spec.Ballooning:
		// Proxmox disables the balloon driver by targeting 0, so a floor would
		// be a figure nothing enforces.
		spec.MemoryMinMiB = 0
	case r.MemoryMinMiB != nil:
		spec.MemoryMinMiB = *r.MemoryMinMiB
	case spec.MemoryMinMiB == 0 || memoryGiven:
		// A preset's floor does not survive a changed ceiling.
		spec.MemoryMinMiB = balloonFloor(spec.MemoryMiB)
	}

	if err := validateSpec(spec); err != nil {
		return Spec{}, err
	}
	return spec, nil
}

// validateSpec rejects a size no guest could boot. Launches and an
// administrator's resize share it, so the two cannot drift apart.
func validateSpec(spec Spec) error {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
	}
	switch {
	case spec.CPUCores < 1:
		return bad("vcpus must be at least 1")
	case spec.MemoryMiB < minMemoryMiB:
		return bad("memory_mib must be at least %d", minMemoryMiB)
	case spec.Ballooning && spec.MemoryMinMiB < minMemoryMiB:
		return bad("memory_min_mib must be at least %d", minMemoryMiB)
	case spec.Ballooning && spec.MemoryMinMiB > spec.MemoryMiB:
		return bad("memory_min_mib (%d) must not exceed memory_mib (%d)", spec.MemoryMinMiB, spec.MemoryMiB)
	}
	return nil
}

func (s *Service) validate(ctx context.Context, r *RunRequest, limits site.Limits) (Spec, error) {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
	}
	switch {
	case r.ImageID == "" && r.InstallISOID == "":
		return Spec{}, bad("either image_id or install_iso_id is required")
	case r.ImageID != "" && r.InstallISOID != "":
		return Spec{}, bad("image_id and install_iso_id cannot be combined: install media is not a root image")
	case r.GuestOS != "" && r.GuestOS != seed.OSLinux && r.GuestOS != seed.OSWindows:
		return Spec{}, bad("guest_os must be linux or windows")
	}
	if r.ImageID != "" {
		// Shared images and uploaded ones are both launchable, so existence is a
		// question for the resolver rather than for site.json alone.
		image, err := s.ResolveImage(ctx, s.Pool, r.ImageID)
		if err != nil {
			return Spec{}, err
		}
		if r.GuestOS == "" {
			r.GuestOS = image.OS
		}
		if image.OS != "" && r.GuestOS != image.OS {
			return Spec{}, bad("image %s is a %s guest, not %s", r.ImageID, image.OS, r.GuestOS)
		}
	} else {
		iso, err := s.ResolveISO(ctx, s.Pool, r.InstallISOID)
		if err != nil {
			return Spec{}, err
		}
		if r.GuestOS == "" {
			r.GuestOS = iso.OS
		}
		if iso.OS != "" && r.GuestOS != iso.OS {
			return Spec{}, bad("ISO %s is a %s installer, not %s", r.InstallISOID, iso.OS, r.GuestOS)
		}
		if r.DriverISOID != "" {
			if r.DriverISOID == r.InstallISOID {
				return Spec{}, bad("driver_iso_id must differ from install_iso_id")
			}
			if _, err := s.ResolveISO(ctx, s.Pool, r.DriverISOID); err != nil {
				return Spec{}, err
			}
		}
	}
	spec, err := s.resolveSpec(r)
	if err != nil {
		return Spec{}, err
	}
	disk := limits.RootDiskGiB
	if r.RootDiskGiB == 0 {
		r.RootDiskGiB = disk.Default
	}
	if r.RootDiskGiB < disk.Min || r.RootDiskGiB > disk.Max {
		return Spec{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "root_disk_gib must be between %d and %d", disk.Min, disk.Max)
	}
	if len(r.UserData) > maxUserData {
		return Spec{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "user_data must be at most %d bytes", maxUserData)
	}
	if r.ClientToken != "" && !clientToken.MatchString(r.ClientToken) {
		return Spec{}, refuse(http.StatusBadRequest, "InvalidParameterValue", "client_token must be 1-64 printable ASCII characters")
	}
	if err := validateTags(r.Tags); err != nil {
		return Spec{}, err
	}
	return spec, nil
}

// validateTags applies EC2's tag rules, to instances and volumes alike.
func validateTags(tags map[string]string) error {
	if len(tags) > 20 {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", "at most 20 tags are allowed")
	}
	for key, value := range tags {
		if key == "" || utf8.RuneCountInString(key) > 128 || utf8.RuneCountInString(value) > 256 || strings.HasPrefix(key, "shakecloud:") {
			return refuse(http.StatusBadRequest, "InvalidParameterValue", "tag keys are 1-128 characters, values at most 256, and shakecloud: is reserved")
		}
	}
	return nil
}

// requestHash fingerprints everything but the client token, so a retry with
// the same token and different parameters is caught.
func requestHash(r RunRequest) []byte {
	r.ClientToken = ""
	encoded, _ := json.Marshal(r)
	sum := sha256.Sum256(encoded)
	return sum[:]
}

func newInstanceID() string {
	b := make([]byte, 9)
	rand.Read(b)
	return "i-" + hex.EncodeToString(b)[:17]
}

// Run admits a launch. It returns the instance and whether this call created
// it; a retried request with the same client token gets the original back.
// audit runs inside the transaction that records the instance.
func (s *Service) Run(ctx context.Context, accountID string, r RunRequest, audit func(pgx.Tx, db.Instance) error) (db.Instance, bool, error) {
	// Read once: an administrator changing a limit while this launch is being
	// admitted may land either side of it, which is no worse than the request
	// arriving a moment earlier.
	limits, _, err := s.EffectiveLimits(ctx, s.Pool)
	if err != nil {
		return db.Instance{}, false, err
	}
	spec, err := s.validate(ctx, &r, limits)
	if err != nil {
		return db.Instance{}, false, err
	}
	hash := requestHash(r)
	if r.ClientToken != "" {
		existing, err := db.InstanceByClientToken(ctx, s.Pool, accountID, r.ClientToken)
		if err == nil {
			return s.idempotent(existing, hash)
		}
		if !errors.Is(err, db.ErrNotFound) {
			return db.Instance{}, false, err
		}
	}

	// Resolved now and stored with the instance, so deleting the key pair in the
	// seconds before the worker builds the seed image cannot produce a VM with
	// no way into it.
	keyPublicKey := ""
	if r.KeyName != "" {
		pair, err := db.GetKeyPair(ctx, s.Pool, accountID, r.KeyName)
		if errors.Is(err, db.ErrNotFound) {
			return db.Instance{}, false, refuse(http.StatusBadRequest, "InvalidKeyPair.NotFound",
				"you have no key called %q; see GET /v1/key-pairs", r.KeyName)
		}
		if err != nil {
			return db.Instance{}, false, err
		}
		keyPublicKey = pair.PublicKey
	}

	// What only the host knows. It is a snapshot either way; the memory budget
	// checked under the lock below is what stops two launches racing past it.
	if err := s.checkHost(ctx, spec, spec.MemoryMiB, limits); err != nil {
		return db.Instance{}, false, err
	}
	visible, err := s.PVE.ListVMs(ctx)
	if err != nil {
		return db.Instance{}, false, s.unavailable(err)
	}

	var instance db.Instance
	created := false
	err = pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if err := db.LockCapacity(ctx, tx); err != nil {
			return err
		}
		if r.ClientToken != "" {
			existing, err := db.InstanceByClientToken(ctx, tx, accountID, r.ClientToken)
			if err == nil {
				instance = existing
				return nil
			}
			if !errors.Is(err, db.ErrNotFound) {
				return err
			}
		}
		if err := s.checkQuota(ctx, tx, accountID, spec, r.RootDiskGiB, limits, nil); err != nil {
			return err
		}
		groupIDs, err := s.resolveGroups(ctx, tx, accountID, r.SecurityGroupIDs)
		if err != nil {
			return err
		}
		vmid, err := db.AllocateVMID(ctx, tx, s.Site.VMIDFrom, s.Site.VMIDTo, s.skipVMIDs(visible))
		if errors.Is(err, db.ErrNoVMID) {
			return refuse(http.StatusServiceUnavailable, "InsufficientInstanceCapacity", "no VMID is free in %d-%d", s.Site.VMIDFrom, s.Site.VMIDTo)
		}
		if err != nil {
			return err
		}
		instance, err = db.InsertInstance(ctx, tx, db.Instance{
			ID: newInstanceID(), AccountID: accountID, ClientToken: r.ClientToken, RequestSHA256: hash,
			Name: r.Tags["Name"], ImageID: r.ImageID, GuestOS: r.GuestOS,
			InstallISOID: r.InstallISOID, DriverISOID: r.DriverISOID, InstanceType: spec.TypeName,
			CPUCores: spec.CPUCores, MemoryMiB: spec.MemoryMiB, MemoryMinMiB: spec.MemoryMinMiB, Ballooning: spec.Ballooning,
			RootDiskGiB: r.RootDiskGiB, UserData: r.UserData,
			KeyName: r.KeyName, KeyPublicKey: keyPublicKey, Tags: r.Tags,
			VMID: &vmid, MACAddress: seed.NewMACAddress(),
		})
		if err != nil {
			return err
		}
		// The launch writes the firewall these groups make before the first boot.
		if err := db.SetInstanceGroups(ctx, tx, instance.ID, groupIDs); err != nil {
			return err
		}
		if instance, err = db.GetInstance(ctx, tx, instance.ID); err != nil {
			return err
		}
		created = true
		if audit != nil {
			return audit(tx, instance)
		}
		return nil
	})
	if err != nil {
		return db.Instance{}, false, err
	}
	if !created {
		return s.idempotent(instance, hash)
	}
	s.Wake()
	return instance, true, nil
}

func (s *Service) idempotent(existing db.Instance, hash []byte) (db.Instance, bool, error) {
	if !bytes.Equal(existing.RequestSHA256, hash) {
		return db.Instance{}, false, refuse(http.StatusConflict, "IdempotentParameterMismatch",
			"client_token was already used for a request with different parameters (instance %s)", existing.ID)
	}
	return existing, false, nil
}

func (s *Service) skipVMIDs(visible []proxmox.VM) []int {
	skip := append([]int{s.Site.VolumeHolderVMID}, s.Site.ProbeVMIDs...)
	for _, vm := range visible {
		skip = append(skip, vm.VMID)
	}
	return skip
}

// checkQuota enforces the account's share and the cloud's memory budget. A
// limit of 0 means unlimited, which is how an administrator turns one off.
//
// replacing is the instance whose size is being changed, whose current
// resources are therefore not counted against the new ones; nil for a launch.
func (s *Service) checkQuota(ctx context.Context, tx pgx.Tx, accountID string, spec Spec, rootDisk int, limits site.Limits, replacing *db.Instance) error {
	usage, err := db.AccountUsage(ctx, tx, accountID)
	if err != nil {
		return err
	}
	added := 1
	if replacing != nil {
		added = 0
		usage.VCPUs -= replacing.CPUCores
		usage.MemoryMiB -= replacing.MemoryMiB
		usage.RootDiskGiB -= replacing.RootDiskGiB
	}
	quota := limits.AccountQuota
	switch {
	case quota.Instances > 0 && usage.Instances+added > quota.Instances:
		return refuse(http.StatusConflict, "InstanceLimitExceeded", "an account may hold %d instances (stopped ones count)", quota.Instances)
	case quota.VCPUs > 0 && usage.VCPUs+spec.CPUCores > quota.VCPUs:
		return refuse(http.StatusConflict, "VcpuLimitExceeded", "an account may hold %d vCPUs; %d are in use", quota.VCPUs, usage.VCPUs)
	case quota.MemoryMiB > 0 && usage.MemoryMiB+spec.MemoryMiB > quota.MemoryMiB:
		return refuse(http.StatusConflict, "InstanceLimitExceeded", "an account may hold %d MiB of memory; %d are in use", quota.MemoryMiB, usage.MemoryMiB)
	case quota.RootDiskGiB > 0 && usage.RootDiskGiB+rootDisk > quota.RootDiskGiB:
		return refuse(http.StatusConflict, "VolumeLimitExceeded", "an account may hold %d GiB of root disks; %d are in use", quota.RootDiskGiB, usage.RootDiskGiB)
	}
	live, err := db.LiveMemoryMiB(ctx, tx)
	if err != nil {
		return err
	}
	if replacing != nil {
		live -= replacing.MemoryMiB
	}
	if budget := limits.Capacity.MemoryBudgetMiB; budget > 0 && live+spec.MemoryMiB > budget {
		return refuse(http.StatusServiceUnavailable, "InsufficientInstanceCapacity",
			"the cloud's memory budget of %d MiB is used up (%d MiB allotted)", budget, live)
	}
	return nil
}

// checkHost is the part that looks at the machine rather than at policy. The
// memory check is never skipped: whatever the limits say, memory that is not
// there cannot be handed out. A disk threshold of 0 turns that check off.
//
// memoryNeededMiB is what this request would add, which for a resize is only
// the increase.
func (s *Service) checkHost(ctx context.Context, spec Spec, memoryNeededMiB int, limits site.Limits) error {
	capacity := limits.Capacity
	status, err := s.PVE.NodeStatus(ctx)
	if err != nil {
		return s.unavailable(err)
	}
	// A guest with more vCPUs than the host has threads is a configuration the
	// node can never satisfy, so it is refused as a bad request rather than as
	// a lack of capacity.
	if threads := status.CPUInfo.CPUs; threads > 0 && spec.CPUCores > threads {
		return refuse(http.StatusBadRequest, "InvalidParameterValue",
			"vcpus is %d but the node has %d threads", spec.CPUCores, threads)
	}
	if status.Memory.Available-int64(memoryNeededMiB)<<20 < int64(capacity.NodeMemoryReserveMiB)<<20 {
		return refuse(http.StatusServiceUnavailable, "InsufficientInstanceCapacity",
			"the host has %d MiB of memory available and %d MiB must stay free, so %d MiB cannot be allotted",
			status.Memory.Available>>20, capacity.NodeMemoryReserveMiB, memoryNeededMiB)
	}
	if err := s.checkDiskPool(ctx, limits); err != nil {
		return err
	}
	images, err := s.PVE.StorageStatus(ctx, s.Site.Storage.Images)
	if err != nil {
		return s.unavailable(err)
	}
	if images.Avail < int64(capacity.ImageStoreMinFreeMiB)<<20 {
		return refuse(http.StatusServiceUnavailable, "InsufficientInstanceCapacity", "the image store is nearly full")
	}
	return nil
}

// checkDiskPool refuses new disk space once the thin pool is used past the
// threshold: past it, guests see free space that writes can no longer get.
func (s *Service) checkDiskPool(ctx context.Context, limits site.Limits) error {
	threshold := limits.Capacity.VMDiskMaxUsedPercent
	disks, err := s.PVE.StorageStatus(ctx, s.Site.Storage.VMDisks)
	if err != nil {
		return s.unavailable(err)
	}
	if threshold > 0 && disks.Total > 0 && disks.Used*100 >= int64(threshold)*disks.Total {
		return refuse(http.StatusServiceUnavailable, "InsufficientInstanceCapacity", "the disk pool is over %d%% used", threshold)
	}
	return nil
}

func (s *Service) unavailable(err error) error {
	s.Log.Error("hypervisor unreachable", "err", err)
	return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "the hypervisor could not be reached; try again")
}

// Request records a user's terminate, start, stop or reboot. authorize decides
// whether the caller may act on the instance; an instance they may not touch
// answers exactly like one that does not exist.
func (s *Service) Request(ctx context.Context, id, action string, authorize func(db.Instance) bool, audit func(pgx.Tx, db.Instance) error) (db.Instance, error) {
	var result db.Instance
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		instance, err := db.LockInstance(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) || (err == nil && !authorize(instance)) {
			return refuse(http.StatusNotFound, "InvalidInstanceID.NotFound", "instance %s does not exist", id)
		}
		if err != nil {
			return err
		}
		result = instance
		busy := instance.PendingAction != ""
		incorrect := refuse(http.StatusConflict, "IncorrectInstanceState", "instance %s is %s", id, describeState(instance))
		switch action {
		case db.ActionTerminate:
			if instance.State == db.StateTerminated || instance.PendingAction == db.ActionTerminate {
				break
			}
			result, err = db.SetAction(ctx, tx, id, db.StateShuttingDown, db.ActionTerminate)
		case db.ActionStop:
			if (instance.State == db.StateStopped && !busy) || instance.PendingAction == db.ActionStop {
				break
			}
			if instance.State != db.StateRunning || busy {
				return incorrect
			}
			result, err = db.SetAction(ctx, tx, id, db.StateStopping, db.ActionStop)
		case db.ActionStart:
			if (instance.State == db.StateRunning && !busy) || instance.PendingAction == db.ActionStart {
				break
			}
			if instance.State != db.StateStopped || busy {
				return incorrect
			}
			result, err = db.SetAction(ctx, tx, id, db.StatePending, db.ActionStart)
		case db.ActionReboot:
			if instance.State != db.StateRunning || busy {
				return incorrect
			}
			result, err = db.SetAction(ctx, tx, id, db.StateRunning, db.ActionReboot)
		default:
			return fmt.Errorf("unknown action %q", action)
		}
		if err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, result)
		}
		return nil
	})
	if err == nil {
		s.Wake()
	}
	return result, err
}

func describeState(i db.Instance) string {
	if i.PendingAction != "" {
		return i.State + " (" + i.PendingAction + " in progress)"
	}
	return i.State
}
