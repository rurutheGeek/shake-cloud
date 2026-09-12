package db

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

// Instance states follow EC2's lifecycle.
const (
	StatePending      = "pending"
	StateRunning      = "running"
	StateStopping     = "stopping"
	StateStopped      = "stopped"
	StateShuttingDown = "shutting-down"
	StateTerminated   = "terminated"
)

// Actions the worker carries out.
const (
	ActionLaunch    = "launch"
	ActionStart     = "start"
	ActionStop      = "stop"
	ActionReboot    = "reboot"
	ActionTerminate = "terminate"
)

type Instance struct {
	ID        string
	AccountID string
	// OwnerUsername comes from the account row, so a listing can say whose
	// instance this is without a second query.
	OwnerUsername string
	ClientToken   string
	RequestSHA256 []byte
	Name          string
	ImageID       string
	// GuestOS is "windows" for a Windows guest and "" or "linux" otherwise.
	// It decides the virtual hardware the worker creates.
	GuestOS string
	// InstallISOID and DriverISOID are set for an instance that installs
	// itself from ISO media instead of launching from an image. The driver ISO
	// (the virtio-win disc) is optional.
	InstallISOID string
	DriverISOID  string
	// InstanceType is empty when the size was given as explicit numbers rather
	// than a named preset.
	InstanceType string
	CPUCores     int
	MemoryMiB    int
	// MemoryMinMiB is the balloon floor, and 0 when Ballooning is false.
	MemoryMinMiB int
	Ballooning   bool
	RootDiskGiB  int
	UserData     string
	// KeyName and KeyPublicKey record the SSH key written into the seed image.
	// The text is kept so that deleting the key pair afterwards changes nothing
	// about an instance that already has it.
	KeyName       string
	KeyPublicKey  string
	Tags          map[string]string
	State         string
	PendingAction string
	StateReason   string
	LastError     string
	Attempts      int
	NextAttemptAt time.Time
	VMID          *int
	VMCreated     bool
	MACAddress    string
	IPAddress     string
	NetBoxIPID    *int
	SeedVolume    string
	LaunchTime    time.Time
	TerminatedAt  *time.Time
	UpdatedAt     time.Time
	// Adopted marks a VM that already existed and was registered into the
	// cloud, rather than one the API created. Its description carries no
	// instance ID, and it has no seed image or source image to account for.
	Adopted bool
	// FirewallGeneration moves whenever the instance's groups or their rules
	// change; FirewallApplied is the generation its VM firewall was last
	// written from. They differ while a change is on its way to Proxmox.
	FirewallGeneration int64
	FirewallApplied    int64
	FirewallLastError  string
}

const instanceColumns = `i.instance_id, i.account_id,
	coalesce((SELECT a.username FROM accounts a WHERE a.id = i.account_id), ''),
	coalesce(i.client_token, ''), i.request_sha256, i.name,
	i.image_id, i.guest_os, coalesce(i.install_iso_id, ''), coalesce(i.driver_iso_id, ''),
	i.instance_type, i.cpu_cores, i.memory_mib, i.memory_min_mib, i.ballooning, i.root_disk_gib,
	i.user_data, coalesce(i.key_name, ''), coalesce(i.key_public_key, ''), i.tags,
	i.state, coalesce(i.pending_action, ''), i.state_reason, i.last_error, i.attempts, i.next_attempt_at,
	i.vmid, i.vm_created, i.mac_address, coalesce(i.ip_address, ''), i.netbox_ip_id, coalesce(i.seed_volume, ''),
	i.launch_time, i.terminated_at, i.updated_at, i.adopted,
	i.firewall_generation, i.firewall_applied, i.firewall_last_error`

func scanInstance(row pgx.Row) (Instance, error) {
	var i Instance
	err := row.Scan(&i.ID, &i.AccountID, &i.OwnerUsername, &i.ClientToken, &i.RequestSHA256, &i.Name,
		&i.ImageID, &i.GuestOS, &i.InstallISOID, &i.DriverISOID,
		&i.InstanceType, &i.CPUCores, &i.MemoryMiB, &i.MemoryMinMiB, &i.Ballooning, &i.RootDiskGiB,
		&i.UserData, &i.KeyName, &i.KeyPublicKey, &i.Tags,
		&i.State, &i.PendingAction, &i.StateReason, &i.LastError, &i.Attempts, &i.NextAttemptAt,
		&i.VMID, &i.VMCreated, &i.MACAddress, &i.IPAddress, &i.NetBoxIPID, &i.SeedVolume,
		&i.LaunchTime, &i.TerminatedAt, &i.UpdatedAt, &i.Adopted,
		&i.FirewallGeneration, &i.FirewallApplied, &i.FirewallLastError)
	return i, noRows(err)
}

