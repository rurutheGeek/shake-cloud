package compute

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"net/http"
	"regexp"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/knative"
)

// Functions are serverless HTTP services backed by Knative. The cloud API keeps
// the account that owns each one and talks to Kubernetes to create or remove
// the Knative Service. The calls themselves go straight to the function.

// A function name: 2-30 characters, lower case, starts with a letter.
var functionName = regexp.MustCompile(`^[a-z][a-z0-9-]{1,29}$`)

const (
	maxFunctionsPerAccount = 10
	maxImageLength         = 512
)

// FunctionStore is the Kubernetes API for Knative Services as the service uses it.
type FunctionStore interface {
	CreateService(ctx context.Context, spec knative.ServiceSpec) (knative.Service, error)
	GetService(ctx context.Context, namespace, name string) (knative.Service, error)
	ListServices(ctx context.Context, namespace, selector string) ([]knative.Service, error)
	DeleteService(ctx context.Context, namespace, name string) error
}

// FunctionStatus is a function with the live state of its Knative Service.
type FunctionStatus struct {
	Function db.Function
	URL      string
	Ready    bool
}

func functionNotFound(id string) error {
	return refuse(http.StatusNotFound, "NoSuchFunction", "function %s does not exist", id)
}

// functionReady refuses when Kubernetes is not configured on this deployment.
func (s *Service) functionReady() error {
	if s.Functions == nil {
		return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes is not configured on this deployment")
	}
	return nil
}

func newFunctionID() string {
	b := make([]byte, 9)
	_, _ = rand.Read(b)
	return "fn-" + hex.EncodeToString(b)[:17]
}

// CreateFunction makes one serverless function. Repeating with the same name
// returns the existing one.
func (s *Service) CreateFunction(ctx context.Context, accountID, name, image string, audit func(pgx.Tx, db.Function) error) (db.Function, bool, error) {
	bad := func(format string, args ...any) error {
		return refuse(http.StatusBadRequest, "InvalidParameterValue", format, args...)
	}
	name = strings.TrimSpace(name)
	image = strings.TrimSpace(image)
	switch {
	case !functionName.MatchString(name):
		return db.Function{}, false, bad("a function name is 2-30 characters of lower case letters, digits and hyphens, and starts with a letter")
	case image == "":
		return db.Function{}, false, bad("an image is required")
	case len(image) > maxImageLength:
		return db.Function{}, false, bad("an image reference is at most %d characters", maxImageLength)
	}
	if err := s.functionReady(); err != nil {
		return db.Function{}, false, err
	}

	var function db.Function
	created := false
	err := pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		if existing, err := db.GetFunctionByName(ctx, tx, accountID, name); err == nil {
			function = existing
			return nil
		} else if !errors.Is(err, db.ErrNotFound) {
			return err
		}
		count, err := db.CountFunctions(ctx, tx, accountID)
		if err != nil {
			return err
		}
		if count >= maxFunctionsPerAccount {
			return refuse(http.StatusConflict, "FunctionLimitExceeded", "an account may hold %d functions", maxFunctionsPerAccount)
		}
		id := newFunctionID()
		if _, err := s.Functions.CreateService(ctx, knative.ServiceSpec{
			Name:      id,
			Namespace: s.FunctionNamespace,
			Image:     image,
			Labels: map[string]string{
				"shakecloud.io/account":  accountID,
				"shakecloud.io/function": id,
			},
		}); err != nil {
			return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not create the service: %v", err)
		}
		function, err = db.InsertFunction(ctx, tx, id, accountID, name, s.FunctionNamespace, image)
		if err != nil {
			// Do not leak a service the ledger does not know about.
			_ = s.Functions.DeleteService(ctx, s.FunctionNamespace, id)
			if errors.Is(err, db.ErrDuplicate) {
				return refuse(http.StatusConflict, "ResourceAlreadyExists", "function %s already exists", name)
			}
			return err
		}
		created = true
		if audit != nil {
			return audit(tx, function)
		}
		return nil
	})
	return function, created, err
}

// ListFunctions returns an account's functions (every account's when accountID
// is empty) with the live service state.
func (s *Service) ListFunctions(ctx context.Context, accountID string) ([]FunctionStatus, error) {
	if err := s.functionReady(); err != nil {
		return nil, err
	}
	functions, err := db.ListFunctions(ctx, s.Pool, accountID)
	if err != nil {
		return nil, err
	}
	selector := ""
	if accountID != "" {
		selector = "shakecloud.io/account=" + accountID
	}
	services, err := s.Functions.ListServices(ctx, s.FunctionNamespace, selector)
	if err != nil {
		return nil, refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not list services: %v", err)
	}
	byName := make(map[string]knative.Service, len(services))
	for _, service := range services {
		byName[service.Name] = service
	}
	statuses := make([]FunctionStatus, 0, len(functions))
	for _, record := range functions {
		statuses = append(statuses, functionStatusOf(record, byName[record.ID]))
	}
	return statuses, nil
}

// GetFunction returns one function with its live state.
func (s *Service) GetFunction(ctx context.Context, id string) (FunctionStatus, error) {
	if err := s.functionReady(); err != nil {
		return FunctionStatus{}, err
	}
	record, err := db.GetFunction(ctx, s.Pool, id)
	if errors.Is(err, db.ErrNotFound) {
		return FunctionStatus{}, functionNotFound(id)
	}
	if err != nil {
		return FunctionStatus{}, err
	}
	service, err := s.Functions.GetService(ctx, record.Namespace, record.ID)
	if err != nil {
		return FunctionStatus{}, refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not read the service: %v", err)
	}
	return functionStatusOf(record, service), nil
}

// DeleteFunction removes the Knative Service and the ledger row.
func (s *Service) DeleteFunction(ctx context.Context, id string, audit func(pgx.Tx, db.Function) error) error {
	if err := s.functionReady(); err != nil {
		return err
	}
	return pgx.BeginFunc(ctx, s.Pool, func(tx pgx.Tx) error {
		record, err := db.GetFunction(ctx, tx, id)
		if errors.Is(err, db.ErrNotFound) {
			return functionNotFound(id)
		}
		if err != nil {
			return err
		}
		if err := s.Functions.DeleteService(ctx, record.Namespace, record.ID); err != nil {
			var apiErr *knative.Error
			if !errors.As(err, &apiErr) || !apiErr.NotFound() {
				return refuse(http.StatusServiceUnavailable, "ServiceUnavailable", "Kubernetes could not delete the service: %v", err)
			}
		}
		if err := db.DeleteFunction(ctx, tx, id); err != nil {
			return err
		}
		if audit != nil {
			return audit(tx, record)
		}
		return nil
	})
}

func functionStatusOf(record db.Function, service knative.Service) FunctionStatus {
	return FunctionStatus{Function: record, URL: service.URL, Ready: service.Ready}
}
