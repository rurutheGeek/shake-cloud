#!/bin/sh
# Flint 3 の設定を毎日 K11 へ取る仕組みを入れる。手元（dev-02）から実行する。何度実行してもよい。
#
#   tools/flint3-backup-install.sh
#
# - K11 に専用の鍵を作り、Flint 3 にはその鍵で「設定のバックアップを出す」ことだけを許す。
# - K11 の /root/flint3-config（git）へ展開してコミットするので、変わった所は git log -p で見られる。
#   sysupgrade -b の tar も /root/flint3-backups に 60 日分残す（復元は sysupgrade -r）。
# - 中身には Wi-Fi のパスワードなどが入る。K11 の root だけが読める。
set -eu

PVE="${PVE_HOST:-192.168.10.10}"
FLINT="${FLINT_HOST:-192.168.10.1}"
KEY="${PVE_SSH_KEY:-$HOME/.ssh/id_ed25519_pve}"

pve() { ssh -o BatchMode=yes -i "$KEY" "root@$PVE" "$@"; }
flint() { ssh -o BatchMode=yes -i "$KEY" "root@$FLINT" "$@"; }

pve "test -f /root/.ssh/flint3_backup || ssh-keygen -q -t ed25519 -N '' -C flint3-backup -f /root/.ssh/flint3_backup"
pubkey="$(pve cat /root/.ssh/flint3_backup.pub)"
line="command=\"sysupgrade -b - 2>/dev/null\",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding $pubkey"
flint "grep -v 'flint3-backup\$' /etc/dropbear/authorized_keys >/tmp/ak; echo '$line' >>/tmp/ak; cat /tmp/ak >/etc/dropbear/authorized_keys; rm /tmp/ak"
pve "ssh-keygen -F $FLINT >/dev/null || ssh-keyscan -t ed25519 $FLINT 2>/dev/null >>/root/.ssh/known_hosts"

pve 'cat >/usr/local/sbin/flint3-backup' <<EOF
#!/bin/sh
# tools/flint3-backup-install.sh が入れる。手で編集しない。
set -eu
umask 077
dir=/root/flint3-backups
repo=/root/flint3-config
mkdir -p "\$dir" "\$repo"
tar="\$dir/flint3-\$(date +%Y%m%d-%H%M%S).tar.gz"
ssh -o BatchMode=yes -i /root/.ssh/flint3_backup root@$FLINT >"\$tar.part"
tar -tzf "\$tar.part" >/dev/null
mv "\$tar.part" "\$tar"
find "\$dir" -name 'flint3-*.tar.gz' -mtime +60 -delete
[ -d "\$repo/.git" ] || git -C "\$repo" init -q
find "\$repo" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
tar -xzf "\$tar" -C "\$repo"
git -C "\$repo" add -A
git -C "\$repo" -c user.name=flint3-backup -c user.email=root@apextox commit -q -m "\$(date '+%F %T')" || true
EOF
pve 'chmod 700 /usr/local/sbin/flint3-backup && command -v git >/dev/null || apt-get install -y -q git >/dev/null'

pve 'cat >/etc/systemd/system/flint3-backup.service' <<'EOF'
[Unit]
Description=Flint 3 の設定を取る
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/flint3-backup
EOF
pve 'cat >/etc/systemd/system/flint3-backup.timer' <<'EOF'
[Unit]
Description=Flint 3 の設定を毎日取る

[Timer]
OnCalendar=*-*-* 04:30
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF
pve 'systemctl daemon-reload && systemctl enable --now flint3-backup.timer >/dev/null && systemctl start flint3-backup.service && ls -l /root/flint3-backups | tail -1 && git -C /root/flint3-config log --oneline | head -1'
