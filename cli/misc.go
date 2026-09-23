package main

import (
	"context"
	"flag"
	"fmt"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func (g globals) identity(args []string) error {
	c, err := g.client()
	if err != nil {
		return err
	}
	identity, err := c.CallerIdentity(context.Background())
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(identity)
	}
	w := table()
	fmt.Fprintf(w, "account_id\t%s\n", identity.AccountID)
	fmt.Fprintf(w, "username\t%s\n", identity.Username)
	fmt.Fprintf(w, "admin\t%t\n", identity.IsAdmin)
	fmt.Fprintf(w, "credential\t%s\n", identity.CredentialType)
	if identity.AccessKeyID != "" {
		fmt.Fprintf(w, "access_key_id\t%s\n", identity.AccessKeyID)
		fmt.Fprintf(w, "access_key_scope\t%s\n", identity.AccessKeyScope)
	}
	w.Flush()
	return nil
}

func (g globals) capacity(args []string) error {
	c, err := g.client()
	if err != nil {
		return err
	}
	capacity, err := c.DescribeCapacity(context.Background())
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(capacity)
	}
	fmt.Printf("node %s  %d threads  %s\n", capacity.Node.Name, capacity.Node.CPUThreads, capacity.Node.PVEVersion)
	fmt.Printf("  memory %d MiB used / %d MiB total, %d MiB available\n",
		capacity.Node.MemoryUsedMiB, capacity.Node.MemoryTotalMiB, capacity.Node.MemoryAvailableMiB)
	fmt.Println("storage:")
	for _, store := range capacity.Storage {
		fmt.Printf("  %-14s %-22s %5.1f%% used, %d MiB avail\n", store.Name, store.Purpose, store.UsedPercent, store.AvailMiB)
	}
	fmt.Println("allotted by the cloud:")
	printUsage("  cloud", capacity.Cloud)
	printUsage("  yours", capacity.Account)
	if len(capacity.Accounts) > 0 {
		fmt.Println("by account (admins only):")
		w := table()
		fmt.Fprintln(w, "  ACCOUNT\tUSERNAME\tINSTANCES\tVCPUS\tMEMORY_MIB\tROOT_DISK_GIB\tVOLUMES\tVOLUME_GIB")
		for _, usage := range capacity.Accounts {
			fmt.Fprintf(w, "  %s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\n", usage.AccountID, usage.Username,
				usage.Instances, usage.VCPUs, usage.MemoryMiB, usage.RootDiskGiB, usage.Volumes, usage.VolumeGiB)
		}
		w.Flush()
	}
	return nil
}

func printUsage(label string, usage client.Usage) {
	fmt.Printf("%s  %d instances, %d vCPU, %d MiB, %d GiB root, %d volumes / %d GiB\n",
		label, usage.Instances, usage.VCPUs, usage.MemoryMiB, usage.RootDiskGiB, usage.Volumes, usage.VolumeGiB)
}

func (g globals) limits(args []string) error {
	c, err := g.client()
	if err != nil {
		return err
	}
	limits, err := c.DescribeLimits(context.Background())
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(limits)
	}
	printLimits(limits)
	return nil
}

func printLimits(response client.LimitsResponse) {
	l := response.Limits
	fmt.Println("per account (0 means unlimited):")
	fmt.Printf("  instances %d, vcpu %d, memory %d MiB, root disk %d GiB\n",
		l.AccountQuota.Instances, l.AccountQuota.VCPUs, l.AccountQuota.MemoryMiB, l.AccountQuota.RootDiskGiB)
	fmt.Printf("  volumes %d, volume disk %d GiB\n", l.AccountQuota.Volumes, l.AccountQuota.VolumeGiB)
	fmt.Println("root disk GiB:")
	fmt.Printf("  min %d, default %d, max %d\n", l.RootDiskGiB.Min, l.RootDiskGiB.Default, l.RootDiskGiB.Max)
	fmt.Println("one volume GiB:")
	fmt.Printf("  min %d, max %d\n", l.VolumeSizeGiB.Min, l.VolumeSizeGiB.Max)
	fmt.Println("cloud:")
	fmt.Printf("  memory budget %d MiB, node reserve %d MiB, disk max used %d%%, image store free %d MiB, image max %d GiB\n",
		l.Capacity.MemoryBudgetMiB, l.Capacity.NodeMemoryReserveMiB, l.Capacity.VMDiskMaxUsedPercent,
		l.Capacity.ImageStoreMinFreeMiB, l.Capacity.MaxImageGiB)
	if len(response.Overrides) > 0 {
		fmt.Printf("administrator overrides: %v\n", response.Overrides)
	}
}

func (g globals) events(args []string) error {
	flags := flag.NewFlagSet("shakecloud events", flag.ContinueOnError)
	account := flags.String("account", "", "filter by account id")
	eventName := flags.String("name", "", "filter by operation id")
	max := flags.Int("max", 20, "how many events")
	if err := flags.Parse(args); err != nil {
		return err
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	events, err := c.LookupEvents(context.Background(), *account, *eventName, *max)
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(events)
	}
	w := table()
	fmt.Fprintln(w, "TIME\tOPERATION\tRESULT\tACCOUNT\tSOURCE")
	for _, event := range events {
		result := "ok"
		if event.ErrorCode != "" {
			result = event.ErrorCode
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n",
			event.EventTime.Format(time.RFC3339), event.EventName, result, dash(event.AccountID), event.SourceIPAddress)
	}
	w.Flush()
	return nil
}