func collectInstances(rows pgx.Rows, err error) ([]Instance, error) {
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (Instance, error) { return scanInstance(row) })
}

// InsertInstance records a new instance as pending with a launch to carry out.
func InsertInstance(ctx context.Context, q Querier, i Instance) (Instance, error) {
	if i.Tags == nil {
		i.Tags = map[string]string{}
	}
	return scanInstance(q.QueryRow(ctx, `INSERT INTO instances AS i
		(instance_id, account_id, client_token, request_sha256, name, image_id, guest_os,
		 install_iso_id, driver_iso_id, instance_type,
		 cpu_cores, memory_mib, memory_min_mib, ballooning, root_disk_gib, user_data,
		 key_name, key_public_key, tags, state, pending_action, vmid, mac_address)
		VALUES ($1, $2, nullif($3::text, ''), $4, $5, $6, $7,
		        nullif($8::text, ''), nullif($9::text, ''), $10,
		        $11, $12, $13, $14, $15, $16,
		        nullif($17::text, ''), nullif($18::text, ''), $19, 'pending', 'launch', $20, $21)
		RETURNING `+instanceColumns,
		i.ID, i.AccountID, i.ClientToken, i.RequestSHA256, i.Name, i.ImageID, i.GuestOS,
		i.InstallISOID, i.DriverISOID, i.InstanceType,
		i.CPUCores, i.MemoryMiB, i.MemoryMinMiB, i.Ballooning, i.RootDiskGiB, i.UserData,
		i.KeyName, i.KeyPublicKey, i.Tags, i.VMID, i.MACAddress))
}

// InsertAdoptedInstance records a VM that already existed and was registered
// into the cloud. It has no launch to carry out, so it is recorded settled in
// the state Proxmox reports.
func InsertAdoptedInstance(ctx context.Context, q Querier, i Instance) (Instance, error) {
	if i.Tags == nil {
		i.Tags = map[string]string{}
	}
	return scanInstance(q.QueryRow(ctx, `INSERT INTO instances AS i
		(instance_id, account_id, name, image_id, instance_type,
		 cpu_cores, memory_mib, memory_min_mib, ballooning, root_disk_gib, user_data,
		 tags, state, pending_action, vmid, vm_created, mac_address, ip_address, adopted)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, '', $11, $12, NULL, $13, true, $14,
		        nullif($15::text, ''), true)
		RETURNING `+instanceColumns,
		i.ID, i.AccountID, i.Name, i.ImageID, i.InstanceType,
		i.CPUCores, i.MemoryMiB, i.MemoryMinMiB, i.Ballooning, i.RootDiskGiB,
		i.Tags, i.State, i.VMID, i.MACAddress, i.IPAddress))
}

func GetInstance(ctx context.Context, q Querier, id string) (Instance, error) {
	return scanInstance(q.QueryRow(ctx, `SELECT `+instanceColumns+` FROM instances i WHERE i.instance_id = $1`, id))
}

// LockInstance reads an instance and holds its row until the transaction ends.
func LockInstance(ctx context.Context, q Querier, id string) (Instance, error) {
	return scanInstance(q.QueryRow(ctx, `SELECT `+instanceColumns+` FROM instances i WHERE i.instance_id = $1 FOR UPDATE`, id))
}

func InstanceByClientToken(ctx context.Context, q Querier, accountID, token string) (Instance, error) {
	return scanInstance(q.QueryRow(ctx, `SELECT `+instanceColumns+` FROM instances i
		WHERE i.account_id = $1 AND i.client_token = $2`, accountID, token))
}

// LiveInstanceByVMID returns the instance holding a VMID, if any. The unique
// index only allows one non-terminated instance to hold a VMID; this reads it
// for a clear answer rather than a constraint violation.
func LiveInstanceByVMID(ctx context.Context, q Querier, vmid int) (Instance, error) {
	return scanInstance(q.QueryRow(ctx, `SELECT `+instanceColumns+` FROM instances i
		WHERE i.vmid = $1 AND i.state <> 'terminated'`, vmid))
}

