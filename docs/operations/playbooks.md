---
title: Playbook の一覧
updated: 2026-10-24
section: 運用手順
audience: 管理者
tags:
  - ops
  - awx
---

# Playbook の一覧

> **更新日** 2026-10-24 ・ **区分** 運用手順 ・ **読む人** 管理者

<!-- python3 tools/awx-catalog.py が platform/ansible/*.yml の先頭コメントから生成する。直接編集しない。 -->

## Proxmox

| Playbook | 何をするか | 対象 | AWX |
| --- | --- | --- | --- |
| `pve-backup.yml` | 重要VM（Tier1）の週次バックアップを6TB USB HDDへ取る | `pve` | 既定は確認だけ |
| `pve-bulk-storage.yml` | Proxmoxホストの6TB USB HDDをext4でマウントし、media-01とgame1へNFS共有する | `pve` | 既定は確認だけ |
| `pve-guests.yml` | 停電・電源断のあと、直前に動いていたゲストを戻す仕組みを Proxmox ホストへ入れる | `pve` | 既定は確認だけ |
| `pve-node-exporter.yml` | Proxmoxホストにnode_exporterとSMART/NVMeのtextfile collectorを入れる | `pve` | 既定は確認だけ |
| `pve-nut.yml` | ProxmoxホストのUPSをNUTで公開する（読み取り専用） | `pve` | 既定は確認だけ |
| `pve-users.yml` | Proxmox 利用者のパスワードを発行して設定する | `pve` | 既定は確認だけ |
| `survey-pve.yml` | Proxmox VE ホストの実機の読み取り | `pve` | 既定は確認だけ |

## Kubernetes

| Playbook | 何をするか | 対象 | AWX |
| --- | --- | --- | --- |
| `kubernetes.yml` | Kubernetes クラスタを用意する | `k8s_cp`・`k8s_worker` | 既定は確認だけ |

## メディア

| Playbook | 何をするか | 対象 | AWX |
| --- | --- | --- | --- |
| `deploy.yml` | deploy | `media` | 手元専用（旧来の一括配備（stacks/compose.yaml）。いまは media-*.yml を個別に流す） |
| `media-aihist.yml` | media-01 の aihist（systemd）を片付ける | `media` | 実行 |
| `media-base.yml` | media-01（クラウドVM）の土台 | `media` | 実行 |
| `media-forgejo-sso.yml` | Forgejo のネイティブ OIDC を core-01（Authentik）に接続する | `media` | 実行 |
| `media-forgejo.yml` | Forgejo（リポジトリの保管庫）を media-01 の独立 Compose プロジェクトとして配備する | `media` | 実行 |
| `media-freshrss-sso.yml` | FreshRSS のネイティブ OIDC を core-01（Authentik）に接続する | `media` | 実行 |
| `media-freshrss.yml` | FreshRSS を media-01 の独立 Compose プロジェクトとして配備する | `media` | 実行 |
| `media-kavita-sso.yml` | Kavita のネイティブ OIDC を core-01（Authentik）に合わせる | `media` | 実行 |
| `media-kavita.yml` | Kavita を media-01 の独立 Compose プロジェクトとして配備する | `media` | 実行 |
| `media-localsend.yml` | LocalSend の常設受信機を media-01 の独立 Compose プロジェクトとして配備する | `media` | 実行 |
| `media-navidrome.yml` | Navidrome を media-01 の独立 Compose プロジェクトとして配備する | `media` | 実行 |
| `media-nextcloud-mcp.yml` | Nextcloud MCPサーバ（AIエージェント用のファイル操作・MP3タグ・圧縮/解凍）をmedia-01 へ配備する | `media` | 実行 |
| `media-nextcloud.yml` | Nextcloud・Calendar・Tasks を media-01 の独立 Compose プロジェクトとして配備する | `media` | 実行 |
| `media-sso.yml` | media-01 の Nextcloud を core-01（Authentik）へ ネイティブ OIDC で接続する | `media` | 実行 |
| `media-tls.yml` | media-01（クラウドVM）の Caddy を配備する | `media` | 実行 |
| `media-urbackup.yml` | UrBackup（Windows のファイル・システムイメージの世代バックアップ）をmedia-01 の独立 Compose プロジェクトとして配備する | `media` | 実行 |
| `media-verify.yml` | media-01 の配備後確認 | `media` | 実行 |
| `music-tools.yml` | music-tools（MeTube・変換・タグAPI・同期）を media ホストへ配備する | `media` | 実行 |

## アプリ

| Playbook | 何をするか | 対象 | AWX |
| --- | --- | --- | --- |
| `bot-portal.yml` | Botポータル（ログ閲覧・再起動・状態・manage.pyの定型操作）を apps-01 へ配備する | `apps` | 実行 |
| `circleauth.yml` | サークル認証Bot「CIRCLEAUTH」を apps-01 へ配備する | `apps` | 実行 |
| `cups.yml` | Canon TS8430シリーズへのプリント中継（CUPS）を apps-01 へ入れる | `apps` | 実行 |
| `docs-site.yml` | ドキュメントサイトを LAN に公開する | `apps` | 実行 |
| `eufy-leo-rtc.yml` | Eufy leo_rtc ライブ配信を apps-01（Home Assistant と同じホスト）へ配備する | `apps` | 実行 |
| `eufy-security-ws.yml` | eufy-security-ws を apps-01 の独立 Compose プロジェクトへ配備する | `apps` | 実行 |
| `homarr.yml` | Homarr（サービスの入口）を apps-01 へ配備する | `apps` | 実行 |
| `home-assistant.yml` | Home Assistant Container を apps-01 の独立 Compose プロジェクトへ配備する | `apps` | 実行 |
| `librespeed.yml` | LibreSpeed（端末 ↔ apps-01 の実効速度）を apps-01 へ配備する | `apps` | 実行 |
| `mail-view.yml` | メールビューア（Gmail 読み取り専用）を apps-01 へ配備する | `apps` | 実行 |
| `pkdb.yml` | ポケモン系のPostgreSQL（sleepy_pkdb・shakeweb・pkhack）を apps-01 へ配備する | `apps` | 実行 |
| `poke-translate.yml` | ポケモン用語対応翻訳の翻訳サイト（静的ファイルと拡張機能のzip）を apps-01 へ配備する | `apps` | 実行 |
| `ubsleepy-next.yml` | Discord Bot「UBSLEEPY」(-next) を apps-01 へ配備する | `apps` | 実行 |
| `ubsleepy.yml` | Discord Bot「UBSLEEPY」を apps-01 へ配備する（本番・イメージ固定） | `apps` | 実行 |
| `vaultwarden.yml` | Vaultwarden（パスワード管理・SSO）を apps-01 へ配備する | `apps` | 実行 |

## 監視

| Playbook | 何をするか | 対象 | AWX |
| --- | --- | --- | --- |
| `image-scan.yml` | 固定したイメージの脆弱性（Trivy）とランタイムの版（PHP など）を、監視のホストで毎日調べる | `monitoring` | 実行 |
| `monitoring.yml` | 監視スタック（Prometheus・Grafana・exporter）を tarakoserver へ配備する | `monitoring` | 実行 |
| `netmap.yml` | ネットワーク図（stacks/netmap）を tarakoserver へ配備する | `monitoring` | 実行 |
| `node-exporter.yml` | 各VMへ node_exporter を入れる | — | 実行 |
| `storage-health.yml` | ストレージの寿命対策（journald上限・/のnoatime・Dockerログ上限）をホストとゲストへまとめて当てる | `cloud_control`・`identity_provider`・`media`・`monitoring`・`pve`・`storage` | 既定は確認だけ |
| `touch-panel.yml` | 監視のタッチパネル（stacks/touch-panel）を tarakoserver の画面へ配備する | `monitoring` | 実行 |

## 認証・入口

| Playbook | 何をするか | 対象 | AWX |
| --- | --- | --- | --- |
| `edge.yml` | HTTPS の入口（dns.yaml の edge.host）の Caddy を配備する | `core` | 既定は確認だけ |
| `identity.yml` | Authentik を core-01 へ配備する | `identity_provider` | 既定は確認だけ |

## クラウド

| Playbook | 何をするか | 対象 | AWX |
| --- | --- | --- | --- |
| `cloud.yml` | 自作クラウドの API（Phase 1: ログイン、アクセスキー、監査ログ）を cloud-01 へ配備する | `cloud_control` | 既定は確認だけ |
| `garage.yml` | Garage（S3互換オブジェクトストア）を cloud-01 へ構築する（2026-10-03 に storage-s3 から合流） | `storage` | 既定は確認だけ |
| `verify-cloud.yml` | 実機プローブ | `localhost` | 実行 |

## 共通

| Playbook | 何をするか | 対象 | AWX |
| --- | --- | --- | --- |
| `guests.yml` | Terraform が作ったゲストVMの共通設定と、開発VMの追加設定 | `devbox`・`seed`・`terraform_managed` | 既定は確認だけ |
| `media.yml` | media-01（クラウドVM）の配備入口 | — | 実行 |
| `minecraft.yml` | Minecraft（stacks/minecraft）を shakeserver（Raspberry Pi 5）へ配備する | `minecraft` | 手元専用（Minecraft サーバは NetBox の台帳に無い（minecraft 群）） |
| `netbox-dhcp-sync.yml` | dev-02（旧 dev-b）で NetBox とルータの DHCP を定期同期する | `automation` | 実行 |
| `netbox.yml` | NetBox（台帳）を構築する | `netbox_bootstrap` | 手元専用（NetBox 自身を作る。NetBox より前に流すので seed.ini を使う） |
| `public-monitor.yml` | ミニPC（K11・Proxmox）の外から、公開サイトと監視の入口を見る | `outpost` | 手元専用（外部の監視点（outpost.ini）） |
| `raspberry-pi.yml` | Raspberry Pi 3 台の土台（書き込みの削減・画面と VNC の停止・古いコンテナの片付け） | `raspberry_pi` | 手元専用（Raspberry Pi は NetBox の台帳に無い（raspberry_pi 群）） |
| `relay.yml` | 家の外の入口（negitoroserver、zero2w）の nginx・sslh | `relay` | 手元専用（中継サーバは NetBox の台帳に無い（relay 群）） |
| `shake-web.yml` | Shake-Web の公開サイトを配る | `web` | 手元専用（公開サイトのサーバは NetBox の台帳に無い（web 群）） |
| `site.yml` | 全体をまとめるプレイブック | — | 既定は確認だけ |
