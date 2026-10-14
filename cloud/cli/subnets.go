package main

import (
	"context"
	"errors"
	"fmt"
)

func (g globals) subnets(args []string) error {
	if len(args) == 0 {
		return errors.New("subnet needs a subcommand: ls, show, map")
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	switch args[0] {
	case "ls", "list":
		subnets, err := c.DescribeSubnets(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(subnets)
		}
		w := table()
		fmt.Fprintln(w, "SUBNET\tCIDR\tGATEWAY\tVLAN\tDEFAULT\tLAUNCHABLE\tREASON")
		for _, s := range subnets {
			fmt.Fprintf(w, "%s\t%s\t%s\t%d\t%t\t%t\t%s\n",
				s.SubnetID, s.CIDRBlock, s.Gateway, s.VLANID, s.Default, s.Launchable, dash(s.StateReason))
		}
		return w.Flush()
	case "map":
		subnets, err := c.DescribeNetworkMap(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(subnets)
		}
		w := table()
		fmt.Fprintln(w, "SUBNET\tADDRESS\tNAME\tKIND\tSTATUS")
		for _, s := range subnets {
			for _, h := range s.Hosts {
				fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n", s.SubnetID, h.Address, h.Label, h.Kind, dash(h.Status))
			}
		}
		return w.Flush()
	case "show":
		if len(args) != 2 {
			return errors.New("usage: subnet show SUBNET_ID")
		}
		subnet, err := c.DescribeSubnet(context.Background(), args[1])
		if err != nil {
			return err
		}
		return g.printJSON(subnet)
	}
	return fmt.Errorf("unknown subnet subcommand %q", args[0])
}