// ListInstances returns an account's instances (every account's when
// accountID is empty), newest first. Terminated instances stay visible for an
// hour, as in EC2, so a caller can see how a launch ended.
func ListInstances(ctx context.Context, q Querier, accountID string) ([]Instance, error) {
	return collectInstances(q.Query(ctx, `SELECT `+instanceColumns+` FROM instances i
		WHERE ($1::text = '' OR i.account_id = $1)
		  AND (i.state <> 'terminated' OR i.terminated_at > now() - interval '1 hour')
		ORDER BY i.launch_time DESC, i.instance_id`, accountID))
}

// Usage is what an account's instances hold. Stopped instances count: starting
// them again takes the same resources back.
type Usage struct {
	Instances   int
	VCPUs       int
	MemoryMiB   int
	RootDiskGiB int
	// Volumes and VolumeGiB count every volume that is not deleted, attached
	// or not: a detached disk still takes its space.
	Volumes   int
	VolumeGiB int
}

// usageQuery sums one account's holdings, or every account's when $1 is empty.
const usageQuery = `SELECT
	(SELECT count(*) FROM instances WHERE ($1::text = '' OR account_id = $1) AND state <> 'terminated'),
	(SELECT coalesce(sum(cpu_cores), 0) FROM instances WHERE ($1::text = '' OR account_id = $1) AND state <> 'terminated'),
	(SELECT coalesce(sum(memory_mib), 0) FROM instances WHERE ($1::text = '' OR account_id = $1) AND state <> 'terminated'),
	(SELECT coalesce(sum(root_disk_gib), 0) FROM instances WHERE ($1::text = '' OR account_id = $1) AND state <> 'terminated'),
	(SELECT count(*) FROM volumes WHERE ($1::text = '' OR account_id = $1) AND state <> 'deleted'),
	(SELECT coalesce(sum(size_gib), 0) FROM volumes WHERE ($1::text = '' OR account_id = $1) AND state <> 'deleted')`

func scanUsage(row pgx.Row) (Usage, error) {
	var u Usage
	err := row.Scan(&u.Instances, &u.VCPUs, &u.MemoryMiB, &u.RootDiskGiB, &u.Volumes, &u.VolumeGiB)
	return u, err
}

func AccountUsage(ctx context.Context, q Querier, accountID string) (Usage, error) {
	return scanUsage(q.QueryRow(ctx, usageQuery, accountID))
}

// PerAccountUsage names the account a Usage belongs to, for the capacity page.
// The name keeps it apart from AccountUsage, which reads one account's own.
type PerAccountUsage struct {
	AccountID string
	Username  string
	Usage
}

// UsageByAccount is every account that holds something, largest first. Only
// admins see it, so it is not part of the per-account path.
func UsageByAccount(ctx context.Context, q Querier) ([]PerAccountUsage, error) {
	rows, err := q.Query(ctx, `SELECT a.id, a.username,
			coalesce(i.instances, 0), coalesce(i.vcpus, 0), coalesce(i.memory_mib, 0), coalesce(i.root_disk_gib, 0),
			coalesce(v.volumes, 0), coalesce(v.volume_gib, 0)
		FROM accounts a
		LEFT JOIN (SELECT account_id, count(*) AS instances, sum(cpu_cores) AS vcpus,
				sum(memory_mib) AS memory_mib, sum(root_disk_gib) AS root_disk_gib
			FROM instances WHERE state <> 'terminated' GROUP BY account_id) i ON i.account_id = a.id
		LEFT JOIN (SELECT account_id, count(*) AS volumes, sum(size_gib) AS volume_gib
			FROM volumes WHERE state <> 'deleted' GROUP BY account_id) v ON v.account_id = a.id
		WHERE i.account_id IS NOT NULL OR v.account_id IS NOT NULL
		ORDER BY coalesce(i.memory_mib, 0) DESC, coalesce(v.volume_gib, 0) DESC, a.id`)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (PerAccountUsage, error) {
		var u PerAccountUsage
		return u, row.Scan(&u.AccountID, &u.Username, &u.Instances, &u.VCPUs, &u.MemoryMiB, &u.RootDiskGiB, &u.Volumes, &u.VolumeGiB)
	})
}

