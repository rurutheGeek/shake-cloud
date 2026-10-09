---
title: 公開サイト（Shake-Web / pkhack / Alexa / ayahuya）
updated: 2026-10-09
section: 運用手順
audience: 管理者
tags:
  - ops
  - web
---

# 公開サイト（Shake-Web / pkhack / Alexa / ayahuya）

> **更新日** 2026-10-09 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **web-01 へ移行・公開切替済み（2026-10-05）。** 旧 `shakeserver`（Raspberry Pi 5）で動いていた公開サイトを、クラウドVM `web-01`（192.168.10.102、VMID 5002）へ移し、negitoroserver の中継先も web-01 の tailnet IP（`100.75.249.112`）へ切り替えた（[shake-infra#26](https://github.com/rurutheGeek/shake-infra/pull/26)）。旧ホストの Web コンテナ（`web`・`quiz_app`・`pkhack_app`・`alexa_skill`）は停止し、`restart=no` にしてある。Minecraft（25565）と旧DB（`shake_postgres`）は残したが、**2026-10-09 のセキュリティ対応で Minecraft の2コンテナ（`shake_minecraft-pixelmon1.21.1`・`-backup`）を停止し `restart=no` にした**（旧DBは稼働中。公開方法は未決定）。旧ホストの配備は shake-infra の `web` ロールが正本だったが、移行後はこのリポジトリ（`stacks/shake-web/`）が正本。

## 構成

| サイト | ホスト | 中身 |
| --- | --- | --- |
| `shake.ruruthegeek.dpdns.org` | `web-01` | Shake ブランド（Issues・Shaketter・ToBa・ikura）＋ Wiki。Next.js（`quiz_app`＝コンテナ名 `bsquiz`）と静的 HTML |
| `pkhack.ruruthegeek.dpdns.org` | `web-01` | ポケモンクイズ（Next.js。コンテナ名 `pkhack_app`）と静的ハブ |
| `ayahuya.ruruthegeek.dpdns.org` | `web-01` | アヤフヤハッカーズ（純静的） |
| `ruruthegeek.dpdns.org` | `web-01` | ランディング（静的）と旧URLのリダイレクト |
| Alexa スキル | `web-01` | `alexa_skill`（`127.0.0.1:8010`。公開は nginx 経由の `/alexa/`） |

| 項目 | 値 |
| --- | --- |
| 配備先 | web-01（`192.168.10.102`）。Compose と `.env` は `/opt/shake-web`、ソース・静的物・ログ・証明書は `/srv/shake-web`（データディスク） |
| イメージ | nginx・`shake-web-quiz:local`・`shake-web-pkhack:local`・`shake-web-alexa:local`（アプリはホストでビルドするため digest 固定は無い） |
| DB | `pkdb.apextox.dpdns.org:5432`（apps-01）。`sleepy_pkdb`・`shakeweb`・`pkhack`。旧ホストの `host.docker.internal` から切り替えた |
| 入口（現在） | Cloudflare → `negitoroserver`（`100.92.253.28`）の nginx stream（443・PROXY protocol）と sslh（80）→ **web-01 の tailnet IP `100.75.249.112`**。web-01 は tailnet 端末（`--accept-dns=false`、ルートは受けない）。プロキシには LAN のサブネットルートを持たせない |
| 入口（予定） | core-01 の Caddy へ寄せる（[edge.md](edge.md)）。名前は `ruruthegeek.dpdns.org` ゾーンのまま |
| 秘密値 | `platform/sops/shake-web.sops.yaml`（Deploy key 3本・CloudFlare Origin 証明鍵・DB パスワード・セッション鍵） |
| コード | `stacks/shake-web/`、`platform/ansible/roles/shake_web/`、`platform/ansible/shake-web.yml`、`platform/terraform/services/web/` |
| 監視 | node_exporter（`192.168.10.102:9100`）。Prometheus の `node-targets.yml` に登録済み |

## 配備

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook \
     -i platform/ansible/inventory.netbox.yml platform/ansible/shake-web.yml'
```

`manage.py` の流れ: `init`（保存先とデータディスクのマウント確認）→ `fetch`（4リポジトリを `.env` の ref へ）→ `sync`（nginx が配る静的物をコピー）→ `up`（`docker compose up -d --build`）。

- 追う ref は `roles/shake_web/defaults/main.yml` の `shake_web_*_ref`（既定 `main`）。
- アプリの更新は「Ansible を流し直す」だけ。手元で `docker compose` を叩かない。
- **web-01 が5分ごとに `main` を見て自分で更新する**（`shake-web-update.timer`。旧ホスト向け CD の代わり。UBSLEEPY と同じ方式）。即時に反映したいときは `ssh debian@192.168.10.102 'sudo systemctl start shake-web-update'`。
- ビルドに失敗したら `ssh debian@192.168.10.102 'sudo python3 /opt/shake-web/manage.py status'` と `sudo docker logs pkhack_app --tail 50` を見る。

## 公開の切り替え（2026-10-05 実施済み）

1. `shake-infra#26` で `negitoroserver` の `stream_proxy.conf`（443）と `sslh`（80）の向き先を web-01 の tailnet IP へ変更した。
2. GitHub Actions「アプリからの自動デプロイ」→ `target=proxy` で適用し、HSTS ヘッダで切替を確認した。
3. 旧ホストの Web コンテナを停止し、`restart=no` にした（ボリュームは残す）。
4. **2026-10-09 追記**: shake-infra のセルフホストランナーを廃止したため、CD（repository_dispatch → `deploy_shakeweb` など）はもう動かない（ワークフローは残置）。公開サイトの更新は web-01 の `shake-web-update.timer`（5分ごと）だけ。中継ノードの配備は `public-relay.yml` が引き継いだ。

## 既知の不具合

- `pkhack` の practice 3本（`langquiz/practice`・`bsquiz/practice`・`abilityquiz/practice`）は **旧ホストでも 500**。クエリが存在しない `POKEMON_NAMES` を参照する、`mv_quiz_status` に無い種族値・特性の列を読む、が原因。移行とは無関係の既存不具合。
- 2026-10-05 の移行で pkhack の SQL を小文字スキーマへ合わせた（[pkhack#7](https://github.com/rurutheGeek/pkhack/pull/7)、merge 済み）。web-01 は main から fetch して動く。

## 守り（外部公開の前提・2026-10-05 に強化）

- セキュリティグループは既定で拒否。許可は LAN から 22、入口（core-01）と公開中継（negitoroserver）から 80/443、monitor-01 から 9100 だけ。LAN の dev-02 から 80/443/8443/3000/8010/9100 が閉じていることを実測した。
- SSH は鍵のみ（`PasswordAuthentication no`・`KbdInteractiveAuthentication no`・root は `without-password`）。`unattended-upgrades` は有効。
- nginx は `server_tokens off`、TLS1.2 以上（TLS1.1 は拒否を実測）、`X-Content-Type-Options`・`X-Frame-Options`・`Referrer-Policy`・HSTS を全サイトへ付与（`stacks/shake-web/nginx/00-security.conf.template`）。8443 はホストの 127.0.0.1 にだけ公開。
- Docker は json-file を `max-size=10m`・`max-file=3` に制限し、全サービスに `no-new-privileges` を付与。アプリのポートは `127.0.0.1` のみ。
- クイズのトークン暗号鍵 `QUIZ_SECRET` を SOPS に追加し、`platform/sops/shake-web.sops.yaml` から配る（pkhack のコードは既定値フォールバックを削除。`QUIZ_SECRET` 未設定なら起動しない）。
- 残りのリスク: ① negitoroserver は Cloudflare 以外からも直接 443 を受ける（Cloudflare IP の許可リストは shake-infra 側の改善）。② 旧ホストの停止済みデプロイと pkhack の履歴には DB パスワードが残る。`pkdb_reader` のローテーションを推奨。

### 外向き（egress）と自宅LANの分離

公開サイトが突破されても自宅LANへ横展開できないように、SG の外向きも既定拒否にしている。許可はコード（`platform/terraform/services/web/main.tf`）が正本。

- 許可: DNS（53 tcp/udp → `192.168.10.1`）、NTP（123/udp → 全）、pkdb（5432/tcp → `192.168.10.105`）、HTTP/HTTPS（80/443 → 全）。
- 実測（2026-10-05）: PVE の `8006`・SSH `22`、Garage `3900`、NetBox `8000`、他VMへ届かない。pkdb とインターネット 443 は OK。
- GitHub への git は 22 ではなく `ssh.github.com:443` を使う（`manage.py` が指定）。
- 新しい SG は EC2 と同じで外向きが全許可。既定の「全許可」2本（`0.0.0.0/0`・`::/0` の all）は作成後に import して削除してある。**SG を作り直したときは既定が戻る**ので、`shake_web` ロールが配備のたびに確認して revoke する。
- IPv6 の外向きは開けない（LAN 側の IPv6 へ届かせないため）。
- ゲスト側にも nftables の一段（`/etc/nftables.conf` の `inet homeguard`）を置き、**LAN 宛の 80/443 を output と forward の両方で drop** する。SG は宛先 IP の除外を書けないため、ルータの LuCI・入口 core-01 の Caddy・AP の管理画面（いずれも LAN の 80/443）へアプリから届くのをここで塞ぐ。実測（2026-10-05）: `192.168.10.1:80/443`・`192.168.10.200:443`・`192.168.10.2:80` は web-01 から閉じ、pkdb・DNS・インターネット 443 は開いている。policy は accept のままで、Docker の転送や他の通信には触らない。

### プロキシ（negitoroserver）側

公開の中継は、旧ホストと同じく **tailnet の端末間**で行う。web-01 は tailnet に入り（`100.75.249.112`）、プロキシはその tailnet IP を直接指す。プロキシには LAN のサブネットルート（`accept-routes`）を持たせない。これで、プロキシが突破されても届くのは tailnet 上だけで、LAN 全体へのルートは持たない。

**Tailscale の ACL は `platform/tailscale/policy.yaml` が正本で、2026-10-09 に適用した**（[Tailscale](net.md)）。`negitoroserver` には `tag:relay` を付け、届く先は `web-01`（`tag:web`）の 80/443 だけ。`tag:relay` には LAN のサブネットルートも SSH も無い。管理コンソールで直接編集せず、差分があれば `tools/tailscale-net.py apply` で戻す。

**中継ノードの配備は `platform/ansible/public-relay.yml`（ロール `public_relay`、`outpost.ini` の `relay`）が正本。** 2026-10-09 に shake-infra の `proxy` ロールから移した（shake-infra のセルフホストランナー廃止のため）。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_shake .venv/bin/ansible-playbook \
     -i platform/ansible/outpost.ini platform/ansible/public-relay.yml'
```

- sshd はパスワード認証を閉じる（cloud-init の `50-cloud-init.conf` より先に読ませる drop-in で上書き）。
- ufw は **SSH は `tailscale0` だけ、80 は全体、443 は Cloudflare の公開IPレンジだけ**。443 を直結されると PROXY protocol のクライアントIPを偽装できるため、許可しない。レンジは配備時に Cloudflare の公開リストと比べ、違えば失敗する（`public_relay_cloudflare_ipv4` / `_ipv6` を更新して再実行）。
- `tailscale --accept-routes` は無効（LAN のルートを持たない）。Minecraft（25565）への中継は無い。

### プロキシ（negitoroserver）の侵害に備えて

- 中継は DERP リレー（443）でも成立する。直通 UDP を開けていないため、状況により中継経由になる（機能は同じ）。

## 外からの監視（たらこサーバ）

ミニPC（K11）が落ちても気づけるよう、**たらこサーバ（Pi 4）** が外から見張る。`platform/ansible/public-monitor.yml` とロール `public_monitor`（`outpost.ini`、`ansible_admin`）で、1分ごとに次を確認し、**状態が変わったときだけ** Discord へ通知する（通知先は `platform/sops/public-monitor.sops.yaml`）。

- 公開サイト: `shake`・`pkhack`・`ayahuya`・ルート
- 監視の入口: `grafana.apextox.dpdns.org`（monitor-01）

たらこサーバから LAN へ出る通信は `home-egress.yml` で止めてあり、通すのはこの監視が見る入口（core-01 の 443）だけ。

コードとユーザーは [配備台帳](handover.md) を参照。状態はたらこサーバの `/var/lib/public-monitor/` に残る。

## 検証

```bash
tools/tf services/web output
ssh debian@192.168.10.102 'systemctl is-active web-data-mount.service docker; findmnt /srv'
ssh debian@192.168.10.102 'sudo docker ps; curl -sk --resolve pkhack.ruruthegeek.dpdns.org:8443:127.0.0.1 \
  "https://pkhack.ruruthegeek.dpdns.org:8443/quiz/api/langquiz/names?lang=JPN"'
```
