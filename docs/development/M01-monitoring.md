---
title: M01 監視（Prometheus・Grafana）
updated: 2026-09-23
section: 開発計画
audience: 開発者
tags:
  - plan
  - monitoring
---

# M01 監視（Prometheus・Grafana）

> **更新日** 2026-09-23 ・ **区分** 開発計画 ・ **読む人** 開発者

**区分**: 新規実装 ・ **状態**: **配備済み（monitor-01 `192.168.10.102`、`https://grafana.apextox.dpdns.org`）。全ターゲットup、UPS取得、メール通知を実機確認。HomarrのProxmox連携＋System Health／UPS（PeaNUT）ウィジェットとボード整列まで完了。node_exporterの資源アラート、dead man's switch（healthchecks.ioで有効）、管理DBバックアップの最終成功メトリクス、低電池シャットダウン（upsmon）を追加済み。VMごとの実使用メモリを見るダッシュボード（Shake Lab VM memory）と、ホストのメモリ逼迫アラートを追加済み。game1のホスト・セッション使用量をGrafanaで見るゲームサーバー使用量ダッシュボードを追加済み。**Proxmoxホストへnode_exporterとSMART/NVMeのtextfile collectorを導入し、ホスト詳細（Shake Lab host）・ストレージ詳細（Shake Lab storage）の2ダッシュボードと、6TB HDDの容量・SMART・マウント消失アラートを追加済み。**

## 目的・現状・配備先

サービスの稼働とホスト資源を1か所で見える化し、停止・容量・UPS異常に気づけるようにする。Homarrのタイル状態は「その場で赤/緑」を見るだけで、履歴・通知・証明書期限・資源推移を持たない。監視は別のポータル（Grafana）にする。

配備先: **monitor-01（新規cloud VM）**。開始予算は2vCPU／2GiB、OS32GiB＋データ32GiB。Prometheusの保持期間と実測で確定する。`platform/terraform/services/monitor/` の宣言と `stacks/monitoring/` のComposeで作る。基盤VM（`10-platform`）やservices-01へ同居させない。

## 構成

| 役割 | ソフト | 備考 |
| --- | --- | --- |
| 収集・保持 | Prometheus | データディスク32GiB、保持は15日開始。外部公開しない |
| 表示・通知 | Grafana | `grafana.apextox.dpdns.org`（tls_proxy）。identityのOIDC＋ローカル管理者。ダッシュボードは overview（稼働・資源・UPS）、 VM memory（VMごとのメモリ実使用）、ゲームサーバー使用量（game1のホスト・セッション） |
| 疎通 | blackbox_exporter | `dns.yaml`のHTTPS名をprobe。証明書期限も取れる |
| VM資源 | node_exporter | services-01・identity・cloud-01・storage-s3・monitor-01の5台。media-01・game1は入れず、Proxmox側（pve-exporter）の資源で見る |
| ホスト資源・SMART | node_exporter（ホスト） | Proxmoxホスト。デバイス別I/O・fs空き・hwmon温度・SMART/NVMe（2026-09-23追加。下の節） |
| Proxmox | pve-exporter | 読み取り専用APIトークンでノード・VMを収集 |
| UPS | nut_exporter | ProxmoxホストのNUTサーバー（`:3493`）を読む |
| 通知 | Alertmanager | Prometheusのアラートを既存の`smtp.sops.yaml`（Gmail）でメール通知。`Watchdog`だけは外部のdead man's switch（healthchecks.io）へ送る |

アラート規則（`stacks/monitoring/prometheus/alerts.yml`）:

- **疎通**: `probe_success == 0`（5分）、証明書期限14日。
- **ノード**（node_exporterを入れたVM）: exporterのダウン、`/`などの空き15%未満、空きメモリ10%未満、OOM kill、systemd unitのfailed、起動時刻の変化（計画外再起動）。メトリクスは取得済みなので規則だけを置く。
- **バックアップ**: `backup_last_success_timestamp_seconds`の停滞（36時間超）と**欠測そのもの**（`absent()`）。
- **Proxmox・UPS**: ゲストのダウン、ノードのディスク85%、**ホスト**のメモリ使用率90%超、UPSがバッテリー動作中。ゲストの `pve_memory_usage_bytes` はゲスト内のキャッシュを含むため上限比では張り付きが常態になり、規則にはしない（VMごとの実使用はダッシュボードで見る）。ゲスト内の実圧迫は node_exporter の `NodeMemoryLow`（`node_memory_MemAvailable_bytes`）が受け持つ。
- **dead man's switch**: `Watchdog`（`vector(1)`で常時firing）。Alertmanagerから外部（healthchecks.io等）へ送り続け、外部側で「届かなければ監視系が死んでいる」と判定する。ping URLは`monitoring.sops.yaml`の`WATCHDOG_PING_URL`（空なら`deadman`宛先は何もせず、`Watchdog`がメールに流れることもない）。

