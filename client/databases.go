package client

import (
	"context"
	"net/http"
	"net/url"
	"time"
)

// Database appliances backed by CloudNativePG. The database's own traffic never
// passes through the cloud API; these calls manage the appliance and hand out
// its connection credentials.

type Database struct {
	DatabaseID     string    `json:"database_id"`
	Name           string    `json:"name"`
	AccountID      string    `json:"account_id"`
	OwnerUsername  string    `json:"owner_username,omitempty"`
	Engine         string    `json:"engine"`
	EngineVersion  string    `json:"engine_version"`
	StorageGiB     int       `json:"storage_gib"`
	Status         string    `json:"status"`
	Instances      int       `json:"instances"`
	ReadyInstances int       `json:"ready_instances"`
	Host           string    `json:"host"`
	Port           int       `json:"port"`
	CreatedAt      time.Time `json:"created_at"`
}

type DatabaseCredentials struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Host     string `json:"host"`
	Port     string `json:"port"`
	Database string `json:"database"`
}

func (c *Client) DescribeDatabases(ctx context.Context) ([]Database, error) {
	var out struct {
		Databases []Database `json:"databases"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/databases", nil, nil, &out)
	return out.Databases, err
}

func (c *Client) CreateDatabase(ctx context.Context, name string, storageGiB int) (Database, error) {
	var out struct {
		Database Database `json:"database"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/databases", nil,
		map[string]any{"name": name, "storage_gib": storageGiB}, &out)
	return out.Database, err
}

func (c *Client) DescribeDatabase(ctx context.Context, id string) (Database, error) {
	var out struct {
		Database Database `json:"database"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/databases/"+url.PathEscape(id), nil, nil, &out)
	return out.Database, err
}

func (c *Client) DeleteDatabase(ctx context.Context, id string) error {
	return c.do(ctx, http.MethodDelete, "/v1/databases/"+url.PathEscape(id), nil, nil, nil)
}

func (c *Client) DatabaseCredentials(ctx context.Context, id string) (DatabaseCredentials, error) {
	var out struct {
		Credentials DatabaseCredentials `json:"credentials"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/databases/"+url.PathEscape(id)+"/credentials", nil, nil, &out)
	return out.Credentials, err
}
