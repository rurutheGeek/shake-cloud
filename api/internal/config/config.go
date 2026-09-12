// Package config reads the API's settings from the environment.
//
// Secrets arrive as files (compose secrets), never as environment values, so
// they do not show up in `docker inspect` or a process listing.
package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/netip"
	"net/url"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/accesskey"
)

type Config struct {
	Listen string
	// PublicURL is the origin browsers use, e.g. http://192.168.10.205:8080.
	// The OIDC redirect URI and the cookie Secure flag derive from it.
	PublicURL        *url.URL
	DatabaseURL      string
	DatabasePassword string
	OIDCIssuer       string
	OIDCClientID     string
	OIDCClientSecret string
	UserGroup        string
	AdminGroup       string
	SessionTTL       time.Duration
	// TrustedProxies are the peers whose X-Forwarded-For is believed: the TLS
	// proxy in front of the API. Empty means the socket address is the client.
	TrustedProxies []netip.Prefix
	// BootstrapKey is nil when no key file is configured or the file is
	// empty; either way the bootstrap key is revoked at startup.
	BootstrapKey *accesskey.Token

	// Instance settings. Either all of them are present, or none: without them
	// the instance endpoints answer 503 and the API still serves logins, keys
	// and the audit log.
	ProxmoxURL      string
	ProxmoxToken    string
	ProxmoxInsecure bool
	NetBoxURL       string
	NetBoxToken     string
	SiteFile        string
	// WorkDir is where seed ISOs are built. It must be writable.
	WorkDir string
	// UploadDir is disk-backed space for an uploaded image on its way to the
	// node. It must not be WorkDir, which is a tmpfs: images do not fit in RAM.
	// Empty means uploads are refused, which is better than filling memory.
	UploadDir string

	// Object storage (Garage). Optional as a group: without all of them the
	// bucket endpoints answer 503 and everything else still works.
	GarageAdminURL   string
	GarageAdminToken string
	GarageS3Endpoint string
	GarageS3Region   string

	// Kubernetes (database). Optional as a group: without all of them the
	// database endpoints answer 503.
	K8sURL   string
	K8sCA    string
	K8sToken string
}

// KubernetesConfigured reports whether the database endpoints can run.
func (c Config) KubernetesConfigured() bool {
	return c.K8sURL != "" && c.K8sCA != "" && c.K8sToken != ""
}

// StorageConfigured reports whether the bucket endpoints can run.
func (c Config) StorageConfigured() bool {
	return c.GarageAdminURL != "" && c.GarageAdminToken != "" && c.GarageS3Endpoint != ""
}

// ComputeConfigured reports whether the instance endpoints can run.
func (c Config) ComputeConfigured() bool {
	return c.ProxmoxURL != "" && c.ProxmoxToken != "" && c.NetBoxURL != "" && c.NetBoxToken != "" && c.SiteFile != ""
}