// CloudUsage is what every account together holds.
func CloudUsage(ctx context.Context, q Querier) (Usage, error) {
	return scanUsage(q.QueryRow(ctx, usageQuery, ""))
}

// LiveMemoryMiB sums memory_mib, the ceiling, over every account.
func LiveMemoryMiB(ctx context.Context, q Querier) (int, error) {
	var total int
	err := q.QueryRow(ctx, `SELECT coalesce(sum(memory_mib), 0) FROM instances WHERE state <> 'terminated'`).Scan(&total)
	return total, err
}

// ErrNoVMID means every VMID in the range is taken or skipped.
var ErrNoVMID = errors.New("no free VMID")

// AllocateVMID picks the lowest VMID that no live instance holds, that is not
// quarantined and that is not in skip. Call it inside a transaction holding the
// capacity lock so two launches cannot pick the same number.
func AllocateVMID(ctx context.Context, q Querier, from, to int, skip []int) (int, error) {
	if skip == nil {
		skip = []int{}
	}
	var vmid int
	err := q.QueryRow(ctx, `SELECT candidate FROM generate_series($1::int, $2::int) AS candidate
		WHERE candidate <> ALL($3::int[])
		  AND NOT EXISTS (SELECT 1 FROM instances WHERE vmid = candidate AND state <> 'terminated')
		  AND NOT EXISTS (SELECT 1 FROM vmid_quarantine WHERE vmid = candidate)
		ORDER BY candidate LIMIT 1`, from, to, skip).Scan(&vmid)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, ErrNoVMID
	}
	return vmid, err
}

func QuarantineVMID(ctx context.Context, q Querier, vmid int, reason string) error {
	_, err := q.Exec(ctx, `INSERT INTO vmid_quarantine (vmid, reason) VALUES ($1, $2) ON CONFLICT (vmid) DO NOTHING`, vmid, reason)
	return err
}

