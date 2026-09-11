// Command shakecloud is the command-line client for the shake-cloud API.
//
// It uses the same API and access key as Terraform and the portal:
//
//	export SHAKECLOUD_ACCESS_KEY='sca_...'   # issue one in the portal
//	shakecloud instance ls
//	shakecloud instance run --image img-debian13 --type small --name web --wait
//
// The endpoint defaults to the deployment's public address; override it with
// --endpoint or SHAKECLOUD_ENDPOINT. Nothing is read from a config file, and
// the access key is read from the environment so it is not left in shells'
// history.
package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"text/tabwriter"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "shakecloud: "+err.Error())
		os.Exit(1)
	}
}

// globals are the options that come before the command.
type globals struct {
	endpoint string
	json     bool
}

func run(args []string) error {
	flags := flag.NewFlagSet("shakecloud", flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	endpoint := flags.String("endpoint", envOr("SHAKECLOUD_ENDPOINT", client.DefaultEndpoint), "API endpoint")
	asJSON := flags.Bool("json", false, "print the raw JSON instead of a table")
	flags.Usage = usage
	// flag.Parse stops at the first non-flag, so the command follows the
	// global options: shakecloud --json instance ls
	if err := flags.Parse(args); err != nil {
		return err
	}
	rest := flags.Args()
	if len(rest) == 0 {
		usage()
		return errors.New("no command given")
	}
	g := globals{endpoint: *endpoint, json: *asJSON}
	switch rest[0] {
	case "help":
		usage()
		return nil
	case "identity":
		return g.identity(rest[1:])
	case "capacity":
		return g.capacity(rest[1:])
	case "limits":
		return g.limits(rest[1:])
	case "events":
		return g.events(rest[1:])
	case "instance", "instances":
		return g.instances(rest[1:])
	case "volume", "volumes":
		return g.volumes(rest[1:])
	case "sg", "security-group", "security-groups":
		return g.securityGroups(rest[1:])
	case "image", "images":
		return g.images(rest[1:])
	case "key", "keys":
		return g.keyPairs(rest[1:])
	case "access-key", "access-keys":
		return g.accessKeys(rest[1:])
	default:
		return fmt.Errorf("unknown command %q; run shakecloud help", rest[0])
	}
}

func usage() {
	fmt.Fprintf(os.Stderr, `shakecloud - operate a shake-cloud deployment

Usage:
  shakecloud [--endpoint URL] [--json] <command> [args]

Commands:
  identity                       Who the access key belongs to
  capacity                       Node, storage and account usage
  limits                         Effective limits and the administrator's overrides
  events [--account ID] [--name OP] [--max N]
                                 Read the audit log
  instance ls [--account ID]     List instances
  instance show ID               Show one instance
  instance run --image IMG [--type T | --vcpus N --memory MIB] [--disk GiB]
               [--key NAME] [--sg ID]... [--name NAME] [--user-data FILE] [--wait]
                                 Launch an instance
  instance start|stop|reboot ID  Power an instance
  instance rm ID [--wait]        Terminate an instance
  instance console ID            Print a short-lived console URL
  instance sg ID GROUP...        Replace an instance's security groups
  instance modify ID [--vcpus N] [--memory MIB] [--min-memory MIB]
                     [--balloon=true|false] [--disk GiB]
  instance types                 List size presets
  instance adopt --vmid N --account ID [--name NAME] [--ip ADDR] [--disk GiB]
                                 Register an existing cloud-pool VM
  volume ls                      List volumes
  volume create --size GiB [--name NAME]
  volume rm ID
  volume resize ID GiB
  volume attach ID --instance IID [--device virtioN]
  volume detach ID
  sg ls | sg show ID             Security groups
  sg create --name NAME [--description TEXT]
  sg rm ID
  sg add ID --direction ingress|egress --protocol tcp|udp|icmp|icmpv6|all
           [--from N --to N] --cidr CIDR [--description TEXT]
  sg revoke ID RULE_ID
  image ls                       Images
  image upload --name NAME FILE [--wait]
  image rm ID
  key ls                         SSH key pairs
  key import --name NAME (--public-key KEY | FILE)
  key rm NAME
  access-key ls                  API access keys
  access-key rm ID

Set SHAKECLOUD_ACCESS_KEY to the key issued by the portal. The endpoint defaults
to %s.
`, client.DefaultEndpoint)
}

func envOr(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func (g globals) client() (*client.Client, error) {
	key := os.Getenv("SHAKECLOUD_ACCESS_KEY")
	if key == "" {
		return nil, errors.New("set SHAKECLOUD_ACCESS_KEY to a key issued by the portal")
	}
	return client.New(g.endpoint, key), nil
}

func (g globals) printJSON(value any) error {
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}

// table is a tabwriter for the human-readable output.
func table() *tabwriter.Writer {
	return tabwriter.NewWriter(os.Stdout, 0, 4, 2, ' ', 0)
}

// boolFlag parses a --name=true|false option.
type boolFlag struct{ value *bool }

func (b boolFlag) String() string {
	if b.value == nil {
		return "false"
	}
	return fmt.Sprint(*b.value)
}

func (b boolFlag) Set(text string) error {
	parsed, err := parseBool(text)
	if err != nil {
		return err
	}
	*b.value = parsed
	return nil
}

func parseBool(text string) (bool, error) {
	switch text {
	case "true", "1", "yes":
		return true, nil
	case "false", "0", "no":
		return false, nil
	default:
		return false, fmt.Errorf("expected true or false, got %q", text)
	}
}
