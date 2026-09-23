---
title: 監視（monitor-01）
updated: 2026-09-23
section: 運用手順
audience: 管理者
tags:
  - ops
  - monitoring
---

# 監視（monitor-01）

> **更新日** 2026-09-23 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 稼働中。`https://grafana.apextox.dpdns.org`（identity の OIDC）。

**アラートが鳴ったときと、監視そのものを直すときのページ**です。なぜその構成にしたか・いつ何を足したかの経緯は[M01 監視](../development/M01-monitoring.md)が正本で、ここには書きません。

## 1. 何が動いているか

monitor-01（`192.168.10.102`）の独立Composeです。**サービス自身のポートはすべて `127.0.0.1` に閉じて**おり、入口は同じVMのCaddy（`stacks/tls-proxy/`）だけです。

| 役割 | ソフト | ポート（127.0.0.1） |
| --- | --- | --- |
| 収集・保持 | Prometheus | 9090 |
| 通知 | Alertmanager | 9093 |
| 表示 | Grafana | 3000 |
| 疎通・証明書 | blackbox_exporter | 9115 |
| Proxmox | pve-exporter | 9221 |
| UPS | nut_exporter | 9199 |

収集ジョブは `prometheus`・`blackbox`・`pve`・`nut`・`node`・`game` の6つ（`stacks/monitoring/prometheus/prometheus.yml`）。保持は既定15日（`PROMETHEUS_RETENTION`）で、時系列は専用データディスクに置きます。

Grafana のダッシュボードは overview・host・storage・vm-memory・game-server の5枚です（`stacks/monitoring/grafana/provisioning/dashboards/`）。

## 2. 入る

| 入口 | 認証 |
| --- | --- |
| `https://grafana.apextox.dpdns.org` | identity の OIDC。**`admins` は Admin、`users` は Viewer** |
| Prometheus・Alertmanager の画面 | 入口を出していません。見るなら monitor-01 へSSHして `127.0.0.1` へポートフォワード |

**identity が落ちていて Grafana に入れないとき**は、ローカル管理者で入ります。パスワードは monitor-01 の `/opt/monitoring-stack/secrets/grafana_admin_password` です。

```bash
ssh debian@192.168.10.102 'sudo cat /opt/monitoring-stack/secrets/grafana_admin_password'
```

## 3. アラートが鳴ったら

通知はメール（`smtp.sops.yaml` の Gmail）です。定義は `stacks/monitoring/prometheus/alerts.yml`。**`severity: critical` は `SmartDeviceUnhealthy` の1つだけ**で、残りは `warning` です。

### 疎通（availability）

| アラート | 意味 | 最初に見るところ |
| --- | --- | --- |
| `ServiceProbeFailed` | HTTPS名が5分応答しない | そのVMが動いているか。動いていれば中身のコンテナ。[確認と、はまりどころ](verify.md) |
| `CertificateExpiringSoon` | 証明書の期限が14日以内 | 該当ホストのCaddyログ。Cloudflareトークンの権限（ゾーン読み取り＋DNS編集の両方が要る） |

### ノード（node_exporter を入れた5台）

対象は services-01・identity・cloud-01・storage-s3・monitor-01 と Proxmox ホストです。media-01・game1 は入れておらず、Proxmox 側の資源で見ます。

| アラート | 意味 |
| --- | --- |
| `NodeExporterDown` | exporter が応答しない。VM停止かコンテナ停止 |
| `NodeFilesystemAlmostFull` | 空きが15%未満 |
| `NodeMemoryLow` | 空きメモリが10%未満 |
| `NodeOOMKill` | OOM killer が動いた。何が殺されたかを `journalctl` で見る |
| `NodeSystemdUnitFailed` | unit が failed |
| `NodeRebooted` | 起動時刻が変わった。**計画外の再起動を疑う** |

### バックアップ（backup）

| アラート | 意味 |
| --- | --- |
| `CloudBackupStale` | 管理DBのバックアップが36時間以上成功していない |
| `CloudBackupMetricMissing` | **メトリクスそのものが無い。** 「取っているつもり」を検出するための規則 |