## dead man's switch（外部監視・有効）

monitor-01はK11（Proxmoxホスト）の上にあるため、K11ごと落ちると監視も沈黙する。「静かなこと」と「正常なこと」を区別するには外部の受信点が要る。

- 受信点: **healthchecks.io**（無料枠）。チェック`shake-cloud watchdog`。
- 設定: Simple / **Period 12時間 / Grace 1時間** / リクエストは**POSTのみ**。通知はメール（同じGmailでもhealthchecks.io側のサーバーから届くので、うちのSMTP障害には影響されない。別アドレスならGoogleアカウント障害も分離できる）。
- 経路: `Watchdog`（常時firing）→ Alertmanagerの`deadman`宛先 → 1時間ごとにPOST。ping URLは`monitoring.sops.yaml`の`WATCHDOG_PING_URL`。空なら`deadman`は何もせず、`Watchdog`がメールに流れることもない。
- 差し替え: `sops set platform/sops/monitoring.sops.yaml '["WATCHDOG_PING_URL"]' '"<url>"'` → `monitoring.yml`を流す。`.env`のSMTP・WATCHDOG変更でもAlertmanagerを再読込する（2026-09-16に修正）。
- 試験: 受信点を一時的に5分/5分にして`docker stop monitoring-alertmanager-1` → 10分ほどで通知 → `docker start`。**鳴ることを一度見たら12時間/1時間に戻す。**
- K11の外に別電源の機器を置けるようになったら、2つ目のwebhookとして追加する（[電源とUPS](../operations/power.md#停電で自動停止させる実装済み)）。**いまはルータもK11上のVMなので、K11が落ちると通知経路ごと失われる。**

## 管理DBバックアップの見える化

`cloud-backup.timer`（cloud-01、毎日03:40）の成否をメトリクスにする。

- 成功時に`manage.py backup-metric`がnode_exporterのtextfile collectorへ`backup_last_success_timestamp_seconds`を1行書く（失敗時は更新されない）。
- 配備時にも既存世代から現在値を書く（無ければ0）。欠測1時間・停滞36時間でメールする。
- 外部コピー（[O01](O01-cloud-backup.md)）を足す前にこれを入れて、「やったつもり」を防ぐ。

## UPS（CyberPower CP1200PFCLCDJP）

UPSはUSBでProxmoxホストに接続されている。NUTはUSBを持つホストで動かす。

1. ホストに`nut`（`usbhid-ups`＋`upsd`）をAnsibleで導入する。`upsmon`（`nut-monitor`）も有効にし、低電池時に**k8s worker → control plane → ホスト**の順に停止する（[電源とUPS](../operations/power.md#停電で自動停止させる実装済み)）。停止スクリプトは`/usr/local/sbin/pve-ups-shutdown`。
2. `upsd`は監視LANだけへ公開し、nut_exporter（monitor-01）が読む。UPSの状態はGrafanaのダッシュボードとHomarrのUPSウィジェット（PeaNUT経由）へ出す。`monitor`ユーザーは読み取り専用のまま、upsmon専用ユーザーを分ける。
3. **前提: ProxmoxホストへのSSH公開鍵登録（人）**。`platform/ansible/pve.ini`の`root`接続を使う。鍵は`~/.ssh/id_ed25519_pve`。

## VMメモリの配分見直し（2026-09-21追加）

「メモリがカツカツ」を感覚でなく実測で判断するためのダッシュボードを足した。Grafanaの **Shake Lab VM memory**（`stacks/monitoring/grafana/provisioning/dashboards/vm-memory.json`）。

- 上段: ホストの実使用率、ゲストの実使用合計、割り当て上限合計。
- **VMごとの実使用メモリ**: 凡例の `Max` が選択期間のピーク。既定は7日表示。
- **VMごとの割り当て比**: `pve_memory_usage_bytes / pve_memory_size_bytes`。90%超が続くVMは上限に張り付いている。
- **VMごとの割り当て上限**: `memory_mib` を変えた結果が段差で見える。
- 名前は `pve_guest_info` の `name` から引く。VMID だけでは人は判断できない。

手順: ピークが上限より十分低いVMの `memory_mib` を下げ、その分を張り付いているVMへ回す。静的VMは `platform/terraform/hosts.yaml`、cloud VM（media-01・monitor-01等）はクラウドの flavor／`memory_mib` を変える。バルーニングは使用中の分を返さないので、**再配分の判断は実使用のピークで行う**（[配分の考え方](../architecture/operations.md)）。

ゲストの上限比をそのままアラートにしない理由: `pve_memory_usage_bytes` はゲスト内のページキャッシュを含むRSSなので、game1・services-01 のようにキャッシュで上限まで使うVMが常態になる。ゲスト内の実圧迫（`MemAvailable`）は node_exporter を入れた5台で `NodeMemoryLow` が見ており、media-01・game1 にも必要になったら node_exporter を足す。

## ゲームVMの使用量ダッシュボード（2026-09-22追加）

game1のホストとゲームセッションの使用量をGrafanaで見る。ダッシュボードは **ゲームサーバー使用量**（`stacks/monitoring/grafana/provisioning/dashboards/game-server.json`、uid `shakelab-game`）。

- ゲームポータルがW07 metricsをPrometheus形式で公開する（`https://play.apextox.dpdns.org/metrics`、Bearerトークン）。トークンの正本は `platform/sops/monitoring.sops.yaml` の `GAME_METRICS_TOKEN` で、Ansibleが `secrets/game_metrics_token`（0444、Prometheusのnobodyが読める）へ写し、Prometheusだけにmountする。
- Prometheusの `game` ジョブは15秒間隔。targetは**ホスト名**で指定する。CaddyはHostヘッダでサイトを振り分けるため、IP指定だと空の200が返り `up=1` のまま0サンプルになる。
- ホスト: CPU・メモリ・GPU使用率・GPU温度・ディスクI/O・ネットワーク。セッション: CPU・メモリ・ディスクI/Oと実行中一覧テーブル。
- ポータル経由の起動はruntime instance、ランチャー（Pegasus）起動はホストの `gs-launch` プロセスからタイトルとownerを補い、同じセッションとして表示する。
- セッション別ネットワークは、Netdataがcgroupのネットワーク値を収集しないため表示しない（推定値で埋めない）。

## ホスト資源とストレージ・SMART（2026-09-23追加）

Proxmoxホスト（apextox）にもnode_exporterを入れ、VM側からは見えない資源を取る。

- 配備: `platform/ansible/pve-node-exporter.yml`（ロール `pve_node_exporter`）。Debianの `prometheus-node-exporter` と `smartmontools` を入れる。
- 収集: Prometheusの `node` ジョブへ `192.168.10.10:9100` を追加（`node-targets.yml`）。SMARTとNVMeはパッケージ同梱のtextfile collector（`prometheus-node-exporter-smartmon.timer`・`-nvme.timer`、15分ごと）が `smartmon_*`・`nvme_*` を書く。`smartctl --scan-open` が `/dev/sda -d sat`（6TB HDD）と `/dev/nvme0 -d nvme` を見つける。
- ダッシュボード: **Shake Lab host**（`host.json`、uid `shakelab-host`）はCPUモード別・周波数・hwmon温度・メモリ・NIC・**物理デバイス別I/O**・fs空き・systemd failed。**Shake Lab storage**（`storage.json`、uid `shakelab-storage`）は6TB HDDの容量・I/O・SMART（健康・温度・セクター/CRC）・NVMe寿命/異常・`bulk-backup` の使用量・マウント状態に加え、**NVMe総書込量・書込速度とHDDのLoad Cycle／Start-Stop／Power-On時間**（寿命ペース）。overviewには使用率・空き・SMART・NVMe寿命の4枚を追加。
- アラート（`alerts.yml` の `storage` グループ）: マウント消失（`BulkDiskUnmounted`）、空き10%未満、SMART FAILED、SMARTが読めない（USB切断）、セクター異常、CRC増加、50℃超、SMART収集停止、NVMe寿命80%超。汎用の `NodeFilesystemAlmostFull` からは `/srv/bulk` を外して二重通知を避ける。
- 見る場所: `https://grafana.apextox.dpdns.org` の Shake Lab フォルダ。ディスクの運用は[共有バルクストレージ](../operations/bulk-storage.md)。

## Homarrへの表示

- **Proxmox連携＋System Healthウィジェット**: ノードのCPU/RAM/ディスクとVM状態。読み取り専用トークン（`homarr@pve`、PVEAuditor）を`00-bootstrap`で作り、SOPSへ保存して配備する。
- **UPSウィジェット**: HomarrはNUT直接ではなくPeaNUT（NUTのRESTラッパー）を読む。PeaNUTをmonitor-01へ置き、ホストの`upsd`へ接続する。
- **Grafanaタイル**: 監視ポータルへの入口。
- 静的なスペック（Ryzen 9 8945HS／64GB／1TB NVMe）はボードのノートに記載する。
- 連携とウィジェットの作成はtRPC／OpenAPIを叩くスクリプトで自動化する。**Homarrの内部APIに依存するため、版の更新時に再検証が必要**（[W01](W01-homarr.md)と同じ性質）。

## 変更範囲と実装

1. `platform/terraform/services/monitor/`にVM・SG・データディスク・SSH鍵を宣言する。stateは`shake-cloud/services/monitor/terraform.tfstate`（I05のservices分岐）。
2. `stacks/monitoring/`にPrometheus・Grafana・blackbox_exporter・node_exporter・pve-exporter・nut_exporter・PeaNUTのComposeを作る。秘密値は`manage.py`が生成し、GrafanaのSMTPとOIDC秘密はSOPS／identityから配備する。
3. `platform/ansible/roles/monitoring/`と`monitoring.yml`で配備する。node_exporterは各VMへ別playbookで配る。
4. `platform/terraform/dns.yaml`に`grafana`を追加し、`tls_proxy`でHTTPS入口を作る。identityに`grafana` OIDCクライアントを追加する。
5. ProxmoxホストのNUTとnode_exporterを`platform/ansible/`のPVE向けplaybookで導入する（`pve.ini`）。
6. Grafanaのデータソース・ダッシュボード・アラートをプロビジョニング（ファイル）で宣言し、再作成でも同じ画面に戻す。
7. Homarrの連携・ウィジェットをスクリプトで作成する。

## 依存と並列作業

- **開発開始:** スタックとGrafanaの宣言はVM完成前に作れる。
- **実機:** [I01](I01-resources.md)の余力（monitor-01 2GiB）、ProxmoxホストのSSH鍵、identityのOIDCクライアント、`smtp.sops.yaml`。
- **競合:** `dns.yaml`・`tools/tf`・identityのクライアント追加は他W担当と調整する。ホストのNUT導入はPVEホストの作業として単独で行い、VM再起動を伴う手順を分離する。

## 検証・完了条件

- すべての対象がPrometheusのターゲットで`up`になり、Grafanaで資源・疎通・UPSが見える。
- サービスを1つ止めると、5分以内にアラートメールが届き、復旧で解除される。
- ノードのディスク・メモリ・OOM・systemd failed・再起動が規則で鳴る（[検証](#検証)）。
- monitor-01を再作成しても、宣言済みのデータソース・ダッシュボード・アラートが復元される。
- 保持期間とデータディスクの実使用から容量を再計算し、[配分表](../architecture/operations.md#measured-budget)へ実測を渡す。
- ホストNUTの低電池シャットダウンは`PVE_UPS_SHUTDOWN_DRY_RUN=1`で順番を確認してから有効化する（実停電の試験はUPSのバッテリーで1回行う）。

<a id="検証"></a>
## 検証

- アラート規則: `manage.py reload`後にPrometheusの`/api/v1/rules`で`health=ok`を確認。
- ノード規則: 一時的に閾値を上げた式を`/api/v1/query`で評価して鳴ることを確認し、実配備では戻す。
- バックアップ: cloud-01で`manage.py backup`（手動）→ `backup_last_success_timestamp_seconds`が更新されるのをPrometheusで確認。
- upsmon: `systemctl status nut-monitor`がactive、`upsc cyberpower@localhost ups.status`が`OL`。`journalctl -t pve-ups-shutdown`でdry-runのログを確認。
- dead man's switch: Alertmanagerの`alertmanager_notifications_total{integration="webhook"}`が増え、`..._failed_total`が0（healthchecks.ioがPOSTを受理している）。
- blackboxの設定変更: `manage.py reload`がPrometheus・Alertmanagerと一緒にblackboxも再起動する（2026-09-17に追加。再起動漏れで全プローブが400になった実例あり）。
