package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func (g globals) instances(args []string) error {
	if len(args) == 0 {
		return errors.New("instance needs a subcommand: ls, show, run, start, stop, reboot, rm, console, sg, modify, types, adopt")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		return g.instanceLs(rest)
	case "types":
		return g.instanceTypes(rest)
	case "show":
		return g.instanceShow(rest)
	case "run", "launch":
		return g.instanceRun(rest)
	case "start", "stop", "reboot":
		return g.instancePower(sub, rest)
	case "rm", "terminate", "delete":
		return g.instanceTerminate(rest)
	case "console":
		return g.instanceConsole(rest)
	case "sg", "security-groups":
		return g.instanceSetGroups(rest)
	case "modify":
		return g.instanceModify(rest)
	case "adopt":
		return g.instanceAdopt(rest)
	default:
		return fmt.Errorf("unknown instance subcommand %q", sub)
	}
}

func (g globals) instanceLs(args []string) error {
	flags := flag.NewFlagSet("shakecloud instance ls", flag.ContinueOnError)
	account := flags.String("account", "", "filter by account id")
	if err := flags.Parse(args); err != nil {
		return err
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	instances, err := c.DescribeInstances(context.Background(), *account)
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(instances)
	}
	printInstances(instances)
	return nil
}

func printInstances(instances []client.Instance) {
	w := table()
	fmt.Fprintln(w, "INSTANCE_ID\tNAME\tOWNER\tSTATE\tIP\tSPEC\tDISK\tSECURITY_GROUPS")
	for _, i := range instances {
		spec := i.InstanceType
		if spec == "" {
			spec = "custom"
		}
		spec += fmt.Sprintf(" %dc/%dMiB", i.VCPUs, i.MemoryMiB)
		groups := make([]string, 0, len(i.SecurityGroups))
		for _, group := range i.SecurityGroups {
			groups = append(groups, group.GroupName)
		}
		name := i.Name()
		if i.Adopted {
			name += " (adopted)"
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\t%s\t%dGiB\t%s\n",
			i.InstanceID, dash(name), dash(i.OwnerUsername), i.State, dash(i.PrivateIPAddress),
			spec, i.RootDiskGiB, dash(strings.Join(groups, ",")))
	}
	w.Flush()
}

func (g globals) instanceTypes(args []string) error {
	c, err := g.client()
	if err != nil {
		return err
	}
	types, err := c.DescribeInstanceTypes(context.Background())
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(types)
	}
	w := table()
	fmt.Fprintln(w, "TYPE\tVCPUS\tMEMORY_MIB\tMEMORY_MIN_MIB")
	for _, t := range types {
		fmt.Fprintf(w, "%s\t%d\t%d\t%d\n", t.InstanceType, t.VCPUs, t.MemoryMiB, t.MemoryMinMiB)
	}
	w.Flush()
	return nil
}

func (g globals) instanceShow(args []string) error {
	if len(args) != 1 {
		return errors.New("usage: shakecloud instance show INSTANCE_ID")
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	instance, err := c.DescribeInstance(context.Background(), args[0])
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(instance)
	}
	printInstanceDetail(instance)
	return nil
}

func printInstanceDetail(i client.Instance) {
	w := table()
	fmt.Fprintf(w, "instance_id\t%s\n", i.InstanceID)
	fmt.Fprintf(w, "name\t%s\n", dash(i.Name()))
	fmt.Fprintf(w, "owner\t%s\n", dash(i.OwnerUsername))
	fmt.Fprintf(w, "state\t%s\n", i.State)
	if i.StateReason != "" {
		fmt.Fprintf(w, "state_reason\t%s\n", i.StateReason)
	}
	fmt.Fprintf(w, "private_ip\t%s\n", dash(i.PrivateIPAddress))
	fmt.Fprintf(w, "mac\t%s\n", i.MACAddress)
	fmt.Fprintf(w, "image\t%s\n", dash(i.ImageName))
	fmt.Fprintf(w, "spec\t%d vCPU / %d MiB%s\n", i.VCPUs, i.MemoryMiB, balloonNote(i))
	fmt.Fprintf(w, "root_disk\t%d GiB\n", i.RootDiskGiB)
	fmt.Fprintf(w, "adopted\t%t\n", i.Adopted)
	fmt.Fprintf(w, "firewall\t%s\n", i.FirewallState)
	fmt.Fprintf(w, "launched\t%s\n", i.LaunchTime.Format(time.RFC3339))
	w.Flush()
}

