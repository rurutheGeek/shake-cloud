#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo 'Run this script with sudo.' >&2
  exit 1
fi
. /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo 'Ubuntu/Debian required' >&2; exit 1 ;; esac
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl
install -d -m 0755 /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc
printf 'deb [signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' "$ID" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker info --format '{{.ServerVersion}}'
docker compose version