どちらも cloud-01 の `cloud-backup.timer` を見ます（[クラウドAPIの構築](cloud-resources.md#3-18)）。

### ストレージ（storage）

6TB HDD と NVMe の健康状態です（[共有バルクストレージ](bulk-storage.md)・[バックアップ](backup.md)）。

| アラート | 意味 |
| --- | --- |
| `BulkDiskUnmounted` | `/srv/bulk` が見えない。**NFS越しのmedia-01・game1も巻き込む** |
| `BulkDiskAlmostFull` | 空きが10%未満 |
| `SmartDeviceUnhealthy` | **SMART自己診断がFAILED。唯一の critical。** ディスク交換の検討 |
| `SmartSectorErrors` | 不良・代替処理待ちセクター |
| `SmartCableErrors` | CRCエラーの増加。**多くはケーブル側** |
| `SmartTemperatureHigh` | 50℃超 |
| `SmartDeviceInactive` / `SmartCollectorStale` | SMARTが読めない／収集が1時間以上止まっている。`prometheus-node-exporter-smartmon.timer` を確認 |
| `NvmeWearHigh` | NVMeの寿命消費が80%超。書き込みの多い処理とバックアップ世代数を見直す |

### Proxmox・UPS（resources）

| アラート | 意味 |
| --- | --- |
| `ProxmoxGuestDown` | ゲストが停止または応答なし |
| `ProxmoxNodeMemoryHigh` | ホストのメモリ使用率が90%超。内訳は Grafana の vm-memory |
| `ProxmoxNodeDiskAlmostFull` | ホストのディスク使用率が85%超 |
| `UpsOnBattery` | 停電か入力異常。残り時間を確認（[電源とUPS](power.md)） |

ゲストの `pve_memory_usage_bytes` はゲスト内のキャッシュを含むため上限比では張り付きが常態になり、**規則にはしていません**。ゲスト内の実圧迫は `NodeMemoryLow` が受け持ちます。

## 4. 鳴らないことを検知する（dead man's switch）

monitor-01 は K11 の上にあるので、**K11ごと落ちると監視も沈黙します。** 「静かなこと」と「正常なこと」を区別するため、外部の受信点（healthchecks.io）へ常時POSTしています。

- `Watchdog`（`severity: none`。`vector(1)` で常時firing）→ Alertmanager の `deadman` 宛先 → 1時間ごとにPOST
- 受信側は Period 12時間 / Grace 1時間。**届かなくなったら向こうから通知が来ます**
- ping URL は `platform/sops/monitoring.sops.yaml` の `WATCHDOG_PING_URL`。**空なら `deadman` は何もせず、`Watchdog` がメールに流れることもありません**

```bash
sops set platform/sops/monitoring.sops.yaml '["WATCHDOG_PING_URL"]' '"<url>"'
```

**いまルータも K11 上のVMなので、K11が落ちると通知経路ごと失われます**（[障害モード](../architecture/failure-modes.md)）。外部の受信点だけが残ります。

## 5. 直す・入れ替える

monitor-01 の `/opt/monitoring-stack` で `manage.py` を使います（`sudo` が要ります）。

| コマンド | 何をする |
| --- | --- |
| `status` | コンテナとターゲットの状態 |
| `reload` | 設定だけを再読込（Prometheus・Alertmanager） |
| `restart` | コンテナを作り直す |
| `up` | 配備・起動 |
| `lock` | イメージのdigestを `compose.lock.yaml` へ固定 |
| `backup` | 状態の取得 |

アラート規則やスクレイプ先を変えたときは、Gitを直してから Ansible で配り直します。

```bash
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/monitor.ini platform/ansible/monitoring.yml
```

**`.env` の SMTP・`WATCHDOG_PING_URL` を変えたときも Alertmanager を再読込します**（2026-09-16に修正。忘れると古い設定のまま動き続けます）。

Proxmox ホスト側の exporter は別Playbookです。

```bash
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-node-exporter.yml
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-nut.yml
```

## 6. 限界

- **monitor-01 が止まると、監視の停止そのものは誰も検知しません。** 外部のdead man's switchだけが気づきます
- 監視対象と監視基盤が同じ物理ホストにあります。K11障害は両方を同時に失います
- media-01・game1 には node_exporter を入れていないので、ゲスト内の空きメモリ・fs は見えません（Proxmox側の割当と使用量だけ）
- 保持は15日です。それより古い傾向は残りません

## 関連

- [M01 監視](../development/M01-monitoring.md) — 設計の経緯と実測記録（正本）
- [電源とUPS](power.md) — UPSと停電時の停止順
- [障害モードと単一障害点](../architecture/failure-modes.md) — 何が止まると何が見えなくなるか
- [確認と、はまりどころ](verify.md) — 実際に踏んだ落とし穴