// LockCapacity serialises launches, so quota and budget checks cannot both pass
// for two requests that together exceed them.
func LockCapacity(ctx context.Context, q Querier) error {
	_, err := q.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext('shakecloud.capacity'))`)
	return err
}

// ClaimWork leases the next instance with work due. It returns ErrNotFound
// when there is none. A crashed worker's lease expires and the work is retried.
func ClaimWork(ctx context.Context, q Querier, lease time.Duration) (Instance, error) {
	return scanInstance(q.QueryRow(ctx, `UPDATE instances AS i SET lease_until = now() + make_interval(secs => $1)
		WHERE i.instance_id = (
			SELECT instance_id FROM instances
			WHERE pending_action IS NOT NULL AND next_attempt_at <= now()
			  AND (lease_until IS NULL OR lease_until < now())
			ORDER BY next_attempt_at, instance_id
			LIMIT 1 FOR UPDATE SKIP LOCKED)
		RETURNING `+instanceColumns, lease.Seconds()))
}

// Resources are backend objects the worker has created. They are written as
// soon as they exist, whatever else has happened to the instance meanwhile, so
// that a terminate knows what to remove.
type Resources struct {
	VMID       *int
	VMCreated  bool
	IPAddress  string
	NetBoxIPID *int
	SeedVolume string
}

func RecordResources(ctx context.Context, q Querier, id string, r Resources) error {
	_, err := q.Exec(ctx, `UPDATE instances SET vmid = $2, vm_created = $3, ip_address = nullif($4::text, ''),
		netbox_ip_id = $5, seed_volume = nullif($6::text, ''), updated_at = now()
		WHERE instance_id = $1`, id, r.VMID, r.VMCreated, r.IPAddress, r.NetBoxIPID, r.SeedVolume)
	return err
}

// FinishAction completes action and moves the instance to state. It does
// nothing when the action has been replaced meanwhile (a terminate requested
// during a launch), and reports whether it applied.
func FinishAction(ctx context.Context, q Querier, id, action, state, reason string) (bool, error) {
	terminated := state == StateTerminated
	tag, err := q.Exec(ctx, `UPDATE instances SET state = $3, pending_action = NULL, state_reason = $4,
		last_error = '', attempts = 0, lease_until = NULL, updated_at = now(),
		terminated_at = CASE WHEN $5 THEN now() ELSE terminated_at END
		WHERE instance_id = $1 AND pending_action = $2`, id, action, state, reason, terminated)
	if err != nil {
		return false, err
	}
	if tag.RowsAffected() == 0 {
		return false, ReleaseLease(ctx, q, id)
	}
	return true, nil
}

// RetryLater records a failed attempt and schedules the next one.
func RetryLater(ctx context.Context, q Querier, id, action, lastError string, next time.Time) error {
	_, err := q.Exec(ctx, `UPDATE instances SET attempts = attempts + 1, last_error = $3, next_attempt_at = $4,
		lease_until = NULL, updated_at = now()
		WHERE instance_id = $1 AND pending_action = $2`, id, action, lastError, next)
	if err != nil {
		return err
	}
	return ReleaseLease(ctx, q, id)
}

// AbandonLaunch turns a launch that cannot succeed into a terminate, so
// whatever it created is removed. EC2 does the same: the instance ends up
// terminated with a state reason.
func AbandonLaunch(ctx context.Context, q Querier, id, reason string) error {
	_, err := q.Exec(ctx, `UPDATE instances SET state = 'shutting-down', pending_action = 'terminate', state_reason = $2,
		attempts = 0, next_attempt_at = now(), lease_until = NULL, updated_at = now()
		WHERE instance_id = $1 AND pending_action = 'launch'`, id, reason)
	return err
}

// GiveUpAction stops retrying a power action and leaves the instance in state.
func GiveUpAction(ctx context.Context, q Querier, id, action, state, reason string) error {
	_, err := q.Exec(ctx, `UPDATE instances SET state = $3, pending_action = NULL, state_reason = $4,
		attempts = 0, lease_until = NULL, updated_at = now()
		WHERE instance_id = $1 AND pending_action = $2`, id, action, state, reason)
	return err
}

func ReleaseLease(ctx context.Context, q Querier, id string) error {
	_, err := q.Exec(ctx, `UPDATE instances SET lease_until = NULL WHERE instance_id = $1`, id)
	return err
}

// SetSpec changes an instance's size. The caller has already applied it to the
// hypervisor, so a failure here means the ledger is behind the VM, not ahead of
// it, which the reconciler and a retry can survive.
func SetSpec(ctx context.Context, q Querier, id string, cpuCores, memoryMiB, memoryMinMiB int, ballooning bool, rootDiskGiB int) (Instance, error) {
	return scanInstance(q.QueryRow(ctx, `UPDATE instances AS i
		SET cpu_cores = $2, memory_mib = $3, memory_min_mib = $4, ballooning = $5, root_disk_gib = $6,
		    instance_type = '', updated_at = now()
		WHERE i.instance_id = $1 RETURNING `+instanceColumns,
		id, cpuCores, memoryMiB, memoryMinMiB, ballooning, rootDiskGiB))
}

// SetAction records a requested transition. Callers hold the row via LockInstance.
func SetAction(ctx context.Context, q Querier, id, state, action string) (Instance, error) {
	return scanInstance(q.QueryRow(ctx, `UPDATE instances AS i SET state = $2, pending_action = $3,
		attempts = 0, last_error = '', next_attempt_at = now(), updated_at = now()
		WHERE i.instance_id = $1 RETURNING `+instanceColumns, id, state, action))
}

// SettledInstances are running or stopped with nothing pending: the ones whose
// state the reconciler may correct from what Proxmox reports.
func SettledInstances(ctx context.Context, q Querier) ([]Instance, error) {
	return collectInstances(q.Query(ctx, `SELECT `+instanceColumns+` FROM instances i
		WHERE i.state IN ('running', 'stopped') AND i.pending_action IS NULL
		  AND (i.lease_until IS NULL OR i.lease_until < now())`))
}

// ObserveState corrects a settled instance's state, unless something changed it first.
func ObserveState(ctx context.Context, q Querier, id, from, to, reason string) error {
	_, err := q.Exec(ctx, `UPDATE instances SET state = $3, state_reason = $4, updated_at = now()
		WHERE instance_id = $1 AND state = $2 AND pending_action IS NULL`, id, from, to, reason)
	return err
}

// NoteReason records why a settled instance looks wrong without changing its state.
func NoteReason(ctx context.Context, q Querier, id, reason string) error {
	_, err := q.Exec(ctx, `UPDATE instances SET state_reason = $2, updated_at = now()
		WHERE instance_id = $1 AND pending_action IS NULL AND state_reason <> $2`, id, reason)
	return err
}
