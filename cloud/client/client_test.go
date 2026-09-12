package client

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestRunInstancesSendsTheAccessKeyAndDecodesTheEnvelope(t *testing.T) {
	var gotAuth, gotPath, gotBody string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth, gotPath = r.Header.Get("Authorization"), r.URL.Path
		body, _ := io.ReadAll(r.Body)
		gotBody = string(body)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		io.WriteString(w, `{"instance":{"instance_id":"i-0123456789abcdef0","account_id":"123456789012",
			"image_id":"img-debian13","state":"pending","mac_address":"BC:24:11:00:00:01",
			"vcpus":2,"memory_mib":2048,"root_disk_gib":20,"ballooning":true,"tags":{"Name":"web"},
			"launch_time":"2026-09-11T00:00:00Z","security_groups":[],"firewall_state":"in-sync"}}`)
	}))
	defer server.Close()

	c := New(server.URL, "sca_example.secret")
	instance, err := c.RunInstances(context.Background(), RunRequest{
		ImageID: "img-debian13", InstanceType: "small", Tags: map[string]string{"Name": "web"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if gotAuth != "Bearer sca_example.secret" {
		t.Fatalf("Authorization = %q", gotAuth)
	}
	if gotPath != "/v1/instances" {
		t.Fatalf("path = %q", gotPath)
	}
	if !strings.Contains(gotBody, `"instance_type":"small"`) {
		t.Fatalf("body = %s", gotBody)
	}
	if instance.InstanceID != "i-0123456789abcdef0" || instance.State != "pending" || instance.VCPUs != 2 {
		t.Fatalf("instance = %+v", instance)
	}
	if instance.Name() != "web" {
		t.Fatalf("name = %q", instance.Name())
	}
}

func TestARefusalIsATypedAPIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusConflict)
		io.WriteString(w, `{"error":{"code":"InstanceLimitExceeded","message":"an account may hold 8 instances"},
			"request_id":"req-1"}`)
	}))
	defer server.Close()

	_, err := New(server.URL, "sca_x.y").DescribeInstance(context.Background(), "i-1")
	var apiError *APIError
	if !errors.As(err, &apiError) {
		t.Fatalf("err = %v, want *APIError", err)
	}
	if apiError.Status != http.StatusConflict || apiError.Code != "InstanceLimitExceeded" || apiError.RequestID != "req-1" {
		t.Fatalf("apiError = %+v", apiError)
	}
	if apiError.NotFound() {
		t.Fatal("a 409 must not read as not found")
	}
}

func TestImportImageStreamsNameBeforeFile(t *testing.T) {
	var name, filename, content string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		reader, err := r.MultipartReader()
		if err != nil {
			t.Errorf("multipart: %v", err)
			return
		}
		for {
			part, err := reader.NextPart()
			if err == io.EOF {
				break
			}
			if err != nil {
				t.Errorf("part: %v", err)
				return
			}
			data, _ := io.ReadAll(part)
			switch part.FormName() {
			case "name":
				name = string(data)
			case "file":
				filename, content = part.FileName(), string(data)
			}
		}
		w.WriteHeader(http.StatusCreated)
		io.WriteString(w, `{"image":{"image_id":"img-0123456789abcdef0","name":"ubuntu","state":"available","public":false}}`)
	}))
	defer server.Close()

	image, err := New(server.URL, "sca_x.y").ImportImage(context.Background(), "ubuntu", "disk.qcow2", strings.NewReader("QFI"))
	if err != nil {
		t.Fatal(err)
	}
	if name != "ubuntu" || filename != "disk.qcow2" || content != "QFI" {
		t.Fatalf("name=%q filename=%q content=%q", name, filename, content)
	}
	if image.ImageID != "img-0123456789abcdef0" {
		t.Fatalf("image = %+v", image)
	}
}

func TestWaitInstancePollsUntilTheWantedState(t *testing.T) {
	calls := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		state := "pending"
		if calls >= 2 {
			state = "running"
		}
		io.WriteString(w, `{"instance":{"instance_id":"i-0123456789abcdef0","account_id":"1","image_id":"img-x",
			"state":"`+state+`","mac_address":"m","vcpus":1,"memory_mib":512,"root_disk_gib":10,"ballooning":false,
			"launch_time":"2026-09-11T00:00:00Z","security_groups":[],"firewall_state":"in-sync"}}`)
	}))
	defer server.Close()

	instance, err := New(server.URL, "sca_x.y").WaitInstance(context.Background(), "i-0123456789abcdef0", 5*time.Second, "running", "terminated")
	if err != nil {
		t.Fatal(err)
	}
	if instance.State != "running" || calls < 2 {
		t.Fatalf("state=%q calls=%d", instance.State, calls)
	}
}
