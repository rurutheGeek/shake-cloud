package compute

import (
	"context"
	"fmt"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/knative"
)

// fakeKnative is the Knative API in memory, enough for the function tests.
type fakeKnative struct {
	services map[string]knative.Service
}

func newFakeKnative() *fakeKnative { return &fakeKnative{services: map[string]knative.Service{}} }

func (f *fakeKnative) CreateService(_ context.Context, spec knative.ServiceSpec) (knative.Service, error) {
	service := knative.Service{
		Name: spec.Name, Namespace: spec.Namespace, Image: spec.Image,
		URL: "http://" + spec.Name + ".functions.example", Ready: true,
	}
	f.services[spec.Name] = service
	return service, nil
}

func (f *fakeKnative) GetService(_ context.Context, _, name string) (knative.Service, error) {
	service, ok := f.services[name]
	if !ok {
		return knative.Service{}, &knative.Error{Status: 404}
	}
	return service, nil
}

func (f *fakeKnative) ListServices(context.Context, string, string) ([]knative.Service, error) {
	out := make([]knative.Service, 0, len(f.services))
	for _, service := range f.services {
		out = append(out, service)
	}
	return out, nil
}

func (f *fakeKnative) DeleteService(_ context.Context, _, name string) error {
	delete(f.services, name)
	return nil
}

func functionService(t *testing.T) (*Service, *fakeKnative, string) {
	t.Helper()
	s, _, _ := testService(t)
	fake := newFakeKnative()
	s.Functions = fake
	s.FunctionNamespace = "functions"
	return s, fake, newAccount(t, s, "fn-owner")
}

func TestCreateFunction(t *testing.T) {
	s, fake, account := functionService(t)
	record, created, err := s.CreateFunction(context.Background(), account, "greeter", "example/greeter:v1", nil)
	if err != nil {
		t.Fatal(err)
	}
	if !created || record.Name != "greeter" || record.Image != "example/greeter:v1" {
		t.Fatalf("unexpected record %+v", record)
	}
	if _, ok := fake.services[record.ID]; !ok {
		t.Fatalf("service %s was not created", record.ID)
	}
	again, createdAgain, err := s.CreateFunction(context.Background(), account, "greeter", "example/greeter:v1", nil)
	if err != nil {
		t.Fatal(err)
	}
	if createdAgain || again.ID != record.ID {
		t.Fatalf("repeating the name must return the existing function, got %+v", again)
	}
}

func TestCreateFunctionValidation(t *testing.T) {
	s, _, account := functionService(t)
	for _, test := range []struct{ name, image string }{
		{"Greeter", "img"}, {"a", "img"}, {"x y", "img"}, {"-bad", "img"}, {"ok", ""},
	} {
		if _, _, err := s.CreateFunction(context.Background(), account, test.name, test.image, nil); code(err) != "InvalidParameterValue" {
			t.Fatalf("%q/%q: expected InvalidParameterValue, got %v", test.name, test.image, err)
		}
	}
}

func TestFunctionLifecycle(t *testing.T) {
	s, _, account := functionService(t)
	record, _, err := s.CreateFunction(context.Background(), account, "greeter", "example/greeter:v1", nil)
	if err != nil {
		t.Fatal(err)
	}
	list, err := s.ListFunctions(context.Background(), account)
	if err != nil || len(list) != 1 || !list[0].Ready || list[0].URL == "" {
		t.Fatalf("list = %+v, %v", list, err)
	}
	got, err := s.GetFunction(context.Background(), record.ID)
	if err != nil || got.Function.Name != "greeter" {
		t.Fatalf("get = %+v, %v", got, err)
	}
	if err := s.DeleteFunction(context.Background(), record.ID, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := s.GetFunction(context.Background(), record.ID); code(err) != "NoSuchFunction" {
		t.Fatalf("expected NoSuchFunction after delete, got %v", err)
	}
}

func TestFunctionLimit(t *testing.T) {
	s, _, account := functionService(t)
	for i := 0; i < maxFunctionsPerAccount; i++ {
		if _, _, err := s.CreateFunction(context.Background(), account, fmt.Sprintf("fn%d", i), "img", nil); err != nil {
			t.Fatal(err)
		}
	}
	if _, _, err := s.CreateFunction(context.Background(), account, "toomany", "img", nil); code(err) != "FunctionLimitExceeded" {
		t.Fatalf("expected FunctionLimitExceeded, got %v", err)
	}
}
