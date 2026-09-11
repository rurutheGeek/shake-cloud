// Package netbox allocates and releases instance addresses in NetBox's IPAM.
//
// NetBox owns uniqueness: an address is taken with the IP range's
// available-ips endpoint, which never hands the same address out twice. The
// cloud API only remembers which address belongs to which instance.
package netbox

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type Client struct {
	base  string
	token string
	http  *http.Client
}

func New(serverURL, token string) *Client {
	return &Client{
		base:  strings.TrimRight(serverURL, "/") + "/api",
		token: token,
		http:  &http.Client{Timeout: 60 * time.Second},
	}
}

// Error is a non-2xx answer. Detail is NetBox's explanation, never the request.
type Error struct {
	Method string
	Path   string
	Status int
	Detail string
}

func (e *Error) Error() string {
	return fmt.Sprintf("netbox %s %s: %d %s", e.Method, e.Path, e.Status, e.Detail)
}

func (c *Client) do(ctx context.Context, method, path string, body, out any) error {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(encoded)
	}
	request, err := http.NewRequestWithContext(ctx, method, c.base+path, reader)
	if err != nil {
		return err
	}
	// NetBox 4.5+ tokens (nbt_<key>.<token>) use Bearer; older ones use Token.
	scheme := "Token "
	if strings.HasPrefix(c.token, "nbt_") {
		scheme = "Bearer "
	}
	request.Header.Set("Authorization", scheme+c.token)
	request.Header.Set("Accept", "application/json")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	route := strings.SplitN(path, "?", 2)[0]
	response, err := c.http.Do(request)
	if err != nil {
		return fmt.Errorf("netbox %s %s: %w", method, route, err)
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, 4<<20))
	if err != nil {
		return fmt.Errorf("netbox %s %s: %w", method, route, err)
	}
	if response.StatusCode/100 != 2 {
		var detail struct {
			Detail string `json:"detail"`
		}
		_ = json.Unmarshal(raw, &detail)
		if detail.Detail == "" {
			detail.Detail = strings.TrimSpace(string(raw))
			if len(detail.Detail) > 300 {
				detail.Detail = detail.Detail[:300]
			}
		}
		return &Error{Method: method, Path: route, Status: response.StatusCode, Detail: detail.Detail}
	}
	if out == nil || len(raw) == 0 {
		return nil
	}
	return json.Unmarshal(raw, out)
}

type IPAddress struct {
	ID          int    `json:"id"`
	Address     string `json:"address"`
	Description string `json:"description"`
	DNSName     string `json:"dns_name"`
}

type page[T any] struct {
	Results []T `json:"results"`
}

// IPRangeID finds the range that starts at startAddress, e.g. "192.168.10.100/24".
func (c *Client) IPRangeID(ctx context.Context, startAddress string) (int, error) {
	var ranges page[struct {
		ID int `json:"id"`
	}]
	if err := c.do(ctx, http.MethodGet, "/ipam/ip-ranges/?start_address="+url.QueryEscape(startAddress), nil, &ranges); err != nil {
		return 0, err
	}
	if len(ranges.Results) != 1 {
		return 0, fmt.Errorf("netbox: expected one IP range starting at %s, found %d", startAddress, len(ranges.Results))
	}
	return ranges.Results[0].ID, nil
}

// IPAddressesByDescription finds addresses an earlier, interrupted attempt
// may already have allocated for the same instance.
func (c *Client) IPAddressesByDescription(ctx context.Context, description string) ([]IPAddress, error) {
	var addresses page[IPAddress]
	err := c.do(ctx, http.MethodGet, "/ipam/ip-addresses/?limit=50&description="+url.QueryEscape(description), nil, &addresses)
	return addresses.Results, err
}

type Allocation struct {
	Description string
	DNSName     string
	Tags        []string
}

// AllocateIP takes the next free address in the range.
func (c *Client) AllocateIP(ctx context.Context, rangeID int, allocation Allocation) (IPAddress, error) {
	tags := make([]map[string]string, 0, len(allocation.Tags))
	for _, slug := range allocation.Tags {
		tags = append(tags, map[string]string{"slug": slug})
	}
	body := map[string]any{
		"status":      "active",
		"description": allocation.Description,
		"dns_name":    allocation.DNSName,
		"tags":        tags,
	}
	var address IPAddress
	err := c.do(ctx, http.MethodPost, fmt.Sprintf("/ipam/ip-ranges/%d/available-ips/", rangeID), body, &address)
	return address, err
}

// DeleteIPAddress releases an address. An address that is already gone is not an error.
func (c *Client) DeleteIPAddress(ctx context.Context, id int) error {
	err := c.do(ctx, http.MethodDelete, fmt.Sprintf("/ipam/ip-addresses/%d/", id), nil, nil)
	if e, ok := err.(*Error); ok && e.Status == http.StatusNotFound {
		return nil
	}
	return err
}
