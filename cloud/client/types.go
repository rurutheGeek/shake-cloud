package client

import "time"

// The response and request shapes, field for field, from
// cloud/openapi/shakecloud.yaml. Omitting a field the API treats as optional
// uses the zero value; pointers are used where "not given" is meaningful.

type CallerIdentity struct {
	AccountID      string `json:"account_id"`
	Username       string `json:"username"`
	IsAdmin        bool   `json:"is_admin"`
	CredentialType string `json:"credential_type"`
	AccessKeyID    string `json:"access_key_id,omitempty"`
}

type Instance struct {
	InstanceID       string                  `json:"instance_id"`
	AccountID        string                  `json:"account_id"`
	OwnerUsername    string                  `json:"owner_username,omitempty"`
	ImageID          string                  `json:"image_id"`
	ImageName        string                  `json:"image_name,omitempty"`
	InstanceType     string                  `json:"instance_type,omitempty"`
	State            string                  `json:"state"`
	StateReason      string                  `json:"state_reason,omitempty"`
	PrivateIPAddress string                  `json:"private_ip_address,omitempty"`
	MACAddress       string                  `json:"mac_address"`
	VCPUs            int                     `json:"vcpus"`
	MemoryMiB        int                     `json:"memory_mib"`
	MemoryMinMiB     int                     `json:"memory_min_mib"`
	Ballooning       bool                    `json:"ballooning"`
	RootDiskGiB      int                     `json:"root_disk_gib"`
	KeyName          string                  `json:"key_name,omitempty"`
	Tags             map[string]string       `json:"tags,omitempty"`
	ClientToken      string                  `json:"client_token,omitempty"`
	LaunchTime       time.Time               `json:"launch_time"`
	TerminatedAt     *time.Time              `json:"terminated_at,omitempty"`
	SecurityGroups   []InstanceSecurityGroup `json:"security_groups"`
	FirewallState    string                  `json:"firewall_state"`
	Adopted          bool                    `json:"adopted,omitempty"`
}

// Name is the Name tag, which is also the guest hostname, or "".
func (i Instance) Name() string { return i.Tags["Name"] }

type InstanceSecurityGroup struct {
	GroupID   string `json:"group_id"`
	GroupName string `json:"group_name"`
}

type RunRequest struct {
	ImageID          string            `json:"image_id"`
	InstanceType     string            `json:"instance_type,omitempty"`
	KeyName          string            `json:"key_name,omitempty"`
	VCPUs            *int              `json:"vcpus,omitempty"`
	MemoryMiB        *int              `json:"memory_mib,omitempty"`
	MemoryMinMiB     *int              `json:"memory_min_mib,omitempty"`
	Ballooning       *bool             `json:"ballooning,omitempty"`
	RootDiskGiB      int               `json:"root_disk_gib,omitempty"`
	UserData         string            `json:"user_data,omitempty"`
	ClientToken      string            `json:"client_token,omitempty"`
	Tags             map[string]string `json:"tags,omitempty"`
	SecurityGroupIDs []string          `json:"security_group_ids,omitempty"`
}

type ModifyInstanceRequest struct {
	VCPUs        *int  `json:"vcpus,omitempty"`
	MemoryMiB    *int  `json:"memory_mib,omitempty"`
	MemoryMinMiB *int  `json:"memory_min_mib,omitempty"`
	Ballooning   *bool `json:"ballooning,omitempty"`
	RootDiskGiB  *int  `json:"root_disk_gib,omitempty"`
}

type AdoptRequest struct {
	VMID             int               `json:"vmid"`
	AccountID        string            `json:"account_id"`
	Name             string            `json:"name,omitempty"`
	PrivateIPAddress string            `json:"private_ip_address,omitempty"`
	RootDiskGiB      int               `json:"root_disk_gib,omitempty"`
	Tags             map[string]string `json:"tags,omitempty"`
	SecurityGroupIDs []string          `json:"security_group_ids,omitempty"`
}

type ConsoleSession struct {
	URL       string    `json:"url"`
	ExpiresAt time.Time `json:"expires_at"`
}

