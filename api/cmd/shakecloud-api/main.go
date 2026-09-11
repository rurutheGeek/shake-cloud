// Command shakecloud-api serves the shake-cloud API and portal.
//
//	shakecloud-api              run the server (settings: internal/config)
//	shakecloud-api healthcheck  exit 0 when /healthz answers; for the container
//	                            health check, since the image has no shell or curl
package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/compute"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/config"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/db"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/netbox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/proxmox"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/server"
	"github.com/rurutheGeek/shake-cloud/cloud/api/internal/site"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		os.Exit(healthcheck())
	}
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if err := run(log); err != nil {
		log.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run(log *slog.Logger) error {
	cfg, err := config.Load(os.Getenv)
	if err != nil {
		return fmt.Errorf("configuration: %w", err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	pool, err := db.Open(ctx, cfg.DatabaseURL, cfg.DatabasePassword)
	if err != nil {
		return err
	}
	defer pool.Close()
	if err := waitForDatabase(ctx, pool.Ping, log); err != nil {
		return err
	}
	applied, err := db.Migrate(ctx, pool)
	if err != nil {
		return err
	}
	log.Info("database ready", "applied_migrations", applied)

	srv := server.New(cfg, pool, log)
	if err := srv.ReconcileBootstrapKey(ctx); err != nil {
		return err
	}
	go srv.RunJanitor(ctx)

	if cfg.ComputeConfigured() {
		deployment, err := site.Load(cfg.SiteFile)
		if err != nil {
			return err
		}
		service := compute.New(pool,
			proxmox.New(cfg.ProxmoxURL, cfg.ProxmoxToken, deployment.Node, cfg.ProxmoxInsecure),
			netbox.New(cfg.NetBoxURL, cfg.NetBoxToken),
			deployment, log, cfg.WorkDir)
		service.UploadDir = cfg.UploadDir
		srv.Compute = service
		go service.RunWorker(ctx)
		go service.RunReconciler(ctx, time.Minute)
		log.Info("instances enabled", "node", deployment.Node, "pool", deployment.Pool,
			"vmid_range", fmt.Sprintf("%d-%d", deployment.VMIDFrom, deployment.VMIDTo), "images", len(deployment.Images))
	} else {
		log.Warn("instances disabled: no Proxmox, NetBox or site settings")
	}

	httpServer := &http.Server{
		Addr:              cfg.Listen,
		Handler:           srv.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      60 * time.Second,
		IdleTimeout:       120 * time.Second,
	}
	failed := make(chan error, 1)
	go func() { failed <- httpServer.ListenAndServe() }()
	log.Info("listening", "addr", cfg.Listen, "public_url", cfg.PublicURL.String())

	select {
	case err := <-failed:
		return err
	case <-ctx.Done():
	}
	log.Info("shutting down")
	shutdown, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(shutdown); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

// waitForDatabase rides out PostgreSQL still starting after a host reboot.
func waitForDatabase(ctx context.Context, ping func(context.Context) error, log *slog.Logger) error {
	deadline := time.Now().Add(90 * time.Second)
	for {
		attempt, cancel := context.WithTimeout(ctx, 3*time.Second)
		err := ping(attempt)
		cancel()
		if err == nil {
			return nil
		}
		if time.Now().After(deadline) || ctx.Err() != nil {
			return fmt.Errorf("database unreachable: %w", err)
		}
		log.Warn("waiting for database", "err", err)
		time.Sleep(2 * time.Second)
	}
}

func healthcheck() int {
	host, port, err := net.SplitHostPort(os.Getenv("SHAKECLOUD_LISTEN"))
	if err != nil {
		host, port = "", "8080"
	}
	if host == "" || host == "0.0.0.0" || host == "::" {
		host = "127.0.0.1"
	}
	client := &http.Client{Timeout: 3 * time.Second}
	response, err := client.Get("http://" + net.JoinHostPort(host, port) + "/healthz")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	response.Body.Close()
	if response.StatusCode != http.StatusOK {
		fmt.Fprintln(os.Stderr, "healthz:", response.Status)
		return 1
	}
	return 0
}
