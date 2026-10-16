---
title: 監視（tarakoserver）
updated: 2026-10-16
section: 運用手順
audience: 管理者
tags:
  - ops
  - monitoring
---

# 監視（tarakoserver）

> **更新日** 2026-10-16 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 稼働中。`https://grafana.apextox.dpdns.org`（core-01 の Authentik の OIDC）。

**アラートが鳴ったときと、監視そのものを直すときのページ**です。なぜその構成にしたか・いつ何を足したかの経緯は[M01 監視](../development/M01-monitoring.md)が正本で、ここには書きません。

## 1. 何が動いているか

tarakoserver（Raspberry Pi 4、`192.168.10.11`）の独立Composeです。K11 の外の物理機に置いているので、K11 が落ちても監視は残ります。2026-10-14〜15 に monitor-01（基盤VM、VMID 120）から移し、monitor-01 は廃止しました。**サービス自身のポートは `127.0.0.1` に閉じて**おり、入口は core-01 の Caddy から中継される同じ機械の Caddy（`stacks/tls-proxy/`）だけです。例外は Alloy の syslog（UDP 1514、LAN）です。

| 役割 | ソフト | ポート（127.0.0.1） |
| --- | --- | --- |
| 収集・保持 | Prometheus | 9090 |
| 通知 | Alertmanager | 9093 |
| 表示 | Grafana | 3000 |
| 疎通・証明書 | blackbox_exporter | 9115 |
| Proxmox | pve-exporter | 9221 |
| UPS | nut_exporter | 9199 |
| UPS の画面（Homarr 用） | PeaNUT | 8080 |
| ログの保存・検索 | Loki | 3100 |
| ログの収集 | Alloy | 12345（syslog は 0.0.0.0:1514/udp） |

収集ジョブは `prometheus`・`blackbox`・`pve`・`nut`・`node`・`game` の6つ（`stacks/monitoring/prometheus/prometheus.yml`）。保持は既定15日（`PROMETHEUS_RETENTION`）で、時系列は `/srv/monitoring`（tarakoserver の HDD、`LABEL=tarako-data`）に置きます。起動は SD カードで、書き込みの多いもの（時系列・ログ・Docker）はすべて HDD です。

ログは Loki（14 日）に集めます。集めるのは tarakoserver の journal・Docker のコンテナのログと、Flint 3 の syslog（UDP 1514、`apply-segments` が設定）です。Grafana の Explore で Loki を選んで見ます。

Grafana のダッシュボードは overview・host・storage・vm-memory・game-server の5枚です（`stacks/monitoring/grafana/provisioning/dashboards/`）。

## 2. 入る

| 入口 | 認証 |
| --- | --- |
| `https://grafana.apextox.dpdns.org` | core-01 の Authentik の OIDC。**`admins` は Admin、`users` は Viewer** |
| Prometheus・Alertmanager の画面 | 入口を出していません。見るなら tarakoserver へSSHして `127.0.0.1` へポートフォワード |

**Authentik（core-01）が落ちていて Grafana に入れないとき**は、ローカル管理者で入ります。パスワードは tarakoserver の `/opt/monitoring-stack/secrets/grafana_admin_password` です。

```bash
ssh -i ~/.ssh/id_ed25519_shake ansible_admin@192.168.10.11 'sudo cat /opt/monitoring-stack/secrets/grafana_admin_password'
```

## 3. アラートが鳴ったら

通知は Discord（webhook）へ届きます。送り先は negitoroserver の外からの見張りと同じチャンネル（`platform/sops/public-monitor.sops.yaml` の `DISCORD_WEBHOOK_URL`）。2026-10-16 にメールから切り替えました。定義は `stacks/monitoring/prometheus/alerts.yml`、送り方は `stacks/monitoring/alertmanager/alertmanager.yml.template`、文の形は `stacks/monitoring/alertmanager/notify.tmpl` です。

| 重さ（`severity`） | Discord | 念押し | 例 |
| --- | --- | --- | --- |
| 🔴 `critical`（緊急） | 送る。直ったら「✅ 直った」 | 4 時間ごと | サービス・機械・VM の応答なし、HDD 外れ、SMART の FAILED・不良セクター、停電 |
| 🟡 `warning`（注意） | 送る。直ったら「✅ 直った」 | 1 日 1 回 | 空き容量・メモリ、サービスの失敗、バックアップの遅れ、ルータの設定崩れ、証明書 |
| ⚪ `info`（記録） | 送らない（Grafana とタッチパネルだけ） | — | 再起動した、収集・点検が止まった（原因はほかの警告で出る） |

- **短い途切れでは送らない。** 応答なし系は 10 分、停電は 5 分続いたら送ります（配線替えの抜き差しで鳴らさない）。
- **同じ種類は 1 通にまとめます**（`group_by: [alertname]`）。
- **親が落ちたら子は送りません**（`inhibit_rules`）：K11 が応答しないときの VM・サービス・HDD、Flint 3 が応答しないときのルータの向こう、HDD が見えないときの HDD 上のサービス、停電中の応答なし。
- **作業中は止められます。** Alertmanager のサイレンス（`alertname != Watchdog`）。タッチパネルの「作業中」（[M02](../development/M02-touch-panel.md)）からも入れられます。外からの見張りには効きません。
- **「どこ」は名前で出します。** node_exporter の機械は Prometheus の `host` ラベル（`prometheus.yml` の node の relabel）、VM は Proxmox の名前、サービスは URL の先頭です。
- webhook が無いと、`manage.py` が送り先を `silent` にします（何も送らない）。送り先を Discord 以外にするときは `discord_configs` を `slack_configs`・`webhook_configs` などに替えます。