type Volume struct {
	VolumeID          string            `json:"volume_id"`
	AccountID         string            `json:"account_id"`
	OwnerUsername     string            `json:"owner_username,omitempty"`
	SizeGiB           int               `json:"size_gib"`
	State             string            `json:"state"`
	StateReason       string            `json:"state_reason,omitempty"`
	ModificationState string            `json:"modification_state,omitempty"`
	Serial            string            `json:"serial"`
	Tags              map[string]string `json:"tags,omitempty"`
	ClientToken       string            `json:"client_token,omitempty"`
	CreateTime        time.Time         `json:"create_time"`
	Attachment        *VolumeAttachment `json:"attachment,omitempty"`
}

type VolumeAttachment struct {
	InstanceID string `json:"instance_id"`
	Device     string `json:"device"`
	State      string `json:"state"`
	DevicePath string `json:"device_path,omitempty"`
}

type CreateVolumeRequest struct {
	SizeGiB     int               `json:"size_gib"`
	ClientToken string            `json:"client_token,omitempty"`
	Tags        map[string]string `json:"tags,omitempty"`
}

type AttachVolumeRequest struct {
	InstanceID string `json:"instance_id"`
	Device     string `json:"device,omitempty"`
}

type SecurityGroup struct {
	GroupID       string              `json:"group_id"`
	AccountID     string              `json:"account_id"`
	OwnerUsername string              `json:"owner_username,omitempty"`
	GroupName     string              `json:"group_name"`
	Description   string              `json:"description"`
	IsDefault     bool                `json:"is_default"`
	Ingress       []SecurityGroupRule `json:"ingress"`
	Egress        []SecurityGroupRule `json:"egress"`
	InstanceIDs   []string            `json:"instance_ids"`
	CreatedAt     time.Time           `json:"created_at"`
}

type SecurityGroupRule struct {
	RuleID      string `json:"rule_id"`
	Protocol    string `json:"protocol"`
	FromPort    *int   `json:"from_port,omitempty"`
	ToPort      *int   `json:"to_port,omitempty"`
	CIDR        string `json:"cidr"`
	Description string `json:"description,omitempty"`
}

type SecurityGroupRuleRequest struct {
	Protocol    string `json:"protocol"`
	FromPort    *int   `json:"from_port,omitempty"`
	ToPort      *int   `json:"to_port,omitempty"`
	CIDR        string `json:"cidr"`
	Description string `json:"description,omitempty"`
}

type CreateSecurityGroupRequest struct {
	GroupName   string `json:"group_name"`
	Description string `json:"description,omitempty"`
}

