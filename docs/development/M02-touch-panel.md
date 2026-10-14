---
title: M02 監視のタッチパネル
updated: 2026-10-14
section: 開発計画
audience: 開発者
tags:
  - plan
  - monitoring
---

# M02 監視のタッチパネル

> **更新日** 2026-10-14 ・ **区分** 開発計画 ・ **読む人** 開発者

tarakoserver（Raspberry Pi 4）につないだ小さなタッチパネルに、家の監視の状態を出す専用の表示アプリを、フルスクラッチで作る。公共の場所にある専用の案内板のように、この表示以外には何もできない端末にする。

## 決まっていること

| 項目 | 決定 |
| --- | --- |
| 作り方 | フルスクラッチ。既製のダッシュボード（Grafana など）を映す方式は採らない |
| ブラウザー | 使わない（Chromium・WPE/Cog などを常駐させない） |
| メモリ | 表示のためにメモリを大きく使わない。Chromium のような重いソフトの常駐は不可 |
| 操作 | タッチで操作できる。文字の入力はしない |
| ログイン | 画面からはログインしない。データは同じ機械の中から読む |
| 閉じ込め | 表示アプリ以外の画面（デスクトップ、端末、別のアプリ、外部のサイト）へ出られない。落ちたら自動で表示に戻る |
| 言語 | 画面の文言は日本語。画面に説明文を置かない（見出し・値・状態だけ） |

## 実機

| 項目 | 値 |
| --- | --- |
| 本体 | Raspberry Pi 4 Model B（Rev 1.5、メモリ 4GB、arm64） |
| OS | Raspberry Pi OS Lite（Debian 13 trixie、arm64、カーネル 6.18）。デスクトップ・X・Wayland は入っていない |
| 画面 | DSI 接続、800×480（DRM: `card1-DSI-1`、ドライバ `vc4-kms-v3d`、`/dev/fb0` もある）。物理的に小さい |
| タッチ | `generic ft5x06`（I2C、`10-0038`）。evdev の入力デバイスとして見える |
| 起動ディスク | SD カード（予定。今は USB メモリから起動中）。**書き込みを減らす**ため、表示アプリはディスクに書かない（ログは journald がメモリに置く。設定は読むだけ） |
| データ用ディスク | HDD（`/srv`、ext4、`LABEL=tarako-data`）。必要なら書いてよいが、無くても表示は動くこと |
| 同居するもの | Prometheus・Alertmanager・Grafana・blackbox・pve/nut exporter（Docker、`stacks/monitoring/`）、Caddy、ネットワーク図（`stacks/netmap/`） |

## データの取り方

すべて同じ機械の中（`127.0.0.1`）から、認証なしの HTTP で読む。外部への通信はしない。

| 入手先 | URL | 使い道 |
| --- | --- | --- |
| Prometheus | `http://127.0.0.1:9090/api/v1/query`（`query_range` も） | 値・死活・時系列 |
| Alertmanager | `http://127.0.0.1:9093/api/v2/alerts` | 今出ている警告の一覧 |

Prometheus の収集対象（`stacks/monitoring/prometheus/prometheus.yml`）:

| job | 中身 | 使える値の例 |
| --- | --- | --- |
| `node` | 各ホストの node_exporter（`node-targets.yml`：K11・core-01・cloud-01・tarakoserver・apps-01・web-01 など） | `up`、`node_load1`、`node_memory_MemAvailable_bytes`、`node_filesystem_avail_bytes`、`node_hwmon_temp_celsius`／`node_thermal_zone_temp` |
| `blackbox` | 公開・内部の URL の到達（`blackbox-targets.yml`、`https_reachable`） | `probe_success`、`probe_duration_seconds`、`probe_ssl_earliest_cert_expiry` |
| `pve` | Proxmox（K11）の VM とノード | `pve_up`、`pve_cpu_usage_ratio`、`pve_memory_usage_bytes` |
| `nut` | UPS（K11 の NUT） | `network_ups_tools_battery_charge`、`network_ups_tools_ups_status`、`network_ups_tools_ups_load` |
| `game` | game-01 のメトリクス | 必要なら |
| `prometheus` | Prometheus 自身 | — |

警告（`alerts.yml`）: ServiceProbeFailed、CertificateExpiringSoon、NodeExporterDown、NodeFilesystemAlmostFull、NodeMemoryLow、NodeOOMKill、NodeSystemdUnitFailed、NodeRebooted、CloudBackupMetricMissing、CloudBackupStale、BulkDiskUnmounted、BulkDiskAlmostFull、BulkAreaAlmostFull、SmartDeviceUnhealthy、SmartDeviceInactive、SmartSectorErrors、SmartCableErrors、SmartTemperatureHigh、SmartCollectorStale、NvmeWearHigh、Watchdog（常に鳴っている生存確認。表示から除く）、ProxmoxGuestDown、ProxmoxNodeMemoryHigh、UpsOnBattery、ProxmoxNodeDiskAlmostFull。

正確な系列名は実機の Prometheus で `/api/v1/label/__name__/values` を見て確かめる。

## 表示したいもの（たたき台）

| 優先 | 内容 |
| --- | --- |
| 1 | 今出ている警告（件数と、重いものから名前）。警告があるときは、どの画面でも目に入る |
| 2 | 死活：インターネット（公開サイトの `probe_success`）、Flint 3、K11、各 Pi、主な VM |
| 3 | UPS：電池の残り・負荷・停電中か |
| 4 | 各ホストの CPU・メモリ・ディスク・温度 |
| 5 | 回線：公開サイトの応答時間 |

画面の構成・ページ分け・タッチでの切り替え方は、作る人が決める。

## 配備の決まり

- コードは `stacks/` または Ansible のロールに置き、`platform/ansible/` から tarakoserver へ配備する（`monitoring` グループ、鍵は `~/.ssh/id_ed25519_shake`）。手で入れない。
- systemd のサービスとして起動時に自動で立ち上げ、落ちたら再起動する。表示以外のログイン画面（tty の getty）は画面に出さない。
- 依存（ライブラリ・パッケージ）を足すときは、理由を添えて提案し、了承を得てから入れる（README「改善の提案」）。
- 画面の電源・明るさの制御が要るなら、それも同じ配備に含める。

## 受け入れの目安

- 電源を入れると、何も操作せずに表示が出る。
- タッチだけで全ページを行き来でき、表示以外へ出る操作が無い。
- Prometheus や Alertmanager が止まっていても落ちず、「読めない」ことを表示する。
- 常駐のメモリが小さい（目安は数十 MB 以内）。SD カードへ書かない。
- 24 時間動かし続けて、メモリが増え続けない。

## 関連

- [M01 監視（Prometheus・Grafana）](M01-monitoring.md)
- 監視の配備: `platform/ansible/monitoring.yml`、`stacks/monitoring/`
- Raspberry Pi の土台: `platform/ansible/roles/pi_base/`（journald はメモリ・SD の書き込み削減）
