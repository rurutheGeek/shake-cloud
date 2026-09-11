package compute

import (
	"context"
	"fmt"
	"net/url"
	"regexp"
	"slices"
	"strings"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
)

// The fake node's disks, firewalls and IP sets. They follow what was measured
// on the real one (docs/operations/cloud.md): a moved disk is renamed after its
// new VM, unlinking without force leaves an unusedN entry, and a rule posted
// without a position lands at the top.

type fakeFirewall struct {
	rules        []proxmox.FirewallRule
	options      map[string]any
	ipsets       map[string][]string
	optionWrites int
}

var allocation = regexp.MustCompile(`^local-lvm:(\d+)$`)

func (f *fakePVE) firewall(vmid int) *fakeFirewall {
	if f.firewalls[vmid] == nil {
		f.firewalls[vmid] = &fakeFirewall{options: map[string]any{}, ipsets: map[string][]string{}}
	}
	return f.firewalls[vmid]
}

// nextDisk names a new disk for vmid the way Proxmox does: the lowest free number.
func (f *fakePVE) nextDisk(vmid int) string {
	for n := 0; ; n++ {
		volid := fmt.Sprintf("local-lvm:vm-%d-disk-%d", vmid, n)
		_, exists := f.disks[volid]
		referenced := false
		if vm := f.vms[vmid]; vm != nil {
			for _, value := range vm.config {
				if text, ok := value.(string); ok && strings.SplitN(text, ",", 2)[0] == volid {
					referenced = true
				}
			}
		}
		if !exists && !referenced {
			return volid
		}
	}
}

func freeUnused(config map[string]any) string {
	return freeKey(config, "unused", 0, 255)
}

func (f *fakePVE) ConfigureVM(ctx context.Context, vmid int, params url.Values) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	vm := f.vms[vmid]
	if vm == nil {
		return "", forbidden(vmid)
	}
	for key := range params {
		value := params.Get(key)
		parts := strings.SplitN(value, ",", 2)
		options := ""
		if len(parts) == 2 {
			options = "," + parts[1]
		}
		switch m := allocation.FindStringSubmatch(parts[0]); {
		case m != nil:
			volid := f.nextDisk(vmid)
			var gib int64
			fmt.Sscan(m[1], &gib)
			f.disks[volid] = gib << 30
			vm.config[key] = fmt.Sprintf("%s%s,size=%dG", volid, options, gib)
		case f.disks[parts[0]] != 0:
			if !strings.HasPrefix(parts[0], fmt.Sprintf("local-lvm:vm-%d-", vmid)) {
				return "", fmt.Errorf("volume %s is not owned by VM %d", parts[0], vmid)
			}
			for other, current := range vm.config {
				if strings.HasPrefix(other, "unused") && current == parts[0] {
					delete(vm.config, other)
				}
			}
			vm.config[key] = fmt.Sprintf("%s%s,size=%dG", parts[0], options, f.disks[parts[0]]>>30)
		default:
			vm.config[key] = value
		}
	}
	return f.task(nil), nil
}

func (f *fakePVE) UnlinkDisks(ctx context.Context, vmid int, keys []string, force bool) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	vm := f.vms[vmid]
	if vm == nil {
		return forbidden(vmid)
	}
	for _, key := range keys {
		value, ok := vm.config[key].(string)
		if !ok {
			return fmt.Errorf("VM %d has no %s", vmid, key)
		}
		if vm.status == "running" && f.refuseUnplug && !strings.HasPrefix(key, "unused") {
			f.pending[vmid] = append(f.pending[vmid], key)
			continue
		}
		delete(vm.config, key)
		volid := strings.SplitN(value, ",", 2)[0]
		if force {
			delete(f.disks, volid)
			delete(f.labels, volid)
		} else if _, disk := f.disks[volid]; disk {
			vm.config[freeUnused(vm.config)] = volid
		}
	}
	return nil
}

