---
title: 公開サイト（Shake-Web / pkhack / Alexa / ayahuya）
updated: 2026-10-16
section: 運用手順
audience: 管理者
tags:
  - ops
  - web
---

# 公開サイト（Shake-Web / pkhack / Alexa / ayahuya）

> **更新日** 2026-10-16 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **DMZ の shakeserver（Raspberry Pi 5、`192.168.30.12`）で公開中（2026-10-16〜）。** 中継（negitoroserver）は Pi 5 の tailnet IP（`100.116.167.59`）を指す。2026-10-05〜16 に使った web-01（クラウドVM）は 2026-10-16 に消した。

## 構成

| サイト | ホスト | 中身 |
| --- | --- | --- |
| `shake.ruruthegeek.dpdns.org` | `shakeserver`（Pi 5、DMZ） | Shake ブランド（Issues・Shaketter・ToBa・ikura）＋ Wiki。Next.js（`quiz_app`＝コンテナ名 `bsquiz`）と静的 HTML |
| `pkhack.ruruthegeek.dpdns.org` | `shakeserver` | ポケモンクイズ（Next.js。コンテナ名 `pkhack_app`）と静的ハブ |
| `ayahuya.ruruthegeek.dpdns.org` | `shakeserver` | アヤフヤハッカーズ（純静的） |
| `ruruthegeek.dpdns.org` | `shakeserver` | ランディング（静的）と旧URLのリダイレクト |
| Alexa スキル | `shakeserver` | `alexa_skill`（`127.0.0.1:8010`。公開は nginx 経由の `/alexa/`） |

| 項目 | 値 |
| --- | --- |
| 配備先 | shakeserver（Pi 5、DMZ `192.168.30.12`、`outpost.ini` の `web`）。`.venv/bin/ansible-playbook -i platform/ansible/outpost.ini --private-key ~/.ssh/id_ed25519_shake platform/ansible/shake-web.yml`。Compose と `.env` は `/opt/shake-web`、ソース・静的物・ログ・証明書は `/srv/shake-web`（NVMe） |
| イメージ | nginx・`shake-web-quiz:local`・`shake-web-pkhack:local`・`shake-web-alexa:local`（アプリはホストでビルドするため digest 固定は無い） |
| DB | `pkdb.apextox.dpdns.org:5432`（apps-01）。DMZ からは Flint 3 の `DMZ-to-pkdb`（`dmz-db-clients`）と apps-01 のセキュリティグループ（`pkdb_dmz`）で Pi 5 だけ通す。`sleepy_pkdb`・`shakeweb`・`pkhack`。旧ホストの `host.docker.internal` から切り替えた |
| 入口（現在） | Cloudflare → `negitoroserver`（`100.92.253.28`）の nginx stream（443・PROXY protocol）と sslh（80）→ **shakeserver の tailnet IP `100.116.167.59`**（`roles/relay/defaults/main.yml`）。Tailscale の ACL は `tag:relay` → `tag:dmz:80,443` だけ。プロキシには LAN のサブネットルートを持たせない |
| 入口（予定） | core-01 の Caddy へ寄せる（[edge.md](edge.md)）。名前は `ruruthegeek.dpdns.org` ゾーンのまま |
| 秘密値 | `platform/sops/shake-web.sops.yaml`（Deploy key 2本・CloudFlare Origin 証明鍵・DB パスワード・セッション鍵・GHCR 読み取り用のマシンユーザーのトークン） |
| コード | `stacks/shake-web/`、`platform/ansible/roles/shake_web/`、`platform/ansible/shake-web.yml`、守りは `platform/ansible/host_vars/shakeserver.yml`（`pi_base_lan_guard`） |
| 監視 | node_exporter（`192.168.30.12:9100`）。Prometheus の `node-targets.yml` に登録済み。外からは negitoroserver の public-monitor |

## 配備

```bash
.venv/bin/ansible-playbook -i platform/ansible/outpost.ini \
  --private-key ~/.ssh/id_ed25519_shake platform/ansible/shake-web.yml
```

