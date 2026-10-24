---
title: 自動化の一覧
updated: 2026-10-24
section: 運用手順
audience: 管理者
tags:
  - ops
  - awx
---

# 自動化の一覧

> **更新日** 2026-10-24 ・ **区分** 運用手順 ・ **読む人** 管理者

| 仕組み | 何をするか | いつ | 定義 |
| --- | --- | --- | --- |
| AWX | Playbook の実行と履歴（人は画面から、AI は `tools/awx-run`） | 押したとき | [AWX の使い方](awx.md)・[Playbook の一覧](playbooks.md) |
| Flux | k8s の構成（AWX・CNPG・Knative・上限）を `main` に合わせる | Git を1分ごと、適用は10分ごと | `platform/flux/` |
| GitHub Actions | 検証（テスト・lint・文書のビルド・脆弱性） | push と PR のたび | `.github/workflows/validate.yml` |
| GitHub Actions | AWX の実行環境のイメージを作る | `execution-environment.yml` などを `main` へ入れたとき | `.github/workflows/awx-ee.yml` |
| Renovate | 依存の更新の PR を作る（自動マージはしない） | 月曜の6時前 | `renovate.json` |
| Proxmox | Tier1 VM の週次バックアップ（vzdump） | 日曜 6:00 | `platform/ansible/roles/pve_backup/defaults/main.yml` |

## ホストの定期処理（systemd timer）

| ホスト | タイマー | 何をするか | いつ | 定義 |
| --- | --- | --- | --- | --- |
| K11（Proxmox） | `shakecloud-guests-snapshot` | 動いているゲストを記録する（停電後に戻すため） | 1分ごと | `platform/ansible/roles/pve_guest_state/files/shakecloud-guests-snapshot.timer` |
| K11（Proxmox） | `bulk-quota-textfile` | 6TB HDD の使用量を監視へ出す | 15分ごと | `platform/ansible/roles/pve_bulk_storage/tasks/main.yml` |
| K11（Proxmox） | `shakecloud-backup-status` | 最新のバックアップ時刻を監視へ出す | 15分ごと | `platform/ansible/roles/pve_node_exporter/tasks/main.yml` |
| K11（Proxmox） | `shakecloud-speedtest` | 回線の速度を測る（測るかはスクリプトが決める） | 毎時 | `platform/ansible/roles/pve_node_exporter/tasks/main.yml` |
| K11（Proxmox） | `monitoring-pull` | tarakoserver の監視の写しを取り寄せる | 毎日 5:00 | `platform/ansible/roles/monitoring_backup/tasks/main.yml` |
| K11（Proxmox） | `flint3-backup` | Flint 3 の設定を取る | 毎日 4:30 | `tools/flint3-backup-install.sh` |
| tarakoserver | `monitoring-backup` | 監視の記録を固めて K11 へ写す | 毎日 4:00 | `platform/ansible/roles/monitoring_backup/tasks/main.yml` |
| tarakoserver | `image-scan` | 固定したイメージの脆弱性を調べる | 毎日 2:30 | `platform/ansible/roles/image_scan/tasks/main.yml` |
| tarakoserver | `netmap-router-check` | Flint 3 の設定崩れを点検する | 5分ごと | `platform/ansible/roles/netmap/tasks/main.yml` |
| cloud-01 | `cloud-backup` | クラウドの管理DBをダンプする | 毎日 3:40 | `cloud/cloud-backup.timer.j2` |
| apps-01 | `pkdb-backup` | pkdb の PostgreSQL をダンプする | 毎日 4:20 | `platform/ansible/roles/pkdb/templates/pkdb-backup.timer.j2` |
| apps-01 | `ubsleepy-backup` | UBSLEEPY のセーブデータを固める | 毎日 19:10 | `platform/ansible/roles/ubsleepy-next/templates/ubsleepy-backup.timer.j2` |
| apps-01 | `circleauth-update` | CIRCLEAUTH の `main` を見て更新する | 5分ごと | `platform/ansible/roles/circleauth/templates/circleauth-update.timer.j2` |
| apps-01 | `circleauth-backup` | CIRCLEAUTH のセーブデータを固める | 毎日 19:20 | `platform/ansible/roles/circleauth/templates/circleauth-backup.timer.j2` |
| apps-01 | `eufy-camera-watch` | Eufy カメラの見張り | 2分ごと | `platform/ansible/home-assistant.yml` |
| media-01 | `forgejo-issues` | GitHub の Issues を Forgejo へ写す | 毎日 3:30 | `platform/ansible/media-forgejo.yml` |
| media-01 | `media-stack-ocr-index` | Nextcloud の画像の文字を索引にする | 毎日 2:30 | `stacks/media/nextcloud/media-stack-ocr-index.timer.j2` |
| media-01 | `media-stack-kavita-shelve` | Kavita のばらの本を棚へ移す | 1時間おき | `stacks/media/kavita/media-stack-kavita-shelve.timer` |
| media-01 | `media-stack-music-sync` | 取り込んだ音楽を確かめる | 1分おき | `stacks/music-tools/media-stack-music-sync.timer` |
| dev-02 | `netbox-dhcp-sync` | NetBox とルータの DHCP を同期する | 15分ごと | `platform/ansible/roles/netbox_dhcp_sync/templates/netbox-dhcp-sync.timer.j2` |
| shakeserver | `podman-auto-update` | 公開サイトの新しいイメージを取り込む | 5分ごと | `platform/ansible/roles/shake_web/tasks/podman.yml` |
| 外部の監視点 | `public-monitor` | 公開サイトを外から確かめる | 1分ごと | `platform/ansible/roles/public_monitor/templates/public-monitor.timer.j2` |

時刻はすべて日本時間。タイマーを足したら、この表に定義のファイルを書く（`tests/test_docs_structure.py` が、タイマーを定義しているファイルがすべてここにあるかを確かめる）。

## コンテナの中の定期処理

| ホスト | 何をするか | いつ | 定義 |
| --- | --- | --- | --- |
| media-01 | Nextcloud のバックグラウンドジョブ（`cron` コンテナ） | 5分ごと | `stacks/media/nextcloud/compose.yaml` |
| media-01 | Forgejo のミラーの同期 | 24時間ごと | [Forgejo](../services/forgejo.md) |