type Image struct {
	ImageID       string    `json:"image_id"`
	Name          string    `json:"name"`
	State         string    `json:"state"`
	Public        bool      `json:"public"`
	AccountID     string    `json:"account_id,omitempty"`
	OwnerUsername string    `json:"owner_username,omitempty"`
	Format        string    `json:"format,omitempty"`
	SizeMiB       int       `json:"size_mib,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
}

type KeyPair struct {
	KeyName     string    `json:"key_name"`
	Fingerprint string    `json:"fingerprint"`
	CreatedAt   time.Time `json:"created_at"`
}

type AccessKey struct {
	AccessKeyID  string     `json:"access_key_id"`
	Status       string     `json:"status"`
	Description  string     `json:"description"`
	CreateDate   time.Time  `json:"create_date"`
	ExpireDate   *time.Time `json:"expire_date,omitempty"`
	LastUsedDate *time.Time `json:"last_used_date,omitempty"`
}

type CreatedAccessKey struct {
	AccessKey       AccessKey `json:"access_key"`
	SecretAccessKey string    `json:"secret_access_key"`
}

type AuditEvent struct {
	EventID         string         `json:"event_id"`
	EventTime       time.Time      `json:"event_time"`
	EventName       string         `json:"event_name"`
	AccountID       string         `json:"account_id,omitempty"`
	AccessKeyID     string         `json:"access_key_id,omitempty"`
	CredentialType  string         `json:"credential_type"`
	SourceIPAddress string         `json:"source_ip_address"`
	UserAgent       string         `json:"user_agent"`
	RequestID       string         `json:"request_id"`
	ResourceID      string         `json:"resource_id,omitempty"`
	ErrorCode       string         `json:"error_code,omitempty"`
	Detail          map[string]any `json:"detail,omitempty"`
}

type InstanceType struct {
	InstanceType string `json:"instance_type"`
	VCPUs        int    `json:"vcpus"`
	MemoryMiB    int    `json:"memory_mib"`
	MemoryMinMiB int    `json:"memory_min_mib"`
}

type Usage struct {
	AccountID   string `json:"account_id,omitempty"`
	Username    string `json:"username,omitempty"`
	Instances   int    `json:"instances"`
	VCPUs       int    `json:"vcpus"`
	MemoryMiB   int    `json:"memory_mib"`
	RootDiskGiB int    `json:"root_disk_gib"`
	Volumes     int    `json:"volumes"`
	VolumeGiB   int    `json:"volume_gib"`
}

type Quota struct {
	Instances   int `json:"instances"`
	VCPUs       int `json:"vcpus"`
	MemoryMiB   int `json:"memory_mib"`
	RootDiskGiB int `json:"root_disk_gib"`
	Volumes     int `json:"volumes"`
	VolumeGiB   int `json:"volume_gib"`
}

type RootDiskLimit struct {
	Min     int `json:"min"`
	Default int `json:"default"`
	Max     int `json:"max"`
}

type VolumeSizeLimit struct {
	Min int `json:"min"`
	Max int `json:"max"`
}

type CapacityLimits struct {
	MaxImageGiB          int `json:"max_image_gib"`
	MemoryBudgetMiB      int `json:"memory_budget_mib"`
	NodeMemoryReserveMiB int `json:"node_memory_reserve_mib"`
	VMDiskMaxUsedPercent int `json:"vm_disk_max_used_percent"`
	ImageStoreMinFreeMiB int `json:"image_store_min_free_mib"`
}

type Limits struct {
	AccountQuota  Quota           `json:"account_quota"`
	RootDiskGiB   RootDiskLimit   `json:"root_disk_gib"`
	VolumeSizeGiB VolumeSizeLimit `json:"volume_size_gib"`
	Capacity      CapacityLimits  `json:"capacity"`
}

// LimitOverrides is whatever an administrator changed. Left as raw JSON, since
// every field is optional and only the API needs to reason about it.
type LimitOverrides map[string]any

type LimitsResponse struct {
	Limits    Limits         `json:"limits"`
	Defaults  Limits         `json:"defaults"`
	Overrides LimitOverrides `json:"overrides"`
	UpdatedAt *time.Time     `json:"updated_at,omitempty"`
	UpdatedBy string         `json:"updated_by,omitempty"`
}

type NodeStatus struct {
	Name               string  `json:"name"`
	CPUModel           string  `json:"cpu_model,omitempty"`
	CPUCores           int     `json:"cpu_cores"`
	CPUThreads         int     `json:"cpu_threads"`
	CPUUsagePercent    float64 `json:"cpu_usage_percent,omitempty"`
	MemoryTotalMiB     int     `json:"memory_total_mib"`
	MemoryUsedMiB      int     `json:"memory_used_mib"`
	MemoryAvailableMiB int     `json:"memory_available_mib"`
	KernelVersion      string  `json:"kernel_version,omitempty"`
	PVEVersion         string  `json:"pve_version,omitempty"`
	UptimeSeconds      int64   `json:"uptime_seconds,omitempty"`
}

type StorageStatus struct {
	Name           string  `json:"name"`
	Purpose        string  `json:"purpose"`
	TotalMiB       int     `json:"total_mib"`
	UsedMiB        int     `json:"used_mib"`
	AvailMiB       int     `json:"avail_mib"`
	UsedPercent    float64 `json:"used_percent"`
	MaxUsedPercent int     `json:"max_used_percent,omitempty"`
	MinFreeMiB     int     `json:"min_free_mib,omitempty"`
}

type Capacity struct {
	Node     NodeStatus      `json:"node"`
	Storage  []StorageStatus `json:"storage"`
	Cloud    Usage           `json:"cloud"`
	Account  Usage           `json:"account"`
	Limits   Limits          `json:"limits"`
	Accounts []Usage         `json:"accounts,omitempty"`
}
