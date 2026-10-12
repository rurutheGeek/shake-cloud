---
title: 監視（monitor-01）
updated: 2026-10-12
section: 運用手順
audience: 管理者
tags:
  - ops
  - monitoring
---

# 監視（monitor-01）

> **更新日** 2026-10-12 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 稼働中。`https://grafana.apextox.dpdns.org`（core-01 の Authentik の OIDC）。

**アラートが鳴ったときと、監視そのものを直すときのページ**です。なぜその構成にしたか・いつ何を足したかの経緯は[M01 監視](../development/M01-monitoring.md)が正本で、ここには書きません。

## 1. 何が動いているか

monitor-01（基盤VM、VMID 120、`192.168.10.210`）の独立Composeです。2026-10-03 に、クラウドVM（`192.168.10.102`）から基盤VMへ作り直しました。**サービス自身のポートはすべて `127.0.0.1` に閉じて**おり、入口は同じVMのCaddy（`stacks/tls-proxy/`）だけです。

| 役割 | ソフト | ポート（127.0.0.1） |
| --- | --- | --- |
| 収集・保持 | Prometheus | 9090 |
| 通知 | Alertmanager | 9093 |
| 表示 | Grafana | 3000 |
| 疎通・証明書 | blackbox_exporter | 9115 |
| Proxmox | pve-exporter | 9221 |
| UPS | nut_exporter | 9199 |

収集ジョブは `prometheus`・`blackbox`・`pve`・`nut`・`node`・`game` の6つ（`stacks/monitoring/prometheus/prometheus.yml`）。保持は既定15日（`PROMETHEUS_RETENTION`）で、時系列は `/srv/monitoring`（OSと同じディスク）に置きます。

Grafana のダッシュボードは overview・host・storage・vm-memory・game-server の5枚です（`stacks/monitoring/grafana/provisioning/dashboards/`）。

## 2. 入る

| 入口 | 認証 |
| --- | --- |
| `https://grafana.apextox.dpdns.org` | core-01 の Authentik の OIDC。**`admins` は Admin、`users` は Viewer** |
| Prometheus・Alertmanager の画面 | 入口を出していません。見るなら monitor-01 へSSHして `127.0.0.1` へポートフォワード |

**Authentik（core-01）が落ちていて Grafana に入れないとき**は、ローカル管理者で入ります。パスワードは monitor-01 の `/opt/monitoring-stack/secrets/grafana_admin_password` です。

```bash
ssh debian@192.168.10.210 'sudo cat /opt/monitoring-stack/secrets/grafana_admin_password'
```

## 3. アラートが鳴ったら

通知はメール（`smtp.sops.yaml` の Gmail）です。定義は `stacks/monitoring/prometheus/alerts.yml`。**`severity: critical` は `SmartDeviceUnhealthy` の1つだけ**で、残りは `warning` です。

### 疎通（availability）

| アラート | 意味 | 最初に見るところ |
| --- | --- | --- |
| `ServiceProbeFailed` | HTTPS名が5分応答しない | そのVMが動いているか。動いていれば中身のコンテナ。[確認と、はまりどころ](verify.md) |
| `CertificateExpiringSoon` | 証明書の期限が14日以内 | 該当ホストのCaddyログ。Cloudflareトークンの権限（ゾーン読み取り＋DNS編集の両方が要る） |

<a id="node-alerts"></a>
### ノード（node_exporter を入れたホスト）

対象は core-01・cloud-01・monitor-01・apps-01・web-01 と Proxmox ホストです（正本は `stacks/monitoring/prometheus/node-targets.yml`。ここへ足すと監視対象になります）。media-01・game-01 は入れておらず、Proxmox 側の資源で見ます。

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

## 4. K11の外から見る（2系統）

monitor-01 は K11 の上にあるので、**K11ごと落ちると監視も沈黙します。** 「静かなこと」と「正常なこと」を区別する仕組みを、外に2つ置いています。

| 系統 | どこから | 何を見る | 通知 |
| --- | --- | --- | --- |
| dead man's switch | 外部の受信点（healthchecks.io） | monitor-01 からのPOSTが**途切れないこと** | 届かなくなったら受信点から来る |
| たらこサーバ（Pi 4） | K11とは別筐体・別電源。tailnet 経由 | 公開サイト4つと `grafana` の**応答** | Discord（状態が変わったときだけ） |

### dead man's switch（沈黙を検知する）

外部の受信点（healthchecks.io）へ常時POSTしています。

- `Watchdog`（`severity: none`。`vector(1)` で常時firing）→ Alertmanager の `deadman` 宛先 → 1時間ごとにPOST
- 受信側は Period 12時間 / Grace 1時間。**届かなくなったら向こうから通知が来ます**
- ping URL は `platform/sops/monitoring.sops.yaml` の `WATCHDOG_PING_URL`。**空なら `deadman` は何もせず、`Watchdog` がメールに流れることもありません**

