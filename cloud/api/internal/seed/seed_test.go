package seed

import (
	"net/netip"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"github.com/diskfs/go-diskfs/backend/file"
	"github.com/diskfs/go-diskfs/filesystem/iso9660"
	"go.yaml.in/yaml/v3"
)

func config() Config {
	return Config{
		InstanceID:  "i-0123456789abcdef0",
		Hostname:    "web",
		MACAddress:  "BC:24:11:AA:BB:CC",
		Address:     netip.MustParsePrefix("192.168.10.100/24"),
		Gateway:     netip.MustParseAddr("192.168.10.1"),
		Nameservers: []netip.Addr{netip.MustParseAddr("192.168.10.1")},
		UserData:    "#cloud-config\npackages: [nginx]\n",
	}
}

func TestTheISOCarriesTheExactNamesCloudInitReads(t *testing.T) {
	raw, err := Build(config(), t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	// Set to inspect the image with another tool (xorriso, pycdlib).
	if dump := os.Getenv("SHAKECLOUD_SEED_DUMP"); dump != "" {
		_ = os.WriteFile(dump, raw, 0o600)
	}
	path := filepath.Join(t.TempDir(), "seed.iso")
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	storage, err := file.OpenFromPath(path, true)
	if err != nil {
		t.Fatal(err)
	}
	defer storage.Close()
	fs, err := iso9660.Read(storage, int64(len(raw)), 0, 2048)
	if err != nil {
		t.Fatal(err)
	}
	if label := strings.TrimRight(fs.Label(), "\x00 "); label != Label {
		t.Errorf("label = %q, want %q", label, Label)
	}
	for _, name := range []string{"meta-data", "user-data", "network-config"} {
		content, err := fs.ReadFile(name)
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		if len(content) == 0 {
			t.Errorf("%s is empty", name)
		}
	}
	user, _ := fs.ReadFile("user-data")
	if string(user) != config().UserData {
		t.Errorf("user-data = %q", user)
	}
}

func TestNetworkConfigPinsTheAddressToTheNIC(t *testing.T) {
	files, err := config().Files()
	if err != nil {
		t.Fatal(err)
	}
	var network struct {
		Version   int `yaml:"version"`
		Ethernets map[string]struct {
			Match       map[string]string   `yaml:"match"`
			Addresses   []string            `yaml:"addresses"`
			Routes      []map[string]string `yaml:"routes"`
			Nameservers map[string][]string `yaml:"nameservers"`
		} `yaml:"ethernets"`
	}
	if err := yaml.Unmarshal(files["network-config"], &network); err != nil {
		t.Fatal(err)
	}
	primary := network.Ethernets["primary"]
	if network.Version != 2 || primary.Match["macaddress"] != "bc:24:11:aa:bb:cc" ||
		primary.Addresses[0] != "192.168.10.100/24" || primary.Routes[0]["via"] != "192.168.10.1" ||
		primary.Nameservers["addresses"][0] != "192.168.10.1" {
		t.Fatalf("network-config = %s", files["network-config"])
	}
	var meta map[string]string
	if err := yaml.Unmarshal(files["meta-data"], &meta); err != nil || meta["instance-id"] != "i-0123456789abcdef0" || meta["local-hostname"] != "web" {
		t.Fatalf("meta-data = %s (%v)", files["meta-data"], err)
	}
}

func TestWindowsGetsNetworkConfigV1ForCloudbaseInit(t *testing.T) {
	c := config()
	c.GuestOS = OSWindows
	files, err := c.Files()
	if err != nil {
		t.Fatal(err)
	}
	// cloudbase-init's NoCloud service implements static networking only in
	// cloud-init's network config v1 (a Linux guest keeps v2).
	var network struct {
		Version int `yaml:"version"`
		Config  []struct {
			Type       string `yaml:"type"`
			Name       string `yaml:"name"`
			MACAddress string `yaml:"mac_address"`
			Subnets    []struct {
				Type    string `yaml:"type"`
				Address string `yaml:"address"`
				Netmask string `yaml:"netmask"`
				Gateway string `yaml:"gateway"`
			} `yaml:"subnets"`
			Address []string `yaml:"address"`
		} `yaml:"config"`
	}
	if err := yaml.Unmarshal(files["network-config"], &network); err != nil {
		t.Fatal(err)
	}
	if network.Version != 1 || len(network.Config) != 2 {
		t.Fatalf("network-config = %s", files["network-config"])
	}
	physical := network.Config[0]
	if physical.Type != "physical" || physical.Name != "eth0" || physical.MACAddress != "bc:24:11:aa:bb:cc" {
		t.Fatalf("physical = %+v", physical)
	}
	subnet := physical.Subnets[0]
	if subnet.Type != "static" || subnet.Address != "192.168.10.100" ||
		subnet.Netmask != "255.255.255.0" || subnet.Gateway != "192.168.10.1" {
		t.Fatalf("subnet = %+v", subnet)
	}
	nameserver := network.Config[1]
	if nameserver.Type != "nameserver" || len(nameserver.Address) != 1 || nameserver.Address[0] != "192.168.10.1" {
		t.Fatalf("nameserver = %+v", nameserver)
	}
}

func TestAnEmptyUserDataIsStillACloudConfig(t *testing.T) {
	c := config()
	c.UserData = ""
	files, err := c.Files()
	if err != nil || string(files["user-data"]) != "#cloud-config\n" {
		t.Fatalf("user-data = %q, %v", files["user-data"], err)
	}
}

func TestIncompleteConfigIsRefused(t *testing.T) {
	c := config()
	c.Address = netip.Prefix{}
	if _, err := c.Files(); err == nil {
		t.Fatal("a seed without an address was built")
	}
}

func TestHostnameIsAUsableLabel(t *testing.T) {
	for name, want := range map[string]string{
		"Web Server 1":          "web-server-1",
		"日本語":                   "i-1",
		"--x--":                 "x",
		"":                      "i-1",
		strings.Repeat("a", 80): strings.Repeat("a", 63),
	} {
		if got := Hostname(name, "i-1"); got != want {
			t.Errorf("Hostname(%q) = %q, want %q", name, got, want)
		}
	}
}

func TestMACAddressesAreProxmoxStyle(t *testing.T) {
	pattern := regexp.MustCompile(`^BC:24:11:[0-9A-F]{2}:[0-9A-F]{2}:[0-9A-F]{2}$`)
	if a, b := NewMACAddress(), NewMACAddress(); !pattern.MatchString(a) || a == b {
		t.Fatalf("MACs %q %q", a, b)
	}
}