func (f *fakePVE) MoveDisk(ctx context.Context, vmid int, disk string, targetVMID int, targetDisk string) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	source, target := f.vms[vmid], f.vms[targetVMID]
	if source == nil || target == nil {
		return "", forbidden(targetVMID)
	}
	value, ok := source.config[disk].(string)
	if !ok {
		return "", fmt.Errorf("VM %d has no %s", vmid, disk)
	}
	if _, taken := target.config[targetDisk]; taken {
		return "", fmt.Errorf("VM %d already has %s", targetVMID, targetDisk)
	}
	old := strings.SplitN(value, ",", 2)[0]
	renamed := f.nextDisk(targetVMID)
	f.disks[renamed], f.labels[renamed] = f.disks[old], f.labels[old]
	delete(f.disks, old)
	delete(f.labels, old)
	delete(source.config, disk)
	target.config[targetDisk] = renamed
	return f.task(nil), nil
}

func (f *fakePVE) VMPending(ctx context.Context, vmid int) ([]proxmox.PendingChange, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	var changes []proxmox.PendingChange
	for _, key := range f.pending[vmid] {
		changes = append(changes, proxmox.PendingChange{Key: key, Delete: 1})
	}
	return changes, nil
}

func (f *fakePVE) FirewallRules(ctx context.Context, vmid int) ([]proxmox.FirewallRule, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.vms[vmid] == nil {
		return nil, forbidden(vmid)
	}
	rules := slices.Clone(f.firewall(vmid).rules)
	for i := range rules {
		rules[i].Pos = i
	}
	return rules, nil
}

func (f *fakePVE) InsertFirewallRule(ctx context.Context, vmid int, rule proxmox.FirewallRule) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.vms[vmid] == nil {
		return forbidden(vmid)
	}
	firewall := f.firewall(vmid)
	firewall.rules = append([]proxmox.FirewallRule{rule}, firewall.rules...)
	return nil
}

func (f *fakePVE) DeleteFirewallRule(ctx context.Context, vmid, pos int) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	firewall := f.firewall(vmid)
	if pos < 0 || pos >= len(firewall.rules) {
		return fmt.Errorf("no rule at position %d", pos)
	}
	firewall.rules = slices.Delete(firewall.rules, pos, pos+1)
	return nil
}

func (f *fakePVE) FirewallOptions(ctx context.Context, vmid int) (map[string]any, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	copied := map[string]any{}
	for key, value := range f.firewall(vmid).options {
		copied[key] = value
	}
	return copied, nil
}

func (f *fakePVE) SetFirewallOptions(ctx context.Context, vmid int, params url.Values) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.vms[vmid] == nil {
		return forbidden(vmid)
	}
	options := f.firewall(vmid).options
	f.firewall(vmid).optionWrites++
	for key := range params {
		if key == "delete" {
			for _, name := range strings.Split(params.Get(key), ",") {
				delete(options, name)
			}
			continue
		}
		options[key] = params.Get(key)
	}
	return nil
}

func (f *fakePVE) IPSets(ctx context.Context, vmid int) ([]string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	var names []string
	for name := range f.firewall(vmid).ipsets {
		names = append(names, name)
	}
	return names, nil
}

func (f *fakePVE) CreateIPSet(ctx context.Context, vmid int, name string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	sets := f.firewall(vmid).ipsets
	if _, exists := sets[name]; exists {
		return fmt.Errorf("IPSet %s already exists", name)
	}
	sets[name] = []string{}
	return nil
}

func (f *fakePVE) IPSetEntries(ctx context.Context, vmid int, name string) ([]string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	entries, exists := f.firewall(vmid).ipsets[name]
	if !exists {
		return nil, fmt.Errorf("no such IPSet %s", name)
	}
	return slices.Clone(entries), nil
}

func (f *fakePVE) AddIPSetEntry(ctx context.Context, vmid int, name, cidr string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	sets := f.firewall(vmid).ipsets
	sets[name] = append(sets[name], cidr)
	return nil
}

func (f *fakePVE) DeleteIPSetEntry(ctx context.Context, vmid int, name, cidr string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	sets := f.firewall(vmid).ipsets
	sets[name] = slices.DeleteFunc(sets[name], func(entry string) bool { return entry == cidr })
	return nil
}