```bash
sops set platform/sops/monitoring.sops.yaml '["WATCHDOG_PING_URL"]' '"<url>"'
```

**いまルータも K11 上のVMなので、K11が落ちると通知経路ごと失われます**（[障害モード](../architecture/failure-modes.md)）。外に出した2系統だけが残ります。

<a id="public-monitor"></a>
### たらこサーバ（外から応答を見る）

ミニPC（K11）の外から、公開サイトと監視の入口を見ます。配備は `platform/ansible/public-monitor.yml`（ロール `public_monitor`、インベントリは `platform/ansible/outpost.ini`）。

| 項目 | 値 |
| --- | --- |
| 動かす場所 | たらこサーバ（Raspberry Pi 4、tailnet 上）。systemd timer で**1分ごと** |
| 見る先 | `shake`・`pkhack`・`ayahuya`・ルート（`ruruthegeek.dpdns.org` ゾーン）と `grafana.apextox.dpdns.org` |
| 合格とみなす応答 | 公開サイトは 200/301/302、Grafana は 200/301/302/401/403 |
| 通知 | Discord Webhook。**状態が変わったときだけ**（`platform/sops/public-monitor.sops.yaml`） |
| 状態 | たらこサーバの `/var/lib/public-monitor/<名前>` |

**誤報を抑える仕掛けが2つあります。** どちらも 2026-10-06 の誤報を受けて入れました。

- 名前引きは **DoH（`https://1.1.1.1/dns-query`）** で行います。tailnet の DNS（`100.100.100.100`）が詰まると、サイトは無事なのに監視だけNGになりました。
- 状態の確定には **2回連続**の一致が要ります（1分間隔なので、確定までおよそ2分）。加えて1回の判定の中で5秒あけて3回まで取り直します。

テスト通知は `--test` です。

```bash
ssh <たらこサーバ> 'sudo /usr/local/bin/public-monitor.sh --test'
```

**`grafana` の確認は経路のテストも兼ねています。** `grafana.apextox.dpdns.org` は内部IPを返すので、たらこサーバから届くには tailnet → router-01 の subnet router → core-01 の Caddy → monitor-01 が全部生きている必要があります。ここがNGなら、Grafana だけでなくその経路のどこかが落ちています。

## 5. 直す・入れ替える

monitor-01 の `/opt/monitoring-stack` で `manage.py` を使います（`sudo` が要ります）。

| コマンド | 何をする |
| --- | --- |
| `status` | コンテナとターゲットの状態 |
| `reload` | 設定だけを再読込（Prometheus・Alertmanager） |
| `restart` | コンテナを作り直す |
| `up` | 配備・起動 |
| `lock` | イメージのdigestを `compose.lock.yaml` へ固定。**正本はリポジトリの `stacks/monitoring/compose.lock.yaml`** で、Ansibleが配る。更新するときはリポジトリのlockを書き換えて配り直す（配備先だけで `--refresh-images` しない） |
| `backup` | 状態の取得 |

アラート規則やスクレイプ先を変えたときは、Gitを直してから Ansible で配り直します。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/monitoring.yml'
```

**`.env` の SMTP・`WATCHDOG_PING_URL` を変えたときも Alertmanager を再読込します**（2026-09-16に修正。忘れると古い設定のまま動き続けます）。

Proxmox ホスト側の exporter は別Playbookです。

```bash
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-node-exporter.yml
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-nut.yml
```

## 6. 限界

- 監視対象と監視基盤が同じ物理ホストにあります。K11障害は両方を同時に失うので、気づけるのは**外に出した2系統だけ**です（§4）
- **たらこサーバ自身の沈黙は誰も検知しません。** 落ちても通知は来ず、「静かで平常」と区別できません。dead man's switch と二重にしてあるのはこのためです
- たらこサーバが見ているのは**応答コードだけ**です。中身が壊れていても 200 なら通ります
- media-01・game-01 には node_exporter を入れていないので、ゲスト内の空きメモリ・fs は見えません（Proxmox側の割当と使用量だけ）
- 保持は15日です。それより古い傾向は残りません

## 関連

- [公開サイト](web.md) — たらこサーバが見ている対象と、公開の経路
- [M01 監視](../development/M01-monitoring.md) — 設計の経緯と実測記録（正本）
- [電源とUPS](power.md) — UPSと停電時の停止順
- [障害モードと単一障害点](../architecture/failure-modes.md) — 何が止まると何が見えなくなるか
- [確認と、はまりどころ](verify.md) — 実際に踏んだ落とし穴