`manage.py` の流れ: `init`（保存先とデータディスクのマウント確認）→ `fetch`（3リポジトリを `.env` の ref へ）→ `sync`（nginx が配る静的物をコピー）→ `pull`（CI がビルドしたイメージを取ってくる）→ `up`（`docker compose up -d --build`）。

- 追う ref は `roles/shake_web/defaults/main.yml` の `shake_web_*_ref`（既定 `main`）。
- **ayahuya はソースではなく、ayahuya の CI（`.github/workflows/image.yml`）がビルドしたイメージ `ghcr.io/ruruthegeek/ayahuya:main` を動かす**（web 構成をイメージの pull に移す作業の最初の一歩）。入口の nginx は TLS だけを受け持ち、`ayahuya:8080` へ転送する。記事ページの書き出しと旧 URL の 301 はイメージ側にある。GHCR のパッケージは非公開で、配備先は読み取り専用のマシンユーザーのトークン（`SHAKE_GHCR_USER`・`SHAKE_GHCR_READ_TOKEN`、SOPS）で `docker login` する。そのアカウントには読ませるパッケージにだけ Read を付ける（[bootstrap.md](bootstrap.md) の「残っている手作業」）。戻すときは `shake_web_ayahuya_image` をコミット SHA のタグにする。
- アプリの更新は「Ansible を流し直す」だけ。手元で `docker compose` を叩かない。
- **配備先が5分ごとに `main` と ayahuya のイメージを見て自分で更新する**（`shake-web-update.timer`。旧ホスト向け CD の代わり。UBSLEEPY と同じ方式）。即時に反映したいときは `ssh -i ~/.ssh/id_ed25519_shake ansible_admin@192.168.30.12 'sudo systemctl start shake-web-update'`。
- ビルドに失敗したら `ssh -i ~/.ssh/id_ed25519_shake ansible_admin@192.168.30.12 'sudo python3 /opt/shake-web/manage.py status'` と `sudo docker logs pkhack_app --tail 50` を見る。

## 公開の切り替え（2026-10-05 実施済み）

1. `shake-infra#26` で `negitoroserver` の `stream_proxy.conf`（443）と `sslh`（80）の向き先を web-01 の tailnet IP へ変更した。
2. GitHub Actions「アプリからの自動デプロイ」→ `target=proxy` で適用し、HSTS ヘッダで切替を確認した。
3. 旧ホストの Web コンテナを停止し、`restart=no` にした（ボリュームは残す）。
4. **残り**: shake-infra の CD（repository_dispatch → `deploy_shakeweb` など）は旧ホスト向けのまま。旧ホストの Web コンテナは停止しているため実害は無いが、`deploy_shakeweb` を流すと停止中のコンテナへ配備を試みる。整理するまで shake-web / pkhack の `main` へ push した際の自動デプロイは止めておくのが安全。

## 既知の不具合