func balloonNote(i client.Instance) string {
	if i.Ballooning {
		return fmt.Sprintf(" (balloon floor %d MiB)", i.MemoryMinMiB)
	}
	return " (fixed)"
}

func (g globals) instanceRun(args []string) error {
	flags := flag.NewFlagSet("shakecloud instance run", flag.ContinueOnError)
	image := flags.String("image", "", "image id (required)")
	instanceType := flags.String("type", "", "size preset from `instance types`")
	vcpus, memory, minMemory := &optionalInt{}, &optionalInt{}, &optionalInt{}
	flags.Var(vcpus, "vcpus", "vCPU count")
	flags.Var(memory, "memory", "memory MiB")
	flags.Var(minMemory, "min-memory", "balloon floor MiB")
	balloon := &optionalBool{}
	flags.Var(balloon, "balloon", "use ballooning (true|false)")
	disk := flags.Int("disk", 0, "root disk GiB")
	keyName := flags.String("key", "", "SSH key pair name")
	groups := &stringsFlag{}
	flags.Var(groups, "sg", "security group id (repeatable)")
	name := flags.String("name", "", "instance name")
	userData := flags.String("user-data", "", "path to a cloud-init user-data file")
	clientToken := flags.String("client-token", "", "idempotency token")
	tags := keyValues{}
	flags.Var(tags, "tag", "tag key=value (repeatable)")
	wait := flags.Bool("wait", false, "wait until the instance is running")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *image == "" {
		flags.Usage()
		return errors.New("--image is required")
	}
	if *name != "" {
		tags["Name"] = *name
	}
	request := client.RunRequest{
		ImageID: *image, InstanceType: *instanceType, KeyName: *keyName,
		VCPUs: vcpus.pointer(), MemoryMiB: memory.pointer(), MemoryMinMiB: minMemory.pointer(),
		Ballooning: balloon.pointer(), RootDiskGiB: *disk, ClientToken: *clientToken,
		Tags: tags, SecurityGroupIDs: *groups,
	}
	if *userData != "" {
		data, err := os.ReadFile(*userData)
		if err != nil {
			return err
		}
		request.UserData = string(data)
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	instance, err := c.RunInstances(context.Background(), request)
	if err != nil {
		return err
	}
	if *wait {
		instance, err = c.WaitInstance(context.Background(), instance.InstanceID, 10*time.Minute, "running", "terminated")
		if err != nil {
			return err
		}
	}
	if g.json {
		return g.printJSON(instance)
	}
	printInstanceDetail(instance)
	return nil
}

// instancePower handles start, stop and reboot, which differ in the state they
// settle into.
func (g globals) instancePower(action string, args []string) error {
	flags := flag.NewFlagSet("shakecloud instance "+action, flag.ContinueOnError)
	wait := flags.Bool("wait", false, "wait for the instance to settle")
	rest, err := parseWithID(flags, args)
	if err != nil {
		return err
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	ctx := context.Background()
	var instance client.Instance
	switch action {
	case "start":
		instance, err = c.StartInstance(ctx, rest)
	case "stop":
		instance, err = c.StopInstance(ctx, rest)
	case "reboot":
		instance, err = c.RebootInstance(ctx, rest)
	}
	if err != nil {
		return err
	}
	if *wait {
		wanted := "running"
		if action == "stop" {
			wanted = "stopped"
		}
		instance, err = c.WaitInstance(ctx, instance.InstanceID, 5*time.Minute, wanted)
		if err != nil {
			return err
		}
	}
	if g.json {
		return g.printJSON(instance)
	}
	fmt.Printf("%s is %s\n", instance.InstanceID, instance.State)
	return nil
}

func (g globals) instanceTerminate(args []string) error {
	flags := flag.NewFlagSet("shakecloud instance rm", flag.ContinueOnError)
	wait := flags.Bool("wait", false, "wait until the instance is terminated")
	rest, err := parseWithID(flags, args)
	if err != nil {
		return err
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	ctx := context.Background()
	instance, err := c.TerminateInstance(ctx, rest)
	if err != nil {
		return err
	}
	if *wait {
		instance, err = c.WaitInstance(ctx, instance.InstanceID, 10*time.Minute, "terminated")
		if err != nil {
			return err
		}
	}
	if g.json {
		return g.printJSON(instance)
	}
	fmt.Printf("%s is %s\n", instance.InstanceID, instance.State)
	return nil
}

func (g globals) instanceConsole(args []string) error {
	if len(args) != 1 {
		return errors.New("usage: shakecloud instance console INSTANCE_ID")
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	session, err := c.CreateConsoleSession(context.Background(), args[0])
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(session)
	}
	fmt.Printf("%s\n", strings.TrimRight(c.Endpoint(), "/")+session.URL)
	fmt.Printf("expires %s\n", session.ExpiresAt.Format(time.RFC3339))
	return nil
}

func (g globals) instanceSetGroups(args []string) error {
	if len(args) < 2 {
		return errors.New("usage: shakecloud instance sg INSTANCE_ID GROUP_ID [GROUP_ID...]")
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	instance, err := c.SetInstanceSecurityGroups(context.Background(), args[0], args[1:])
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(instance)
	}
	fmt.Printf("%s security groups updated\n", instance.InstanceID)
	return nil
}

func (g globals) instanceModify(args []string) error {
	flags := flag.NewFlagSet("shakecloud instance modify", flag.ContinueOnError)
	vcpus, memory, minMemory, disk := &optionalInt{}, &optionalInt{}, &optionalInt{}, &optionalInt{}
	flags.Var(vcpus, "vcpus", "vCPU count")
	flags.Var(memory, "memory", "memory MiB")
	flags.Var(minMemory, "min-memory", "balloon floor MiB")
	flags.Var(disk, "disk", "root disk GiB (grow only)")
	balloon := &optionalBool{}
	flags.Var(balloon, "balloon", "use ballooning (true|false)")
	rest, err := parseWithID(flags, args)
	if err != nil {
		return err
	}
	request := client.ModifyInstanceRequest{
		VCPUs: vcpus.pointer(), MemoryMiB: memory.pointer(), MemoryMinMiB: minMemory.pointer(),
		Ballooning: balloon.pointer(), RootDiskGiB: disk.pointer(),
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	instance, err := c.ModifyInstance(context.Background(), rest, request)
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(instance)
	}
	printInstanceDetail(instance)
	return nil
}

func (g globals) instanceAdopt(args []string) error {
	flags := flag.NewFlagSet("shakecloud instance adopt", flag.ContinueOnError)
	vmid := flags.Int("vmid", 0, "VMID of the existing VM in the cloud pool (required)")
	account := flags.String("account", "", "owner account id (required, admins only)")
	name := flags.String("name", "", "display name; defaults to the VM's own")
	ip := flags.String("ip", "", "the VM's address, so security groups can filter")
	disk := flags.Int("disk", 0, "root disk GiB when storage cannot report it")
	tags := keyValues{}
	flags.Var(tags, "tag", "tag key=value (repeatable)")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *vmid == 0 || *account == "" {
		flags.Usage()
		return errors.New("--vmid and --account are required")
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	instance, err := c.AdoptInstance(context.Background(), client.AdoptRequest{
		VMID: *vmid, AccountID: *account, Name: *name, PrivateIPAddress: *ip,
		RootDiskGiB: *disk, Tags: tags,
	})
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(instance)
	}
	printInstanceDetail(instance)
	return nil
}

// parseWithID parses flags and returns the single positional ID that follows.
func parseWithID(flags *flag.FlagSet, args []string) (string, error) {
	if err := flags.Parse(args); err != nil {
		return "", err
	}
	rest := flags.Args()
	if len(rest) != 1 {
		return "", fmt.Errorf("usage: %s ID", flags.Name())
	}
	return rest[0], nil
}

func dash(value string) string {
	if value == "" {
		return "-"
	}
	return value
}
