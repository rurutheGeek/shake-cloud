package client

import (
	"context"
	"net/http"
	"net/url"
	"time"
)

// Serverless functions backed by Knative. The function's own traffic never
// passes through the cloud API; these calls manage the Knative Service.

type Function struct {
	FunctionID    string    `json:"function_id"`
	Name          string    `json:"name"`
	AccountID     string    `json:"account_id"`
	OwnerUsername string    `json:"owner_username,omitempty"`
	Image         string    `json:"image"`
	Status        string    `json:"status"`
	URL           string    `json:"url,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
}

func (c *Client) DescribeFunctions(ctx context.Context) ([]Function, error) {
	var out struct {
		Functions []Function `json:"functions"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/functions", nil, nil, &out)
	return out.Functions, err
}

func (c *Client) CreateFunction(ctx context.Context, name, image string) (Function, error) {
	var out struct {
		Function Function `json:"function"`
	}
	err := c.do(ctx, http.MethodPost, "/v1/functions", nil,
		map[string]any{"name": name, "image": image}, &out)
	return out.Function, err
}

func (c *Client) DescribeFunction(ctx context.Context, id string) (Function, error) {
	var out struct {
		Function Function `json:"function"`
	}
	err := c.do(ctx, http.MethodGet, "/v1/functions/"+url.PathEscape(id), nil, nil, &out)
	return out.Function, err
}

func (c *Client) DeleteFunction(ctx context.Context, id string) error {
	return c.do(ctx, http.MethodDelete, "/v1/functions/"+url.PathEscape(id), nil, nil, nil)
}
