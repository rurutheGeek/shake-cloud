package compute

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"net/http"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/workload"
)

// Services are always-on containers: one Deployment that never scales to
// zero, with an optional disk, secrets and a LAN address. The cloud API keeps
// the account that owns each one and the settings to rebuild it from.

const (
	maxServicesPerAccount = 10
	defaultServiceMemory  = 128
	minServiceMemory      = 32
	maxServiceMemory      = 512
	maxServiceDiskGiB     = 32
	maxServiceEnv         = 50
	maxServiceSecrets     = 20
)

var (
	// An environment variable name, as POSIX shells accept it.
	envName   = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]{0,127}$`)
	mountPath = regexp.MustCompile(`^/[A-Za-z0-9._/-]*$`)
)

// WorkloadStore is the Kubernetes API for container services as the service uses it.
type WorkloadStore interface {
	Apply(ctx context.Context, spec workload.Spec) error
	Get(ctx context.Context, namespace, name string) (workload.State, error)
	Secrets(ctx context.Context, namespace, name string) (map[string]string, error)
	Delete(ctx context.Context, namespace, name string) error
}

// ServiceStatus is a service with the live state of its Deployment.
type ServiceStatus struct {
	Service db.Service
	Ready   bool
	URL     string
}

// ServiceRequest is what a create asks for.
type ServiceRequest struct {
	Name      string
	Image     string
	Port      int
	MemoryMiB int
	Env       map[string]string
	Secrets   map[string]string
	DiskGiB   int
	MountPath string
}

// ServiceChange is what a modify asks for; nil fields stay as they are.
type ServiceChange struct {
	Image     *string
	MemoryMiB *int
	Env       map[string]string
	Secrets   map[string]string
	SetEnv    bool
	SetSecret bool
}

func serviceNotFound(id string) error {
	return refuse(http.StatusNotFound, "NoSuchService", "service %s does not exist", id)
}

func (s *Service) serviceReady() error {
	if s.Workloads == nil {
		return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes is not configured on this deployment")
	}
	return nil
}

func newServiceID() string {
	b := make([]byte, 9)
	_, _ = rand.Read(b)
	return "svc-" + hex.EncodeToString(b)[:17]
}

func badService(format string, args ...any) error {
	return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
}

func checkImage(image string) error {
	switch {
	case image == "":
		return badService("an image is required")
	case len(image) > maxImageLength:
		return badService("an image reference is at most %d characters", maxImageLength)
	}
	return nil
}

func checkMemory(memory int) error {
	if memory < minServiceMemory || memory > maxServiceMemory {
		return badService("memory_mib is %d-%d", minServiceMemory, maxServiceMemory)
	}
	return nil
}

func checkEnv(env, secrets map[string]string) error {
	if len(env) > maxServiceEnv {
		return badService("a service has at most %d environment variables", maxServiceEnv)
	}
	if len(secrets) > maxServiceSecrets {
		return badService("a service has at most %d secrets", maxServiceSecrets)
	}
	for name := range env {
		if !envName.MatchString(name) {
			return badService("%q is not an environment variable name", name)
		}
		if _, clash := secrets[name]; clash {
			return badService("%s is both an environment variable and a secret", name)
		}
	}
	for name := range secrets {
		if !envName.MatchString(name) {
			return badService("%q is not an environment variable name", name)
		}
	}
	return nil
}

func secretNames(secrets map[string]string) []string {
	names := make([]string, 0, len(secrets))
	for name := range secrets {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func (s *Service) workloadSpec(record db.Service, secrets map[string]string) workload.Spec {
	return workload.Spec{
		Name: record.ID, Namespace: record.Namespace, Image: record.Image,
		Port: record.Port, MemoryMiB: record.MemoryMiB, Env: record.Env, Secrets: secrets,
		DiskGiB: record.DiskGiB, MountPath: record.MountPath,
		Labels: map[string]string{
			"shakecloud.io/account": record.AccountID,
			"shakecloud.io/service": record.ID,
		},
	}
}

// CreateService makes one container service. Repeating with the same name
// returns the existing one unchanged.
func (s *Service) CreateService(ctx context.Context, accountID string, request ServiceRequest, audit func(pgx.Tx, db.Service) error) (db.Service, bool, error) {
	request.Name = strings.TrimSpace(request.Name)
	request.Image = strings.TrimSpace(request.Image)
	if request.MemoryMiB == 0 {
		request.MemoryMiB = defaultServiceMemory
	}
	if !functionName.MatchString(request.Name) {
		return db.Service{}, false, badService("a service name is 2-30 characters of lower case letters, digits and hyphens, and starts with a letter")
	}
	if err := checkImage(request.Image); err != nil {
		return db.Service{}, false, err
	}
	if request.Port < 0 || request.Port > 65535 {
		return db.Service{}, false, badService("port is 1-65535")
	}
	if err := checkMemory(request.MemoryMiB); err != nil {
		return db.Service{}, false, err
	}
	if err := checkEnv(request.Env, request.Secrets); err != nil {
		return db.Service{}, false, err
	}
	switch {
	case request.DiskGiB < 0 || request.DiskGiB > maxServiceDiskGiB:
		return db.Service{}, false, badService("disk.size_gib is 1-%d", maxServiceDiskGiB)
	case request.DiskGiB > 0 && (!mountPath.MatchString(request.MountPath) || request.MountPath == "/" || request.MountPath == "/tmp"):
		return db.Service{}, false, badService("disk.mount_path is an absolute path other than / and /tmp")
	case request.DiskGiB == 0 && request.MountPath != "":
		return db.Service{}, false, badService("disk.mount_path needs disk.size_gib")
	}
	if err := s.serviceReady(); err != nil {
		return db.Service{}, false, err
	}

	var service db.Service
	created := false
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if existing, err := db.GetServiceByName(ctx, tx, accountID, request.Name); err == nil {
			service = existing
			return nil
		} else if !errors.Is(err, db.ErrNotFound) {
			return err
		}
		count, err := db.CountServices(ctx, tx, accountID)
		if err != nil {
			return err
		}
		if count >= maxServicesPerAccount {
			return refuse(http.StatusConflict, "ServiceLimitExceeded", "an account may hold %d services", maxServicesPerAccount)
		}
		service, err = db.InsertService(ctx, tx, db.Service{
			ID: newServiceID(), AccountID: accountID, Name: request.Name, Namespace: s.ServiceNamespace,
			Image: request.Image, Port: request.Port, MemoryMiB: request.MemoryMiB, Env: request.Env,
			SecretNames: secretNames(request.Secrets), DiskGiB: request.DiskGiB, MountPath: request.MountPath,
		})
		if errors.Is(err, db.ErrDuplicate) {
			return refuse(http.StatusConflict, "ResourceAlreadyExists", "service %s already exists", request.Name)
		}
		if err != nil {
			return err
		}
		if err := s.Workloads.Apply(ctx, s.workloadSpec(service, request.Secrets)); err != nil {
			// Do not leak objects the ledger does not know about.
			_ = s.Workloads.Delete(ctx, service.Namespace, service.ID)
			return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not create the service: %v", err)
		}
		created = true
		if audit != nil {
			return audit(tx, service)
		}
		return nil
	})
	return service, created, err
}

// ModifyService changes the image, memory, environment or secrets and
// replaces the pod.
func (s *Service) ModifyService(ctx context.Context, id string, change ServiceChange, audit func(pgx.Tx, db.Service) error) (db.Service, error) {
	if err := s.serviceReady(); err != nil {
		return db.Service{}, err
	}
	var service db.Service
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		record, err := db.GetServiceForUpdate(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) {
			return serviceNotFound(id)
		}
		if err != nil {
			return err
		}
		if change.Image != nil {
			record.Image = strings.TrimSpace(*change.Image)
			if err := checkImage(record.Image); err != nil {
				return err
			}
		}
		if change.MemoryMiB != nil {
			if err := checkMemory(*change.MemoryMiB); err != nil {
				return err
			}
			record.MemoryMiB = *change.MemoryMiB
		}
		if change.SetEnv {
			record.Env = change.Env
			if record.Env == nil {
				record.Env = map[string]string{}
			}
		}
		secrets := change.Secrets
		if !change.SetSecret {
			if secrets, err = s.Workloads.Secrets(ctx, record.Namespace, record.ID); err != nil {
				return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not read the secrets: %v", err)
			}
		}
		if err := checkEnv(record.Env, secrets); err != nil {
			return err
		}
		record.SecretNames = secretNames(secrets)
		if service, err = db.UpdateService(ctx, tx, record); err != nil {
			return err
		}
		if err := s.Workloads.Apply(ctx, s.workloadSpec(service, secrets)); err != nil {
			return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not update the service: %v", err)
		}
		if audit != nil {
			return audit(tx, service)
		}
		return nil
	})
	return service, err
}

// ListServices returns an account's services (every account's when accountID
// is empty) with the live state.
func (s *Service) ListServices(ctx context.Context, accountID string) ([]ServiceStatus, error) {
	if err := s.serviceReady(); err != nil {
		return nil, err
	}
	records, err := db.ListServices(ctx, s.Pool, accountID)
	if err != nil {
		return nil, err
	}
	statuses := make([]ServiceStatus, 0, len(records))
	for _, record := range records {
		status, err := s.serviceStatus(ctx, record)
		if err != nil {
			return nil, err
		}
		statuses = append(statuses, status)
	}
	return statuses, nil
}

// GetService returns one service with its live state.
func (s *Service) GetService(ctx context.Context, id string) (ServiceStatus, error) {
	if err := s.serviceReady(); err != nil {
		return ServiceStatus{}, err
	}
	record, err := db.GetService(ctx, s.Pool, id)
	if errors.Is(err, db.ErrNotFound) {
		return ServiceStatus{}, serviceNotFound(id)
	}
	if err != nil {
		return ServiceStatus{}, err
	}
	return s.serviceStatus(ctx, record)
}

func (s *Service) serviceStatus(ctx context.Context, record db.Service) (ServiceStatus, error) {
	state, err := s.Workloads.Get(ctx, record.Namespace, record.ID)
	if err != nil {
		return ServiceStatus{}, refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not read the service: %v", err)
	}
	status := ServiceStatus{Service: record, Ready: state.Ready}
	if record.Port > 0 && state.Address != "" {
		status.URL = "http://" + state.Address + ":" + strconv.Itoa(record.Port)
	}
	return status, nil
}

// DeleteService removes the Kubernetes objects, the disk included, and the
// ledger row.
func (s *Service) DeleteService(ctx context.Context, id string, audit func(pgx.Tx, db.Service) error) error {
	if err := s.serviceReady(); err != nil {
		return err
	}
	return pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		record, err := db.GetServiceForUpdate(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) {
			return serviceNotFound(id)
		}
		if err != nil {
			return err
		}
		if err := s.Workloads.Delete(ctx, record.Namespace, record.ID); err != nil {
			return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not delete the service: %v", err)
		}
		if err := db.DeleteService(ctx, tx, id); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, record)
		}
		return nil
	})
}
