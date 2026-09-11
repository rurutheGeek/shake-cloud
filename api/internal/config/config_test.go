package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/accesskey"
)

func write(t *testing.T, name, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func valid(t *testing.T) map[string]string {
	return map[string]string{
		"SHAKECLOUD_PUBLIC_URL":            "http://192.0.2.5:8080",
		"SHAKECLOUD_DATABASE_URL":          "postgres://shakecloud@db/shakecloud",
		"SHAKECLOUD_OIDC_ISSUER":           "http://192.0.2.4:9000/application/o/cloud/",
		"SHAKECLOUD_OIDC_CREDENTIALS_FILE": write(t, "oidc.json", `{"client_id": "cloud", "client_secret": "s3cret"}`),
	}
}

func load(env map[string]string) (Config, error) {
	return Load(func(name string) string { return env[name] })
}

func TestValidSettingsLoadWithDefaults(t *testing.T) {
	cfg, err := load(valid(t))
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Listen != ":8080" || cfg.UserGroup != "cloud-users" || cfg.AdminGroup != "cloud-admins" {
		t.Errorf("unexpected defaults: %+v", cfg)
	}
	if cfg.OIDCClientID != "cloud" || cfg.OIDCClientSecret != "s3cret" {
		t.Errorf("credentials not read")
	}
	if cfg.BootstrapKey != nil {
		t.Errorf("bootstrap key enabled without a file")
	}
}

func TestRedirectURLMatchesTheOneAuthentikRegisters(t *testing.T) {
	// stacks/identity/configure.py registers <portal>/auth/callback, stripping
	// one trailing slash; a double slash would fail Authentik's strict match.
	env := valid(t)
	env["SHAKECLOUD_PUBLIC_URL"] = "http://192.0.2.5:8080/"
	cfg, err := load(env)
	if err != nil {
		t.Fatal(err)
	}
	if got := cfg.RedirectURL(); got != "http://192.0.2.5:8080/auth/callback" {
		t.Errorf("RedirectURL() = %q", got)
	}
	if cfg.SecureCookies() {
		t.Error("plain HTTP must not set Secure cookies, or browsers drop them")
	}
}

func TestEveryMissingSettingIsReportedAtOnce(t *testing.T) {
	_, err := load(map[string]string{})
	if err == nil {
		t.Fatal("empty environment accepted")
	}
	for _, name := range []string{"SHAKECLOUD_PUBLIC_URL", "SHAKECLOUD_DATABASE_URL", "SHAKECLOUD_OIDC_ISSUER", "SHAKECLOUD_OIDC_CREDENTIALS_FILE"} {
		if !strings.Contains(err.Error(), name) {
			t.Errorf("error does not mention %s: %v", name, err)
		}
	}
}

func TestPublicURLMustBeAnOrigin(t *testing.T) {
	for _, value := range []string{"192.0.2.5:8080", "ftp://192.0.2.5", "http://192.0.2.5/portal", "http://192.0.2.5/?x=1"} {
		env := valid(t)
		env["SHAKECLOUD_PUBLIC_URL"] = value
		if _, err := load(env); err == nil {
			t.Errorf("accepted %q", value)
		}
	}
}

func TestOIDCCredentialsErrorsDoNotQuoteTheFile(t *testing.T) {
	env := valid(t)
	env["SHAKECLOUD_OIDC_CREDENTIALS_FILE"] = write(t, "oidc.json", `{"client_id": "cloud", "client_secret": SECRETVALUE`)
	_, err := load(env)
	if err == nil || strings.Contains(err.Error(), "SECRETVALUE") {
		t.Fatalf("got %v", err)
	}
}

func TestTrustedProxies(t *testing.T) {
	env := valid(t)
	env["SHAKECLOUD_TRUSTED_PROXIES"] = "127.0.0.1, 172.16.0.0/12 ,"
	cfg, err := load(env)
	if err != nil {
		t.Fatal(err)
	}
	if len(cfg.TrustedProxies) != 2 || cfg.TrustedProxies[0].String() != "127.0.0.1/32" || cfg.TrustedProxies[1].String() != "172.16.0.0/12" {
		t.Fatalf("TrustedProxies = %v", cfg.TrustedProxies)
	}
	env["SHAKECLOUD_TRUSTED_PROXIES"] = "proxy.example"
	if _, err := load(env); err == nil {
		t.Fatal("a hostname was accepted as a trusted proxy")
	}
}

func TestBootstrapKeyFile(t *testing.T) {
	token := accesskey.New()
	env := valid(t)
	env["SHAKECLOUD_BOOTSTRAP_KEY_FILE"] = write(t, "key", token.String()+"\n")
	cfg, err := load(env)
	if err != nil || cfg.BootstrapKey == nil || *cfg.BootstrapKey != token {
		t.Fatalf("key not loaded: %v", err)
	}

	env["SHAKECLOUD_BOOTSTRAP_KEY_FILE"] = write(t, "empty", "\n")
	if cfg, err := load(env); err != nil || cfg.BootstrapKey != nil {
		t.Fatalf("an empty file must disable the key: %v", err)
	}

	almost := token.String()[:len(token.String())-1]
	env["SHAKECLOUD_BOOTSTRAP_KEY_FILE"] = write(t, "bad", almost)
	_, err = load(env)
	if err == nil || strings.Contains(err.Error(), token.Secret[:20]) {
		t.Fatalf("malformed key must fail without echoing it: %v", err)
	}
}