// Load reports every problem at once so a broken deployment is fixed in one pass.
func Load(getenv func(string) string) (Config, error) {
	var errs []error
	required := func(name string) string {
		value := getenv(name)
		if value == "" {
			errs = append(errs, fmt.Errorf("%s is required", name))
		}
		return value
	}
	cfg := Config{
		Listen:      withDefault(getenv("SHAKECLOUD_LISTEN"), ":8080"),
		DatabaseURL: required("SHAKECLOUD_DATABASE_URL"),
		OIDCIssuer:  required("SHAKECLOUD_OIDC_ISSUER"),
		UserGroup:   withDefault(getenv("SHAKECLOUD_USER_GROUP"), "cloud-users"),
		AdminGroup:  withDefault(getenv("SHAKECLOUD_ADMIN_GROUP"), "cloud-admins"),
		SessionTTL:  12 * time.Hour,
	}

	if raw := required("SHAKECLOUD_PUBLIC_URL"); raw != "" {
		origin, err := url.Parse(raw)
		if err != nil || (origin.Scheme != "http" && origin.Scheme != "https") || origin.Host == "" ||
			strings.TrimSuffix(origin.Path, "/") != "" || origin.RawQuery != "" || origin.Fragment != "" {
			errs = append(errs, errors.New("SHAKECLOUD_PUBLIC_URL must be an http(s) origin such as http://192.0.2.5:8080"))
		} else {
			origin.Path = ""
			cfg.PublicURL = origin
		}
	}

	if path := getenv("SHAKECLOUD_DATABASE_PASSWORD_FILE"); path != "" {
		value, err := readSecret(path)
		if err != nil {
			errs = append(errs, err)
		}
		cfg.DatabasePassword = value
	}

	if path := required("SHAKECLOUD_OIDC_CREDENTIALS_FILE"); path != "" {
		id, secret, err := readOIDCCredentials(path)
		if err != nil {
			errs = append(errs, err)
		}
		cfg.OIDCClientID, cfg.OIDCClientSecret = id, secret
	}

	if raw := getenv("SHAKECLOUD_SESSION_TTL"); raw != "" {
		ttl, err := time.ParseDuration(raw)
		if err != nil || ttl <= 0 {
			errs = append(errs, errors.New("SHAKECLOUD_SESSION_TTL must be a positive duration such as 12h"))
		} else {
			cfg.SessionTTL = ttl
		}
	}

	for _, raw := range strings.Split(getenv("SHAKECLOUD_TRUSTED_PROXIES"), ",") {
		if raw = strings.TrimSpace(raw); raw == "" {
			continue
		}
		prefix, err := netip.ParsePrefix(raw)
		if err != nil {
			addr, addrErr := netip.ParseAddr(raw)
			if addrErr != nil {
				errs = append(errs, fmt.Errorf("SHAKECLOUD_TRUSTED_PROXIES: %q is not an IP address or CIDR", raw))
				continue
			}
			prefix = netip.PrefixFrom(addr, addr.BitLen())
		}
		cfg.TrustedProxies = append(cfg.TrustedProxies, prefix.Masked())
	}

	cfg.ProxmoxURL = strings.TrimRight(getenv("SHAKECLOUD_PROXMOX_URL"), "/")
	cfg.NetBoxURL = strings.TrimRight(getenv("SHAKECLOUD_NETBOX_URL"), "/")
	cfg.SiteFile = getenv("SHAKECLOUD_SITE_FILE")
	cfg.WorkDir = withDefault(getenv("SHAKECLOUD_WORK_DIR"), os.TempDir())
	cfg.UploadDir = getenv("SHAKECLOUD_UPLOAD_DIR")
	// Object storage (Garage). Optional: without it the bucket endpoints 503.
	cfg.GarageAdminURL = strings.TrimRight(getenv("SHAKECLOUD_GARAGE_ADMIN_URL"), "/")
	cfg.GarageS3Endpoint = strings.TrimRight(getenv("SHAKECLOUD_GARAGE_S3_ENDPOINT"), "/")
	cfg.GarageS3Region = withDefault(getenv("SHAKECLOUD_GARAGE_S3_REGION"), "garage")
	// Kubernetes (database). Optional: without it the database endpoints 503.
	cfg.K8sURL = strings.TrimRight(getenv("SHAKECLOUD_K8S_URL"), "/")
	if raw := getenv("SHAKECLOUD_PROXMOX_INSECURE"); raw != "" {
		insecure, parseErr := strconv.ParseBool(raw)
		if parseErr != nil {
			errs = append(errs, errors.New("SHAKECLOUD_PROXMOX_INSECURE must be true or false"))
		}
		cfg.ProxmoxInsecure = insecure
	}
	for name, target := range map[string]*string{
		"SHAKECLOUD_PROXMOX_TOKEN_FILE":      &cfg.ProxmoxToken,
		"SHAKECLOUD_NETBOX_TOKEN_FILE":       &cfg.NetBoxToken,
		"SHAKECLOUD_GARAGE_ADMIN_TOKEN_FILE": &cfg.GarageAdminToken,
		"SHAKECLOUD_K8S_CA_FILE":             &cfg.K8sCA,
		"SHAKECLOUD_K8S_TOKEN_FILE":          &cfg.K8sToken,
	} {
		if path := getenv(name); path != "" {
			value, err := readSecret(path)
			if err != nil {
				errs = append(errs, err)
			}
			*target = value
		}
	}
	// Half-configured instances would fail on the first launch instead of at
	// startup, so refuse the deployment now.
	settings := map[string]string{
		"SHAKECLOUD_PROXMOX_URL":        cfg.ProxmoxURL,
		"SHAKECLOUD_PROXMOX_TOKEN_FILE": cfg.ProxmoxToken,
		"SHAKECLOUD_NETBOX_URL":         cfg.NetBoxURL,
		"SHAKECLOUD_NETBOX_TOKEN_FILE":  cfg.NetBoxToken,
		"SHAKECLOUD_SITE_FILE":          cfg.SiteFile,
	}
	var missing []string
	for name, value := range settings {
		if value == "" {
			missing = append(missing, name)
		}
	}
	if len(missing) > 0 && len(missing) < len(settings) {
		sort.Strings(missing)
		errs = append(errs, fmt.Errorf("instances need every setting or none; missing: %s", strings.Join(missing, ", ")))
	}

	if path := getenv("SHAKECLOUD_BOOTSTRAP_KEY_FILE"); path != "" {
		value, err := readSecret(path)
		switch {
		case err != nil:
			errs = append(errs, err)
		case value != "":
			token, err := accesskey.Parse(value)
			if err != nil {
				// Never echo the file: a near-miss is still most of a secret.
				errs = append(errs, fmt.Errorf("%s does not hold an sca_ access key", path))
			} else {
				cfg.BootstrapKey = &token
			}
		}
	}

	return cfg, errors.Join(errs...)
}

// RedirectURL must equal the redirect URI stacks/identity/configure.py registers.
func (c Config) RedirectURL() string { return c.PublicURL.String() + "/auth/callback" }

// SecureCookies is false only while the portal is served over plain HTTP on the LAN.
func (c Config) SecureCookies() bool { return c.PublicURL.Scheme == "https" }

func withDefault(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func readSecret(path string) (string, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read secret file: %w", err)
	}
	return strings.TrimSpace(string(content)), nil
}

// readOIDCCredentials reads the identity VM's secrets/oidc-cloud.json as copied
// by the cloud_api Ansible role, so the file has exactly one format.
func readOIDCCredentials(path string) (string, string, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return "", "", fmt.Errorf("read OIDC credentials: %w", err)
	}
	var credentials struct {
		ClientID     string `json:"client_id"`
		ClientSecret string `json:"client_secret"`
	}
	// The decoder's error can quote the input, so replace it wholesale.
	if json.Unmarshal(content, &credentials) != nil || credentials.ClientID == "" || credentials.ClientSecret == "" {
		return "", "", fmt.Errorf("%s must be JSON with client_id and client_secret", path)
	}
	return credentials.ClientID, credentials.ClientSecret, nil
}
