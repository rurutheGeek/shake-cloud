package main

import (
	"context"
	"errors"
	"flag"
	"fmt"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func (g globals) securityGroups(args []string) error {
	if len(args) == 0 {
		return errors.New("sg needs a subcommand: ls, show, create, rm, add, revoke")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		groups, err := c.DescribeSecurityGroups(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(groups)
		}
		printSecurityGroups(groups)
		return nil
	case "show":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud sg show GROUP_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		group, err := c.DescribeSecurityGroup(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(group)
		}
		printSecurityGroupDetail(group)
		return nil
	case "create":
		return g.securityGroupCreate(rest)
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud sg rm GROUP_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		if err := c.DeleteSecurityGroup(context.Background(), rest[0]); err != nil {
			return err
		}
		fmt.Printf("%s deleted\n", rest[0])
		return nil
	case "add":
		return g.securityGroupAdd(rest)
	case "revoke":
		if len(rest) != 2 {
			return errors.New("usage: shakecloud sg revoke GROUP_ID RULE_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		group, err := c.RevokeSecurityGroupRule(context.Background(), rest[0], rest[1])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(group)
		}
		printSecurityGroupDetail(group)
		return nil
	default:
		return fmt.Errorf("unknown sg subcommand %q", sub)
	}
}

func (g globals) securityGroupCreate(args []string) error {
	flags := flag.NewFlagSet("shakecloud sg create", flag.ContinueOnError)
	name := flags.String("name", "", "group name (required)")
	description := flags.String("description", "", "description")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *name == "" {
		flags.Usage()
		return errors.New("--name is required")
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	group, err := c.CreateSecurityGroup(context.Background(), client.CreateSecurityGroupRequest{GroupName: *name, Description: *description})
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(group)
	}
	printSecurityGroupDetail(group)
	return nil
}

func (g globals) securityGroupAdd(args []string) error {
	flags := flag.NewFlagSet("shakecloud sg add", flag.ContinueOnError)
	direction := flags.String("direction", "", "ingress or egress (required)")
	protocol := flags.String("protocol", "", "tcp, udp, icmp, icmpv6 or all (required)")
	from := flags.Int("from", -1, "first port (tcp/udp)")
	to := flags.Int("to", -1, "last port (tcp/udp)")
	cidr := flags.String("cidr", "", "IPv4 or IPv6 CIDR (required)")
	description := flags.String("description", "", "description")
	if err := flags.Parse(args); err != nil {
		return err
	}
	rest := flags.Args()
	if len(rest) != 1 || *direction == "" || *protocol == "" || *cidr == "" {
		flags.Usage()
		return errors.New("usage: shakecloud sg add GROUP_ID --direction ingress|egress --protocol PROTO --cidr CIDR [--from N --to N]")
	}
	rule := client.SecurityGroupRuleRequest{Protocol: *protocol, CIDR: *cidr, Description: *description}
	if *from >= 0 || *to >= 0 {
		rule.FromPort = from
		rule.ToPort = to
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	ctx := context.Background()
	var group client.SecurityGroup
	switch *direction {
	case "ingress", "in":
		group, err = c.AuthorizeIngress(ctx, rest[0], []client.SecurityGroupRuleRequest{rule})
	case "egress", "out":
		group, err = c.AuthorizeEgress(ctx, rest[0], []client.SecurityGroupRuleRequest{rule})
	default:
		return fmt.Errorf("--direction must be ingress or egress, got %q", *direction)
	}
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(group)
	}
	printSecurityGroupDetail(group)
	return nil
}

func printSecurityGroups(groups []client.SecurityGroup) {
	w := table()
	fmt.Fprintln(w, "GROUP_ID\tNAME\tOWNER\tDEFAULT\tINGRESS\tEGRESS\tINSTANCES")
	for _, group := range groups {
		fmt.Fprintf(w, "%s\t%s\t%s\t%t\t%d\t%d\t%d\n",
			group.GroupID, group.GroupName, dash(group.OwnerUsername), group.IsDefault,
			len(group.Ingress), len(group.Egress), len(group.InstanceIDs))
	}
	w.Flush()
}

func printSecurityGroupDetail(group client.SecurityGroup) {
	fmt.Printf("%s  %s  (default=%t, %d instances)\n", group.GroupID, group.GroupName, group.IsDefault, len(group.InstanceIDs))
	if group.Description != "" {
		fmt.Printf("  %s\n", group.Description)
	}
	for _, direction := range []struct {
		name  string
		rules []client.SecurityGroupRule
	}{{"ingress", group.Ingress}, {"egress", group.Egress}} {
		fmt.Printf("  %s:\n", direction.name)
		if len(direction.rules) == 0 {
			fmt.Printf("    (none)\n")
			continue
		}
		for _, rule := range direction.rules {
			ports := ""
			if rule.FromPort != nil && rule.ToPort != nil {
				ports = fmt.Sprintf(" %d-%d", *rule.FromPort, *rule.ToPort)
			}
			fmt.Printf("    %s  %s%s  %s  %s\n", rule.RuleID, rule.Protocol, ports, rule.CIDR, rule.Description)
		}
	}
}
