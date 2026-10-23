package compute

import (
	"context"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/workload"
)

// fakeWorkloads is the Kubernetes API in memory, enough for the service tests.
type fakeWorkloads struct {
	specs map[string]workload.Spec
}

func (f *fakeWorkloads) Apply(_ context.Context, spec workload.Spec) error {
	f.specs[spec.Name] = spec
	return nil
}

func (f *fakeWorkloads) Get(_ context.Context, _, name string) (workload.State, error) {
	if _, ok := f.specs[name]; !ok {
		return workload.State{}, nil
	}
	return workload.State{Ready: true, Address: "192.168.10.240"}, nil
}

func (f *fakeWorkloads) Secrets(_ context.Context, _, name string) (map[string]string, error) {
	return f.specs[name].Secrets, nil
}

func (f *fakeWorkloads) Delete(_ context.Context, _, name string) error {
	delete(f.specs, name)
	return nil
}

func workloadService(t *testing.T) (*Service, *fakeWorkloads, string) {
	t.Helper()
	s, _, _ := testService(t)
	fake := &fakeWorkloads{specs: map[string]workload.Spec{}}
	s.Workloads = fake
	s.ServiceNamespace = "services"
	return s, fake, newAccount(t, s, "svc-owner")
}

func TestServiceLifecycle(t *testing.T) {
	ctx := context.Background()
	s, fake, account := workloadService(t)
	record, created, err := s.CreateService(ctx, account, ServiceRequest{
		Name: "aihist", Image: "example/aihist:v1", Port: 5840,
		Env: map[string]string{"A": "1"}, Secrets: map[string]string{"TOKEN": "secret"},
		DiskGiB: 4, MountPath: "/data",
	}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if !created || record.MemoryMiB != defaultServiceMemory || len(record.SecretNames) != 1 {
		t.Fatalf("unexpected record %+v", record)
	}
	status, err := s.GetService(ctx, record.ID)
	if err != nil || status.URL != "http://192.168.10.240:5840" {
		t.Fatalf("status %+v, %v", status, err)
	}
	image := "example/aihist:v2"
	if _, err := s.ModifyService(ctx, record.ID, ServiceChange{Image: &image}, nil); err != nil {
		t.Fatal(err)
	}
	if spec := fake.specs[record.ID]; spec.Image != image || spec.Secrets["TOKEN"] != "secret" {
		t.Fatalf("a modify without secrets must keep them, got %+v", spec)
	}
	if err := s.DeleteService(ctx, record.ID, nil); err != nil {
		t.Fatal(err)
	}
	if len(fake.specs) != 0 {
		t.Fatal("delete left objects behind")
	}
}

func TestCreateServiceValidation(t *testing.T) {
	s, _, account := workloadService(t)
	for _, request := range []ServiceRequest{
		{Name: "A", Image: "i"},
		{Name: "app", Image: ""},
		{Name: "app", Image: "i", MemoryMiB: 2048},
		{Name: "app", Image: "i", Env: map[string]string{"1X": "v"}},
		{Name: "app", Image: "i", Env: map[string]string{"K": "v"}, Secrets: map[string]string{"K": "s"}},
		{Name: "app", Image: "i", DiskGiB: 1, MountPath: "/"},
		{Name: "app", Image: "i", MountPath: "/data"},
	} {
		if _, _, err := s.CreateService(context.Background(), account, request, nil); err == nil {
			t.Errorf("%+v was accepted", request)
		}
	}
}
