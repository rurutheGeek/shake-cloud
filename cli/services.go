package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"

	"github.com/rurutheGeek/shake-cloud/client"
)

// pairs collects repeated NAME=VALUE flags.
type pairs map[string]string

func (p pairs) String() string { return "" }

func (p pairs) Set(value string) error {
	name, v, ok := strings.Cut(value, "=")
	if !ok || name == "" {
		return fmt.Errorf("%q is not NAME=VALUE", value)
	}
	p[name] = v
	return nil
}

// secretNames collects repeated --secret NAME flags. The value is read from
// the environment variable of the same name, so it never appears in argv or
// the shell history.
type secretNames map[string]string

func (s secretNames) String() string { return "" }

func (s secretNames) Set(name string) error {
	value, ok := os.LookupEnv(name)
	if !ok {
		return fmt.Errorf("--secret %s: the environment variable %s is not set", name, name)
	}
	s[name] = value
	return nil
}

func (g globals) services(args []string) error {
	if len(args) == 0 {
		return errors.New("service needs a subcommand: ls, create, show, update, rm")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		services, err := c.DescribeServices(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(services)
		}
		printServices(services)
		return nil
	case "create":
		flags := flag.NewFlagSet("shakecloud service create", flag.ContinueOnError)
		image := flags.String("image", "", "container image (required)")
		port := flags.Int("port", 0, "port the container listens on; gives the service a LAN address")
		memory := flags.Int("memory", 0, "memory in MiB (default 128)")
		disk := flags.String("disk", "", "persistent disk as SIZE_GIB:MOUNT_PATH, e.g. 8:/data")
		env := pairs{}
		secrets := secretNames{}
		flags.Var(env, "env", "environment variable NAME=VALUE (repeatable)")
		flags.Var(secrets, "secret", "secret NAME, its value read from $NAME (repeatable)")
		if err := flags.Parse(rest); err != nil {
			return err
		}
		names := flags.Args()
		if len(names) != 1 || *image == "" {
			return errors.New("usage: shakecloud service create --image IMAGE [--port N] [--memory MIB] [--disk GIB:PATH] [--env K=V] [--secret K] NAME")
		}
		input := client.CreateServiceInput{
			Name: names[0], Image: *image, Port: *port, MemoryMiB: *memory, Env: env, Secrets: secrets,
		}
		if *disk != "" {
			size, path, ok := strings.Cut(*disk, ":")
			gib, err := strconv.Atoi(size)
			if !ok || err != nil {
				return fmt.Errorf("--disk %q is not SIZE_GIB:MOUNT_PATH", *disk)
			}
			input.Disk = &client.ServiceDisk{SizeGiB: gib, MountPath: path}
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		service, err := c.CreateService(context.Background(), input)
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(service)
		}
		printServiceDetail(service)
		return nil
	case "update":
		flags := flag.NewFlagSet("shakecloud service update", flag.ContinueOnError)
		image := flags.String("image", "", "new container image")
		memory := flags.Int("memory", 0, "new memory in MiB")
		env := pairs{}
		secrets := secretNames{}
		flags.Var(env, "env", "environment variable NAME=VALUE; replaces all of them (repeatable)")
		flags.Var(secrets, "secret", "secret NAME from $NAME; replaces all of them (repeatable)")
		if err := flags.Parse(rest); err != nil {
			return err
		}
		ids := flags.Args()
		if len(ids) != 1 {
			return errors.New("usage: shakecloud service update [--image IMAGE] [--memory MIB] [--env K=V] [--secret K] SERVICE_ID")
		}
		input := client.ModifyServiceInput{}
		if *image != "" {
			input.Image = image
		}
		if *memory != 0 {
			input.MemoryMiB = memory
		}
		if len(env) > 0 {
			m := map[string]string(env)
			input.Env = &m
		}
		if len(secrets) > 0 {
			m := map[string]string(secrets)
			input.Secrets = &m
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		service, err := c.ModifyService(context.Background(), ids[0], input)
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(service)
		}
		printServiceDetail(service)
		return nil
	case "show":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud service show SERVICE_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		service, err := c.DescribeService(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(service)
		}
		printServiceDetail(service)
		return nil
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud service rm SERVICE_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		if err := c.DeleteService(context.Background(), rest[0]); err != nil {
			return err
		}
		fmt.Printf("%s deleted\n", rest[0])
		return nil
	default:
		return fmt.Errorf("unknown service subcommand %q", sub)
	}
}

func printServices(services []client.Service) {
	w := table()
	fmt.Fprintln(w, "SERVICE_ID\tNAME\tSTATUS\tMEMORY\tURL\tIMAGE")
	for _, service := range services {
		fmt.Fprintf(w, "%s\t%s\t%s\t%dMiB\t%s\t%s\n", service.ServiceID, service.Name, service.Status,
			service.MemoryMiB, dash(service.URL), service.Image)
	}
	w.Flush()
}

func printServiceDetail(service client.Service) {
	fmt.Printf("%s  %s  (%s)\n", service.ServiceID, service.Name, service.Status)
	fmt.Printf("  image   %s\n", service.Image)
	fmt.Printf("  memory  %dMiB\n", service.MemoryMiB)
	if service.URL != "" {
		fmt.Printf("  url     %s\n", service.URL)
	}
	if service.Disk != nil {
		fmt.Printf("  disk    %dGiB at %s\n", service.Disk.SizeGiB, service.Disk.MountPath)
	}
	keys := make([]string, 0, len(service.Env))
	for key := range service.Env {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		fmt.Printf("  env     %s=%s\n", key, service.Env[key])
	}
	if len(service.SecretNames) > 0 {
		fmt.Printf("  secrets %s\n", strings.Join(service.SecretNames, ", "))
	}
	fmt.Printf("  owner   %s\n", dash(service.OwnerUsername))
}
