# M01 監視（Prometheus・Grafana）

更新日: 2026-09-12。区分: **新規実装**。状態: **配備済み（monitor-01 `192.168.10.102`、`https://grafana.apextox.dpdns.org`）。全24ターゲットup、UPS取得、メール通知1通を実機確認。残りはHomarrのProxmox/PeaNUT連携、低電池シャットダウン、ダッシュボード拡充**。

## 目的・現状・配備先

サービスの稼働とホスト資源を1か所で見える化し、停止・容量・UPS異常に気づけるようにする。Homarrのタイル状態は「その場で赤/緑」を見るだけで、履歴・通知・証明書期限・資源推移を持たない。監視は別のポータル（Grafana）にする。

配備先: **monitor-01（新規cloud VM）**。開始予算は2vCPU／2GiB、OS32GiB＋データ32GiB。Prometheusの保持期間と実測で確定する。`platform/terraform/services/monitor/` の宣言と `stacks/monitoring/` のComposeで作る。基盤VM（`10-platform`）やservices-01へ同居させない。

## 構成

| 役割 | ソフト | 備考 |
| --- | --- | --- |
| 収集・保持 | Prometheus | データディスク32GiB、保持は15日開始。外部公開しない |
| 表示・通知 | Grafana | `grafana.apextox.dpdns.org`（tls_proxy）。identityのOIDC＋ローカル管理者 |
| 疎通 | blackbox_exporter | `dns.yaml`のHTTPS名をprobe。証明書期限も取れる |
| VM資源 | node_exporter | 各VM（services-01・identity・cloud-01・storage-s3・media-01・monitor-01）。game1は導入可否を別途 |
| Proxmox | pve-exporter | 読み取り専用APIトークンでノード・VMを収集 |
| UPS | nut_exporter | ProxmoxホストのNUTサーバー（`:3493`）を読む |
| 通知 | Alertmanager | Prometheusのアラートを既存の`smtp.sops.yaml`（Gmail）でメール通知 |

アラート例: `probe_success == 0`（5分）、ノード/VMのダウン、ディスク使用率85%、証明書期限14日、UPSがバッテリー動作。

## UPS（CyberPower CP1200PFCLCDJP）

UPSはUSBでProxmoxホストに接続されている。NUTはUSBを持つホストで動かす。

1. ホストに`nut`（`usbhid-ups`＋`upsd`）をAnsibleで導入する。`upsmon`も入れ、低電池時にVMを順に停止してホストをシャットダウンする。
2. `upsd`は監視LANだけへ公開し、nut_exporter（monitor-01）が読む。UPSの状態はGrafanaのダッシュボードとHomarrのUPSウィジェット（PeaNUT経由）へ出す。
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
- monitor-01を再作成しても、宣言済みのデータソース・ダッシュボード・アラートが復元される。
- 保持期間とデータディスクの実使用から容量を再計算し、[配分表](../architecture/operations.md#measured-budget)へ実測を渡す。
- ホストNUTの低電池シャットダウンは隔離環境で手順を確認してから有効化する。
