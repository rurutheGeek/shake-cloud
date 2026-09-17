# M01 監視（Prometheus・Grafana）

更新日: 2026-09-16。区分: **新規実装**。状態: **配備済み（monitor-01 `192.168.10.102`、`https://grafana.apextox.dpdns.org`）。全ターゲットup、UPS取得、メール通知を実機確認。HomarrのProxmox連携＋System Health／UPS（PeaNUT）ウィジェットとボード整列まで完了。node_exporterの資源アラート、dead man's switch（healthchecks.ioで有効）、管理DBバックアップの最終成功メトリクス、低電池シャットダウン（upsmon）を追加済み**。

## 目的・現状・配備先

サービスの稼働とホスト資源を1か所で見える化し、停止・容量・UPS異常に気づけるようにする。Homarrのタイル状態は「その場で赤/緑」を見るだけで、履歴・通知・証明書期限・資源推移を持たない。監視は別のポータル（Grafana）にする。

配備先: **monitor-01（新規cloud VM）**。開始予算は2vCPU／2GiB、OS32GiB＋データ32GiB。Prometheusの保持期間と実測で確定する。`platform/terraform/services/monitor/` の宣言と `stacks/monitoring/` のComposeで作る。基盤VM（`10-platform`）やservices-01へ同居させない。

## 構成

| 役割 | ソフト | 備考 |
| --- | --- | --- |
| 収集・保持 | Prometheus | データディスク32GiB、保持は15日開始。外部公開しない |
| 表示・通知 | Grafana | `grafana.apextox.dpdns.org`（tls_proxy）。identityのOIDC＋ローカル管理者 |
| 疎通 | blackbox_exporter | `dns.yaml`のHTTPS名をprobe。証明書期限も取れる |
| VM資源 | node_exporter | services-01・identity・cloud-01・storage-s3・monitor-01の5台。media-01・game1は入れず、Proxmox側（pve-exporter）の資源で見る |
| Proxmox | pve-exporter | 読み取り専用APIトークンでノード・VMを収集 |
| UPS | nut_exporter | ProxmoxホストのNUTサーバー（`:3493`）を読む |
| 通知 | Alertmanager | Prometheusのアラートを既存の`smtp.sops.yaml`（Gmail）でメール通知。`Watchdog`だけは外部のdead man's switch（healthchecks.io）へ送る |

アラート規則（`stacks/monitoring/prometheus/alerts.yml`）:

- **疎通**: `probe_success == 0`（5分）、証明書期限14日。
- **ノード**（node_exporterを入れたVM）: exporterのダウン、`/`などの空き15%未満、空きメモリ10%未満、OOM kill、systemd unitのfailed、起動時刻の変化（計画外再起動）。メトリクスは取得済みなので規則だけを置く。
- **バックアップ**: `backup_last_success_timestamp_seconds`の停滞（36時間超）と**欠測そのもの**（`absent()`）。
- **Proxmox・UPS**: ゲストのダウン、ノードのディスク85%、UPSがバッテリー動作中。
- **dead man's switch**: `Watchdog`（`vector(1)`で常時firing）。Alertmanagerから外部（healthchecks.io等）へ送り続け、外部側で「届かなければ監視系が死んでいる」と判定する。ping URLは`monitoring.sops.yaml`の`WATCHDOG_PING_URL`（空なら`deadman`宛先は何もせず、`Watchdog`がメールに流れることもない）。

## dead man's switch（外部監視・有効）

monitor-01はK11（Proxmoxホスト）の上にあるため、K11ごと落ちると監視も沈黙する。「静かなこと」と「正常なこと」を区別するには外部の受信点が要る。

- 受信点: **healthchecks.io**（無料枠）。チェック`shake-cloud watchdog`。
- 設定: Simple / **Period 12時間 / Grace 1時間** / リクエストは**POSTのみ**。通知はメール（同じGmailでもhealthchecks.io側のサーバーから届くので、うちのSMTP障害には影響されない。別アドレスならGoogleアカウント障害も分離できる）。
- 経路: `Watchdog`（常時firing）→ Alertmanagerの`deadman`宛先 → 1時間ごとにPOST。ping URLは`monitoring.sops.yaml`の`WATCHDOG_PING_URL`。空なら`deadman`は何もせず、`Watchdog`がメールに流れることもない。
- 差し替え: `sops set platform/sops/monitoring.sops.yaml '["WATCHDOG_PING_URL"]' '"<url>"'` → `monitoring.yml`を流す。`.env`のSMTP・WATCHDOG変更でもAlertmanagerを再読込する（2026-09-16に修正）。
- 試験: 受信点を一時的に5分/5分にして`docker stop monitoring-alertmanager-1` → 10分ほどで通知 → `docker start`。**鳴ることを一度見たら12時間/1時間に戻す。**
- ラズパイを別電源で動かせるようになったら、2つ目のwebhookとして追加する（[電源とUPS](../operations/power.md#停電で自動停止させる実装済み)）。

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

## 検証

- アラート規則: `manage.py reload`後にPrometheusの`/api/v1/rules`で`health=ok`を確認。
- ノード規則: 一時的に閾値を上げた式を`/api/v1/query`で評価して鳴ることを確認し、実配備では戻す。
- バックアップ: cloud-01で`manage.py backup`（手動）→ `backup_last_success_timestamp_seconds`が更新されるのをPrometheusで確認。
- upsmon: `systemctl status nut-monitor`がactive、`upsc cyberpower@localhost ups.status`が`OL`。`journalctl -t pve-ups-shutdown`でdry-runのログを確認。
- dead man's switch: Alertmanagerの`alertmanager_notifications_total{integration="webhook"}`が増え、`..._failed_total`が0（healthchecks.ioがPOSTを受理している）。
