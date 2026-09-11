// Package seed builds the NoCloud seed ISO an instance boots with.
//
// Proxmox's upload API does not accept snippets, so user-data cannot reach the
// built-in cloud-init drive through a pool-scoped token. Instead each instance
// gets a CD-ROM labelled CIDATA holding meta-data, user-data and
// network-config, which cloud-init reads on first boot.
//
// The address is written into network-config. Proxmox's ipconfig0 does nothing
// without its own cloud-init drive, so this file is the only place it can go.
package seed

import (
	"crypto/rand"
	"fmt"
	"net/netip"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	diskfs "github.com/diskfs/go-diskfs"
	"github.com/diskfs/go-diskfs/disk"
	"github.com/diskfs/go-diskfs/filesystem"
	"github.com/diskfs/go-diskfs/filesystem/iso9660"
	"go.yaml.in/yaml/v3"
)

// Label is the volume ID cloud-init's NoCloud source looks for.
const Label = "CIDATA"

type Config struct {
	InstanceID  string
	Hostname    string
	MACAddress  string
	Address     netip.Prefix
	Gateway     netip.Addr
	Nameservers []netip.Addr
	UserData    string
}

// NewMACAddress returns a random address under Proxmox's own OUI (BC:24:11),
// the prefix Proxmox itself uses for generated NICs.
func NewMACAddress() string {
	b := make([]byte, 3)
	rand.Read(b)
	return fmt.Sprintf("BC:24:11:%02X:%02X:%02X", b[0], b[1], b[2])
}

var notHostname = regexp.MustCompile(`[^a-z0-9-]+`)

// Hostname turns an instance's Name tag into a DNS label, falling back to the
// instance ID when nothing usable is left.
func Hostname(name, instanceID string) string {
	label := strings.Trim(notHostname.ReplaceAllString(strings.ToLower(name), "-"), "-")
	if len(label) > 63 {
		label = strings.Trim(label[:63], "-")
	}
	if label == "" {
		return instanceID
	}
	return label
}

func (c Config) metaData() ([]byte, error) {
	return yaml.Marshal(map[string]string{"instance-id": c.InstanceID, "local-hostname": c.Hostname})
}

func (c Config) networkConfig() ([]byte, error) {
	type route struct {
		To  string `yaml:"to"`
		Via string `yaml:"via"`
	}
	type ethernet struct {
		Match       map[string]string   `yaml:"match"`
		Addresses   []string            `yaml:"addresses"`
		Routes      []route             `yaml:"routes"`
		Nameservers map[string][]string `yaml:"nameservers"`
	}
	servers := make([]string, 0, len(c.Nameservers))
	for _, server := range c.Nameservers {
		servers = append(servers, server.String())
	}
	return yaml.Marshal(map[string]any{
		"version": 2,
		"ethernets": map[string]ethernet{
			"primary": {
				// Match by MAC: the guest's interface name is not ours to predict.
				Match:       map[string]string{"macaddress": strings.ToLower(c.MACAddress)},
				Addresses:   []string{c.Address.String()},
				Routes:      []route{{To: "default", Via: c.Gateway.String()}},
				Nameservers: map[string][]string{"addresses": servers},
			},
		},
	})
}

// Files returns the seed's contents by file name.
func (c Config) Files() (map[string][]byte, error) {
	if c.InstanceID == "" || c.Hostname == "" || c.MACAddress == "" || !c.Address.IsValid() || !c.Gateway.IsValid() {
		return nil, fmt.Errorf("seed: incomplete config for %q", c.InstanceID)
	}
	meta, err := c.metaData()
	if err != nil {
		return nil, err
	}
	network, err := c.networkConfig()
	if err != nil {
		return nil, err
	}
	user := c.UserData
	if user == "" {
		user = "#cloud-config\n"
	}
	return map[string][]byte{"meta-data": meta, "network-config": network, "user-data": []byte(user)}, nil
}

// Build writes the ISO in workDir and returns its bytes.
func Build(c Config, workDir string) ([]byte, error) {
	files, err := c.Files()
	if err != nil {
		return nil, err
	}
	dir, err := os.MkdirTemp(workDir, "seed-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(dir)
	path := filepath.Join(dir, "seed.iso")
	// go-diskfs stages ISO contents in a directory that must already exist.
	work := filepath.Join(dir, "work")
	if err := os.Mkdir(work, 0o700); err != nil {
		return nil, err
	}

	size := int64(1 << 20)
	for _, content := range files {
		size += int64(len(content))
	}
	image, err := diskfs.Create(path, size, diskfs.SectorSizeDefault)
	if err != nil {
		return nil, fmt.Errorf("seed: create image: %w", err)
	}
	defer image.Close()
	// ISO 9660 only allows 2048, 4096 or 8192 byte logical blocks.
	image.LogicalBlocksize = 2048
	fs, err := image.CreateFilesystem(disk.FilesystemSpec{
		Partition: 0, FSType: filesystem.TypeISO9660, VolumeLabel: Label, WorkDir: filepath.Join(dir, "work"),
	})
	if err != nil {
		return nil, fmt.Errorf("seed: create filesystem: %w", err)
	}
	for name, content := range files {
		file, err := fs.OpenFile("/"+name, os.O_CREATE|os.O_RDWR)
		if err != nil {
			return nil, fmt.Errorf("seed: open %s: %w", name, err)
		}
		if _, err := file.Write(content); err != nil {
			return nil, fmt.Errorf("seed: write %s: %w", name, err)
		}
		if err := file.Close(); err != nil {
			return nil, err
		}
	}
	iso, ok := fs.(*iso9660.FileSystem)
	if !ok {
		return nil, fmt.Errorf("seed: unexpected filesystem %T", fs)
	}
	// Plain ISO 9660 names are upper-case 8.3; cloud-init needs the exact
	// lower-case names with hyphens, which Rock Ridge and Joliet carry.
	if err := iso.Finalize(iso9660.FinalizeOptions{RockRidge: true, Joliet: true, VolumeIdentifier: Label}); err != nil {
		return nil, fmt.Errorf("seed: finalize: %w", err)
	}
	return os.ReadFile(path)
}
