package client

import (
	"context"
	"net/http"
	"net/url"
	"time"
)

// Container services: always-on Deployments. Secret values are sent, never
// returned; a service lists only their names.

type ServiceDisk struct {
	SizeGiB   int    `json:"size_gib"`
	MountPath string `json:"mount_path"`
}

type Service struct {
	ServiceID     string            `json:"service_id"`
	Name          string            `json:"name"`
	AccountID     string            `json:"account_id"`
	OwnerUsername string            `json:"owner_username,omitempty"`
	Image         string            `json:"image"`
	Port          int               `json:"port,omitempty"`
	MemoryMiB     int               `json:"memory_mib"`
	Env           map[string]string `json:"env"`
	SecretNames   []string          `json:"secret_names"`
	Disk          *ServiceDisk      `json:"disk,omitempty"`
	Status        string            `json:"status"`
	URL           string            `json:"url,omitempty"`
	CreatedAt     time.Time         `json:"created_at"`
}

type CreateServiceInput struct {
	Name      string            `json:"name"`
	Image     string            `json:"image"`
	Port      int               `json:"port,omitempty"`
	MemoryMiB int               `json:"memory_mib,omitempty"`
	Env       map[string]string `json:"env,omitempty"`
	Secrets   map[string]string `json:"secrets,omitempty"`
	Disk      *ServiceDisk      `json:"disk,omitempty"`
}

// ModifyServiceInput changes only the fields that are set. Env and Secrets
// replace the whole map; an empty, non-nil map clears it.
type ModifyServiceInput struct {
	Image     *string            `json:"image,omitempty"`
	MemoryMiB *int               `json:"memory_mib,omitempty"`
	Env       *map[string]string `json:"env,omitempty"`
	Secrets   *map[string]string `json:"secrets,omitempty"`
}

func (c *Client) DescribeServices(ctx context.Context) ([]Service, error) {
	var out struct {
		Services []Service `json:"services"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/services", nil, nil, &out)
	return out.Services, err
}

func (c *Client) CreateService(ctx context.Context, input CreateServiceInput) (Service, error) {
	var out struct {
		Service Service `json:"service"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/services", nil, input, &out)
	return out.Service, err
}

func (c *Client) DescribeService(ctx context.Context, id string) (Service, error) {
	var out struct {
		Service Service `json:"service"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/services/"+url.PathEscape(id), nil, nil, &out)
	return out.Service, err
}

func (c *Client) ModifyService(ctx context.Context, id string, input ModifyServiceInput) (Service, error) {
	var out struct {
		Service Service `json:"service"`
	}
	err := c.do(ctx, http.MethodPatch, "/v1/services/"+url.PathEscape(id), nil, input, &out)
	return out.Service, err
}

func (c *Client) DeleteService(ctx context.Context, id string) error {
	return c.do(ctx, http.MethodDelete, "/v1/services/"+url.PathEscape(id), nil, nil, nil)
}