- `pkhack` の practice 3本（`langquiz/practice`・`bsquiz/practice`・`abilityquiz/practice`）は **旧ホストでも 500**。クエリが存在しない `POKEMON_NAMES` を参照する、`mv_quiz_status` に無い種族値・特性の列を読む、が原因。移行とは無関係の既存不具合。
- 2026-10-05 の移行で pkhack の SQL を小文字スキーマへ合わせた（[pkhack#7](https://github.com/rurutheGeek/pkhack/pull/7)、merge 済み）。配備先は main から fetch して動く。

## 守り（外部公開の前提・2026-10-05 に強化）

- 入ってくる通信は、Flint 3 の DMZ（家の中から DMZ へは配備の SSH と監視だけ）と Tailscale の ACL（`tag:relay` → `tag:dmz:80,443`）が絞る。
- SSH は鍵のみ（`PasswordAuthentication no`・`KbdInteractiveAuthentication no`・root は `without-password`）。`unattended-upgrades` は有効。
- nginx は `server_tokens off`、TLS1.2 以上（TLS1.1 は拒否を実測）、`X-Content-Type-Options`・`X-Frame-Options`・`Referrer-Policy`・HSTS を全サイトへ付与（`stacks/shake-web/nginx/00-security.conf.template`）。8443 はホストの 127.0.0.1 にだけ公開。
- Docker は json-file を `max-size=10m`・`max-file=3` に制限し、全サービスに `no-new-privileges` を付与。アプリのポートは `127.0.0.1` のみ。
- クイズのトークン暗号鍵 `QUIZ_SECRET` を SOPS に追加し、`platform/sops/shake-web.sops.yaml` から配る（pkhack のコードは既定値フォールバックを削除。`QUIZ_SECRET` 未設定なら起動しない）。
- 残りのリスク: ① negitoroserver は Cloudflare 以外からも直接 443 を受ける（Cloudflare IP の許可リストは shake-infra 側の改善）。② 旧ホストの停止済みデプロイと pkhack の履歴には DB パスワードが残る。`pkdb_reader` のローテーションを推奨。

### 外向き（egress）と自宅LANの分離

Flint 3 の DMZ が家の中への転送を止め（pkdb だけ通す。`dmz-db-clients`）、Pi 5 の `inet homeguard`（`pi_base` の `pi_base_lan_guard`）が家の中の区画（`192.168.10/30/40/50.0/24`）への送信を落とす。通すのは DNS（DMZ のゲートウェイと AdGuard Home）と pkdb だけ。pkdb の側（apps-01 のセキュリティグループ `pkdb_dmz`）も Pi 5 だけを受ける。

- 実測（2026-10-16）: pkdb とインターネット 443 は届く。`192.168.10.105:22`・`192.168.10.10:8006`・`192.168.10.1:80`・`192.168.40.97:3389` は届かない。
- GitHub への git は 22 ではなく `ssh.github.com:443` を使う（`manage.py` が指定）。

### プロキシ（negitoroserver）側

公開の中継は **tailnet の端末間**で行う。プロキシは shakeserver の tailnet IP（`100.116.167.59`）を直接指す。プロキシには LAN のサブネットルート（`accept-routes`）を持たせない。これで、プロキシが突破されても届くのは tailnet 上だけで、LAN 全体へのルートは持たない。

Tailscale の ACL（`platform/tailscale/acl.json`）で、negitoroserver（`tag:relay`）から届く先は `tag:dmz`（Pi 5）の 80/443 だけ。

### プロキシ（negitoroserver）の侵害に備えて（提案）

- 中継は DERP リレー（443）でも成立する。直通 UDP を開けていないため、状況により中継経由になる（機能は同じ）。

## 外からの監視（negitoroserver）

家の回線や K11 が落ちても気づけるよう、**家の外にある negitoroserver（zero2w、公開の入口）** が外から見張る（2026-10-14 に tarakoserver から移した）。`platform/ansible/public-monitor.yml` とロール `public_monitor`（`outpost.ini`、`ansible_admin`）で、1分ごとに公開サイト（`shake`・`pkhack`・`ayahuya`・ルート）を確認し、**状態が 10 分続けて変わったときだけ** Discord へ通知する（通知先は `platform/sops/public-monitor.sops.yaml`。文の形は家の中の監視と同じ「🔴 緊急｜…」「✅ 直った｜…」）。

家の中の名前（`grafana` など）は見ない（`public_monitor_check_internal: false`。入口は Tailscale の制限で家の中へ入れない）。状態は SD カードではなくメモリの `/run/public-monitor/` に置く。

入口の nginx（443 を TLS のまま中継、PROXY protocol）と sslh（80）は `platform/ansible/relay.yml`（ロール `relay`）で配る（2026-10-14 に shake-infra から取り込んだ）。

## 検証

```bash
ssh -i ~/.ssh/id_ed25519_shake ansible_admin@192.168.30.12 'sudo docker ps; curl -sk --resolve pkhack.ruruthegeek.dpdns.org:8443:127.0.0.1 \
  "https://pkhack.ruruthegeek.dpdns.org:8443/quiz/api/langquiz/names?lang=JPN"'
```