### 疎通（availability）

| アラート | 意味 | 最初に見るところ |
| --- | --- | --- |
| `ServiceProbeFailed` | HTTPS名が10分応答しない | そのVMが動いているか。動いていれば中身のコンテナ。[確認と、はまりどころ](verify.md) |
| `CertificateExpiringSoon` | 証明書の期限が14日以内 | 該当ホストのCaddyログ。Cloudflareトークンの権限（ゾーン読み取り＋DNS編集の両方が要る） |

### ノード（node_exporter を入れた4台）

対象は core-01・cloud-01・tarakoserver・apps-01・shakeserver・Flint 3 と Proxmox ホストです（追加の対象は `stacks/monitoring/prometheus/node-targets.yml` に入ります）。media-01・game1 は入れておらず、Proxmox 側の資源で見ます。

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
| `BulkDiskUnmounted` | `/srv/bulk` が見えない。**HDD上のクラウドVMのディスク（media-01 のデータなど）と、NFS越しの game1 も巻き込む** |
| `BulkDiskAlmostFull` | 空きが10%未満 |
| `BulkAreaAlmostFull` | HDDのバックアップ領域・クラウド領域のどちらかが上限の85%を超えた |
| `SmartDeviceUnhealthy` | **SMART自己診断がFAILED。** ディスク交換の検討 |
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

tarakoserver は K11 の外にあるので、K11 が落ちても監視は残ります。ただし tarakoserver 自身や家の回線が落ちると監視も沈黙します。「静かなこと」と「正常なこと」を区別するため、外部の受信点（healthchecks.io）へ常時POSTしています。家の外にある negitoroserver の public-monitor（[公開サイト](web.md)）も、公開サイトを外から見ています。

- `Watchdog`（`severity: none`。`vector(1)` で常時firing）→ Alertmanager の `deadman` 宛先 → 1時間ごとにPOST
- 受信側は Period 12時間 / Grace 1時間。**届かなくなったら向こうから通知が来ます**
- ping URL は `platform/sops/monitoring.sops.yaml` の `WATCHDOG_PING_URL`。**空なら `deadman` は何もせず、`Watchdog` が Discord に流れることもありません**

```bash
sops set platform/sops/monitoring.sops.yaml '["WATCHDOG_PING_URL"]' '"<url>"'
```

ルータは Flint 3（K11 とは別の機械）です。K11 が落ちても通知は届きます。家の回線か Flint 3 が落ちたときは、外部の受信点と negitoroserver だけが気づきます（[障害モード](../architecture/failure-modes.md)）。

## 5. 直す・入れ替える

tarakoserver の `/opt/monitoring-stack` で `manage.py` を使います（`sudo` が要ります）。

| コマンド | 何をする |
| --- | --- |
| `status` | コンテナとターゲットの状態 |
| `reload` | 設定だけを再読込（Prometheus・Alertmanager） |
| `restart` | コンテナを作り直す |
| `up` | 配備・起動 |
| `lock` | イメージのdigestを `compose.lock.yaml` へ固定。**正本はリポジトリの `stacks/monitoring/compose.lock.yaml`** で、Ansibleが配る。更新するときはリポジトリのlockを書き換えて配り直す（配備先だけで `--refresh-images` しない） |
| `backup` | 状態の取得（監視を1分ほど止めて固める）。毎日 `monitoring-backup.timer`（4:00）が2世代残し、K11 の `monitoring-pull.timer`（5:00）が `/srv/bulk/backups/monitoring` へ14日分取り寄せる（ロール `monitoring_backup`） |

アラート規則やスクレイプ先を変えたときは、Gitを直してから Ansible で配り直します。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/monitoring.yml'
```

**Discord の webhook・`WATCHDOG_PING_URL` を変えたときも Alertmanager を再読込します**（2026-09-16に修正。忘れると古い設定のまま動き続けます）。

Proxmox ホスト側の exporter は別Playbookです。

```bash
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-node-exporter.yml
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-nut.yml
```

## 6. 限界

- **tarakoserver が止まると、監視の停止そのものは家の中では誰も検知しません。** 外部のdead man's switchだけが気づきます。固まったときはハードウェアのウォッチドッグ（15秒）が再起動します
- tarakoserver の電源（Switch の AC アダプター）は、重い処理で電圧不足の記録が出ることがあります（`vcgencmd get_throttled`）
- media-01・game1 には node_exporter を入れていないので、ゲスト内の空きメモリ・fs は見えません（Proxmox側の割当と使用量だけ）
- 保持は15日です。それより古い傾向は残りません

## 関連

- [M01 監視](../development/M01-monitoring.md) — 設計の経緯と実測記録（正本）
- [電源とUPS](power.md) — UPSと停電時の停止順
- [障害モードと単一障害点](../architecture/failure-modes.md) — 何が止まると何が見えなくなるか
- [確認と、はまりどころ](verify.md) — 実際に踏んだ落とし穴
