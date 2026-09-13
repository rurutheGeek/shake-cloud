# 配備・Git管理・ストレージ・復旧

[構成案トップ](index.md)へ戻る。記載する容量は初期設計値で、実測保証値ではありません。

更新日: 2026-09-13。状態: **配置方針とI01・I02の実施記録を併記した資料。Homarr・Vaultwarden・Home Assistant（services-01）と、Nextcloud・Kavita・Navidrome（media-01）、監視（monitor-01）、CUPS印刷・LocalSend受信機は配備済みで、旧環境からのメディアデータ移行とVPNは未完了**。実機の状態は[配備台帳](../operations/handover.md)、個別作業の仕様と進捗は[並列開発計画](../development/index.md)を正とします。

<a id="resource-budget"></a>
## VMと初期リソース配分

**増設は現有ホストへのVM追加です。ハードウェアの増設提案は今回の範囲に含めません。** 常時使う軽いサービスはservices-01、ゲーム・AIはgame1、メディアはmedia-01へまとめます。専用AI VM・HAOS VM・VPN VMは追加しません。

| 配置 | vCPU / RAMの計画値 | ディスク | 機能・起動方針 |
| --- | --- | --- | --- |
| Proxmox | ホスト用6GiB枠 | 現行パーティション維持 | ホストとキャッシュの予算。実消費は測定 |
| services-01（150） | 2 / 4GiB（増枠は実測後） | 現行容量とデータ量を実測 | NetBox・MkDocs・Home Assistant・Homarr・Vaultwarden・Eufy中継・印刷API（CUPS）。VPNは追加予定。常時。`05-seed`の所有を維持 |
| identity（110） | 2 / 4GiB（宣言値） | 32GiB | Authentikと専用DB。常時 |
| cloud-01（140） | 2 / 2GiB（宣言値） | 40GiB | クラウドAPIと管理DB。常時 |
| storage-s3（130） | 2 / 1GiB（宣言値） | OS16＋データ32GiB | Garage。常時 |
| k8s-cp-01（200） | 2 / 3GiB（固定） | 32GiB | control plane。既存構成維持 |
| k8s-worker-01（210） | 4 / 8GiB（固定） | OS32＋データ64GiB | AWX・CNPG・Knative。既存構成維持 |
| k8s-worker-02（211） | 4 / 8GiB（固定） | OS32＋データ48GiB | 停止中。起動・joinは必要量から判断 |
| game1（100、cloudプール） | 8 / 現行12GiB、同居負荷を測って16GiB候補 | 現行維持。AIデータ・モデル・ROM容量を実測 | ゲーム・RomM・Ollama・ポケモンAI・汎用RAG・Bot。VM停止中は一式停止 |
| media-01（cloud VM、作成済み） | 4 / 6GiB | OS32＋データ64GiB | Nextcloud・Calendar・Tasks・Kavita・Navidrome・Picard・LocalSend受信機と各依存DB（MeTubeは追加予定）。機能群をVM単位で停止 |
| monitor-01（cloud VM、作成済み） | 2 / 2GiB（宣言値） | OS32＋データ32GiB | Prometheus・Alertmanager・Grafana・exporter（M01）。時系列は専用データディスク。常時 |
| dev-a / dev-b（400 / 401） | 各2 / 各6GiB（下限2GiB、2026-09-12の実測に同期） | 各40GiB（宣言値） | 既存の作業VM。利用者と調整して停止 |
| probe-01（900） | 2 / 2GiB（宣言値） | 32GiB | 既存の検証VM。未使用時は停止対象 |
| public-edge（必要時に新規cloud VM） | 1 / 1GiB | 16GiB | 外部公開Web。公開条件を確認してから追加 |
| DNS・復旧用Tailscale | 既存ラズパイ、K11枠外 | 現行確認 | K11停止時の管理経路を保持 |

上表は同時稼働を保証する合計ではありません。常用基盤（services-01、identity、cloud-01、storage-s3、cp、worker-01）だけでも計画値で22GiBです。monitor-01 2GiB・media-01 6GiB・game1 12〜16GiB・開発VM2台12GiBを加えると54〜58GiBとなり、現在の物理RAM（認識59.7GiB）とほぼ同程度です。全員のコード・設定作成を並列に進めつつ、実機の重い処理は[I01 容量測定・軽量化](../development/I01-resources.md)で測った余力と利用状況に合わせます。軽量化・停止を先に全員の着手条件にはしません。

<a id="measured-budget"></a>
### 実機の実測

**以下は測定時点の記録で、現在の空き容量ではありません。** 最新はポータルの「容量」で確認します。取得元は Proxmox API（読み取り専用トークン）、各VMのSSH、クラウド管理DB、`platform/terraform/cloud.yaml` です。

#### 2026-09-12（I01）

測定時刻: 2026-09-12 13:16 UTC。クラウドの上限上書き（`limit_overrides`）は無く、実効値は `cloud.yaml` の既定（1アカウント 8台・32vCPU・32GiB・ディスク1000GiB、クラウド全体のメモリ枠32GiB、ノードに4GiB残す、ディスク実使用率85%）です。

| 項目 | 実測 |
| --- | --- |
| CPU | Ryzen 9 8945HS、8コア/16スレッド。直近1日の平均使用率 7%、iowait 0% |
| Proxmoxが認識したRAM | **59.7GiB**（2026-09-10と同じ） |
| 稼働中VMの割当合計 | **35.1GiB**（game1 12 + identity 4 + services-01 4 + dev-a 6 + dev-b 6 + cloud-01 2 + storage-s3 1 + ボリューム保持VM 0.1） |
| ホストの実使用 / 空き | 34.3GiB / **25.4GiB**。swapは8GiB中ほぼ未使用（直近1日の最大0.45GiB） |
| `local-lvm` | **226.7GiB / 794.3GiB（29%）**。メタデータ 101MiB / 8.7GiB |
| rootfs（`local`・`cloud-images`） | 22.0GiB / 93.9GiB。うちISOが17.5GiB |
| SSD | CT1000E100SSD8 1TB。SMART health PASSED、Percentage Used 0%、書き込み768GB、電源投入101時間、温度41°C。Proxmox画面の「wearout 100」は残寿命100%の意味 |
| 負荷 | 直近1日でCPU some最大1.7%、I/O some最大3.9%、メモリ some最大0.4%。OOMなし |

VM別の割当・状態・実使用（測定時刻。ゲスト値は `free`、PVE RSSはホスト側の実使用でゲストのページキャッシュを含む）:

| VMID | 名前 | 状態 | vCPU / RAM | ゲストの実使用 | ディスク |
| --- | --- | --- | --- | --- | --- |
| 100 | game1 | 稼働 | 8 / 12GiB固定 | PVE RSS 12.1GiB | 256GiB（論理） |
| 110 | identity | 稼働 | 2 / 4GiB（下限1GiB） | 1.6GiB / 3.8GiB | 6.1 / 32GiB |
| 130 | storage-s3 | 稼働 | 2 / 1GiB（下限0.5GiB） | 0.25GiB / 0.94GiB | OS 1.0 / 16GiB、データ 0.01 / 32GiB |
| 140 | cloud-01 | 稼働 | 2 / 2GiB（下限0.5GiB） | 0.4GiB / 1.9GiB | 6.2 / 40GiB（軽量化後） |
| 150 | services-01 | 稼働 | 2 / 4GiB固定 | 1.6GiB / 3.8GiB | 3.5 / 48GiB（軽量化後） |
| 200 | k8s-cp-01 | 停止 | 2 / 3GiB固定 | — | 32GiB |
| 210 | k8s-worker-01 | 停止 | 4 / 8GiB固定 | — | OS32 + データ64GiB |
| 211 | k8s-worker-02 | 停止 | 4 / 8GiB固定 | — | OS32 + データ48GiB |
| 400 | dev-a | 稼働 | 2 / 6GiB（下限2GiB） | 0.5GiB / 4.3GiB | 22 / 40GiB |
| 401 | dev-b | 稼働 | 2 / 6GiB（下限2GiB） | 1.4GiB / 5.8GiB | 7.9 / 40GiB |
| 900 | probe-01 | 停止 | 2 / 2GiB（下限0.5GiB） | — | 32GiB |
| 5000 | win11pro（クラウド利用者VM） | 停止 | 2 / 4GiB（下限1GiB） | — | 64GiB |
| 5997 | shakecloud-volumes | 稼働 | 1 / 64MiB | — | 0 |

停止中VMも含めた全VMの割当合計は60.1GiBで、認識RAMの59.7GiBを超えます。**全台同時起動はできません**（実機の電源状態は[配備台帳](../operations/handover.md)）。

**この測定の後にmonitor-01（VMID 5002、2/2GiB、cloud VM）を作成したため、上の表と合計には含まれません。** 配備の結果は[M01](../development/M01-monitoring.md)、最新の電源・容量は[配備台帳](../operations/handover.md)とポータルの「容量」を正とします。

**軽量化（同日実施）**: ビルドキャッシュの削除と `apt` キャッシュの掃除でthin poolを15.1GiB回収しました。cloud-01 17.0→6.2GiB、services-01 5.7→3.5GiB、identity 6.1→3.8GiB。同じ処理は `tools/trim-vms.py` で再実行できます（既定は確認のみで、`--apply` を付けたときだけ削除。dev VMは `--include-dev` で明示したときだけ対象）。dev-aには未使用イメージ7.98GiBとビルドキャッシュ6.0GiBが残るため、利用者と調整します（2026-09-12時点で未削除）。journalはどのVMも121MiB以下で対象外です。

**作成・増枠の判断（`node_memory_reserve_mib` = 4GiB）**:

- media-01（6GiB）: Kubernetes停止中の空き25.4GiBでは作成できます。Kubernetes稼働時は空きが9.0GiBまで下がった記録（同日09:07）があり、その状態では作成を断られる可能性が高いため、**作成はKubernetes停止中に行います**（2026-09-12に作成済み）。
- game1の16GiB（+4GiB）: media-01作成後でもKubernetes停止中なら作成できます（空き14.6GiB）。ゲームとAIの同時負荷は[G03](../development/G03-game-ai-resources.md)で測ります。
- services-01の8GiB（+4GiB）: ゲストの実使用は1.6GiBで、緊急性はありません。
- k8s-worker-02: **起動しません**。起動する場合は開発VM・ゲームの停止と引き換えにします。
- 重い処理を止める順は開発VM → Ollama → バッチ、復帰は逆順です。dev VMsはバルーニングでホストRSSを割当（各6GiB）より小さく抑えています（測定時は2台で約5GiB。作業中のdev-bは増える）。

負荷を掛けた組合せの試験（ゲーム・AI取り込み・AWX同時実行）は未実施で、[G03](../development/G03-game-ai-resources.md)・[A02](../development/A02-ollama.md)・[I06](../development/I06-awx.md)と窓を調整して行います。

#### 2026-09-10（過去）

この日は `GET /v1/capacity` と Proxmox の API から取得しました。

| 項目 | 実測 |
| --- | --- |
| CPU | Ryzen 9 8945HS、8コア / 16スレッド |
| Proxmoxが認識したRAM | **59.7GiB**（64GB の公称からファーム・iGPU 予約を引いた値） |
| 稼働中VMの上限合計 | **40GiB**（game1 12 + dev-a 8 + dev-b 8 + identity 4 + services-01 4 + cloud-01 2 + probe-01 2） |
| そのときの実使用 | 35.1GiB。空き 23.8GiB |
| `local-lvm`（VMディスク） | 794GiB のうち使用 99GiB（13%） |
| `local` / `cloud-images` | 94GiB のうち使用 13GiB（14%） |

旧計画は開発VMを各2GiBとして計53GiB（ゲーム16GiB時57GiB）、論理ディスク計724GiBとしていました。その後、開発VMは各8GiBとなり、services-01・cloud-01・Kubernetesも加わりました。旧合計とこの日の40GiBを新規VM追加時の空きとして流用しません。現在の宣言・稼働状態・使用量は別々に取得します。

**メモリの配り方の方針を変更しました。**以前ここには「余白は約7GiB」と書き、クラウドの枠もそれに合わせて 8GiB にしていました。実測の 59.7GiB に対して稼働VMの上限合計が 40GiB、実使用は 35.1GiB です。**上限の合計を物理メモリ以下に収める方針では、16GiB のゲームVMをクラウドの管轄で作れません。**

そこで、**上限の合計が物理メモリを超えることを許し（バルーニングを前提とする）、実際の空きの検査でホストを守る**方針にしました。

- クラウド全体のメモリ枠（`cloud.yaml` の `memory_budget_mib`、既定 32GiB）は**方針の枠**で、物理の保証ではありません。
- **物理を見ているのは `node_memory_reserve_mib`（既定 4GiB）だけです。**作成のたびにノードの `available` を読み、その分を引いても 4GiB 残らなければ断ります。上限を無制限にしてもこの検査は残ります。
- したがって「上限の合計」と「実際の空き」は一致しません。ポータルの「容量」は**両方**を並べて出します。

**代償を承知しておく必要があります。**バルーニングで返ってくるのは、ゲストが実際に使っていないぶんだけです。ゲームVMのように実際に16GiB使う相手は返しません。全員が上限まで使えば、足りなくなるのは予約ぶんからで、**先に倒れるのはホストと基盤VM（認証・API・台帳）です**。上限を上げたぶんは、止める順番（開発VM → Ollama → バッチ）を実際に運用で守ることで払います。ゲーム・常用サービス・DBを載せるworkerは固定RAMから開始し、バルーニングによる回収を余剰として数えません。

旧ディスク724GiBは論理的な見積もりで、実パーティションや物理空き容量ではありません。新しい配分では実プール使用量・原本・索引・WAL・復元作業領域を測り直します。thin provisioningで物理容量は増えません。容量不足時は不要なコピーや保持期間を見直し、移行する範囲を調整します。カメラ録画はservices-01の既存ディスクへ無条件に追加しません。

Docker・ゲーム・開発の停止単位にはVMを使います。GPUはgame1へ割り当てたまま、同じVMの中でゲームとAIの負荷を調整します。

## 常用Kubernetes

- kubeadm + containerd + Ciliumは構築済み。現行のCilium Ingressとkube-proxy置換設定を維持する。
- クラスタ内HTTPの入口は現行のCilium Ingress、LoadBalancer IPはMetalLB、証明書はcert-managerで管理する。VM上のアプリは各VMのTLS入口を使う。
- Knative Serving・Kourierは構築済み。DB提供のCloudNativePGとともに、既存のOperatorを利用する。
- FluxでHelm/Kustomizeを反映し、SOPSでSecretを暗号化する。
- requests、必要なlimits、readiness/startup/liveness probe、NetworkPolicyを設定する。
- AWXはAnsibleの実行基盤として使うが、クラスタ自身の復旧は管理PCから実行できるようにする。
- 監視はmonitor-01（新規cloud VM）へPrometheus・Alertmanager・Grafana・exporterを配備済み（M01）。外部公開せず、保持期間と容量を抑える。既存ラズパイはDNSと復旧経路を担う。

control plane 1台は、その停止中に新規配置・再配置・設定変更ができなくなる設計です。既存Podは動き続ける場合がありますが、正常性はアプリと障害内容に依存します。VMが3台でも物理ホスト・SSDは1つです。今回のVM追加で物理障害への冗長性が増えるとは扱いません。[kubeadm HA](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/high-availability/)

Kubernetesへ残すのはAWX・DB提供・関数提供です。Homarr・Vaultwardenはservices-01のComposeへ移し、単に小さいWebアプリだからクラスタへ移すことはしません。既存サービスの移行と新機能の実装は別々に検証します。

## アプリの配置と維持する機能

| サービス／構成要素 | 計画上の配置先 | 永続化・担当計画 |
| --- | --- | --- |
| Nextcloud、Calendar、Tasks | media-01 | 配備済み（2026-09-12、`https://nextcloud.apextox.dpdns.org`）。DB・Redis・cronを含む一組の復元と旧環境からの移行はW03 |
| Kavita、Navidrome、MeTube | media-01 | Kavita・Navidromeは配備済み。MeTubeの切替はW06。原本は共有し、アプリ状態・固有DBは分離。W04–W06 |
| Homarr、MkDocs | services-01 | Homarrは新規スタックで配備済み（W01、`https://homarr.apextox.dpdns.org`）。MkDocsは現行のまま |
| Vaultwarden | services-01 | 配備済み（2026-09-12、`https://vault.apextox.dpdns.org`）。DB・添付・鍵を独立して復元。W02 |
| Open WebUI、pokemon-agent、ポケモンRDB・図鑑VDB | game1 | DB・WebUI・agentを一式移行。A01 |
| Ollama、汎用RAG、Discord Bot | game1 | 推論モデルと用途別データ・権限を分離。A02–A04 |
| OpenHome（製品未特定） | game1の同居候補 | 要件調査のみ。追加容量・稼働を確約しない。A05 |
| Wolf、Azahar×2、非公開ルーム | game1 | 利用者別セーブ・設定・ペアリング。G01–G03 |
| RomM | game1 | 独立Compose・状態管理は実装済み。game1実機確認と認証統合はW07 |
| AWXと専用DB | k8s-worker-01 | ローカルPVC、並列数・ジョブ整備。I06 |
| 利用者向けDB・関数 | 常用Kubernetes | CNPG・Knative。API所有の動的リソースとFlux所有物を分離。O02 |
| 自作クラウドAPI・管理DB | cloud-01 | 現行Composeを維持。利用者DBと分離。O01 |
| Authentikと専用DB | identity | 現行構成を維持。旧メディア認証の移行はアプリごとに確認 |
| Garage | storage-s3 | メタデータとオブジェクト。O03 |
| Home Assistant、SwitchBot Cloud、Eufy中継 | services-01 | 配備済み（2026-09-12）。HAはAuthentik OIDCと緊急用ローカルオーナーを併用。構成・履歴・鍵を独立保存。H01・H02・H04（H03 Echoは見送り） |
| Prometheus・Alertmanager・Grafana・exporter | monitor-01 | 配備済み（2026-09-13、M01）。時系列は専用データディスク。Homarr連携・低電池シャットダウンはM01の残作業 |
| CUPS・印刷API | services-01 | 配備済み（D08）。キュー `ts8430`。Nextcloud印刷アプリはmedia-01。ブラウザー操作は未確認 |
| セルフホストVPN | services-01 | 別ComposeでDB・設定・鍵を保存。N01 |
| 公開Caddy | public-edge（条件成立後） | 設定・証明書状態。N04 |
| AdGuard Home・復旧用Tailscale | 既存ラズパイ | 既存負荷と復旧経路を確認。N02 |
| Picard | media-01（利用者PCからも利用可） | **配備済み（2026-09-12、W06の一部）**。Web GUIコンテナ。MeTubeの取込（W06）とNextcloudのmusic原本をタグ付けし、Navidromeの表示へ反映。導線の資料はD05 |
| LocalSend、Tailcat | 端末アプリ＋media-01の受信機 | 専用VM不要。受信機はmedia-01（D06。実送受信は未確認）。Tailcatは資料のみD07 |

停止・更新単位と依存関係は[開発計画の一覧](../development/index.md)を参照してください。services-01のアプリ同士は別Composeと保存先を使い、VM再起動時のみ一緒に停止します。

<a id="pokemon-db"></a>
### ポケモンRDBの配置と移行単位

**配置先はgame1へ変更しました。DB・WebUI・agent・推論を同じVMに置き、game1停止中はポケモンAI一式も停止します。** 旧案の「ゲーム停止中もSQL検索を維持」「専用CNPGへ移行」「一時pokemon-ai-01を作成」は採用しません。[A01 ポケモンAI](../development/A01-pokemon-ai.md)が実装・移行の計画です。

参照元の `pokemon-ai-lab/compose.yaml` は本リポジトリにはありません。旧設計では同じPostgreSQLに `pokemon_rdb` と `openwebui` があり、Embeddingは `openwebui.rag.pokedex_documents` とされています。現行のソース・版・データ量を取得して確認し、未確認の内容を実機状態として扱いません。

- 両DB、ロール・読み取り権限、pgvector、WebUIの状態と鍵、agent設定を移行単位にする。汎用RAGのデータ・文書権限とは分離する。
- 既存PostgreSQL・拡張・Embeddingの版と次元を保持し、移行とモデル変更を同時に行わない。
- game1内でゲーム・モデル・AI状態の保存先を分け、GPU負荷試験は[G03](../development/G03-game-ai-resources.md)で調整する。AI用の4GiBという旧見積もりは実測保証ではなく、VM全体の12–16GiB内で再測定する。
- CNPG移行を前提とした別VM・別ディスクの予算は加算しない。データ・索引・WAL・モデル・復元領域を実測して必要な仮想ディスク容量を決める。

切替手順は、更新・取り込み停止 → 両DBとWebUI状態の整合バックアップ → 隔離した移行先へ復元 → ロール再設定・agent接続 → 全表件数と `fingerprint_data.py` の比較 → SQL・図鑑検索・WebUI/SSEの確認 → 接続先切替、です。元環境は停止して保持し、合格前にボリュームを消しません。切替後に新規チャット等の書き込みが入った場合は、その差分を保全してから切り戻します。

<a id="home-devices"></a>
### Home Assistant・SwitchBot・Eufy（Echoは見送り）

**Home Assistant Containerはservices-01へ配備済みです（2026-09-12）。** 入口は `https://ha.apextox.dpdns.org`（Caddy + Let's Encrypt、本体は `127.0.0.1:8123`）。HAコアはOIDC非対応のため、コミュニティ統合 **hass-oidc-auth v1.2.1**（`custom_components/auth_oidc` へdigest固定で配置）を使います。Authentik側の公開クライアント `home-assistant`（`redirect` `https://ha.apextox.dpdns.org/auth/oidc/callback`、`sub_mode user_uuid`、`users`／`admins` にバインド）は `stacks/identity/configure.py` が冪等作成し、HAは `configuration.yaml` の `auth_oidc` 管理ブロックでSSOします。**ローカルのオーナーアカウントは緊急用に残します。** WebSocket・CompanionアプリがあるためCaddyのForward Authは使いません。Kubernetesやgame1の再起動から家電を分離しますが、services-01・K11の再起動時には停止します。HAOSの追加アプリ管理は使わず、必要な周辺ソフトもComposeで管理します。[公式の導入方式](https://www.home-assistant.io/installation/)・[H01](../development/H01-home-assistant.md)

| 対象 | 接続方針 | 現状 |
| --- | --- | --- |
| SwitchBot | SwitchBot Cloud統合（Hub MiniがBLE機器を中継）。BluetoothローカルとUSBドングルは未使用 | 鍵・ドアセンサー・赤外線家電（エアコン・テレビ・照明など）のエンティティを確認済み |
| Echo Gen2 / Alexa | 既存端末のまま。Home Assistant Cloudも独自Skillも作らない | **見送り（2026-09-12決定）**。「HAからEchoへ音声通知」も実装しない。SwitchBot・Eufyは各社のAlexaスキルで操作できる |
| Anker Eufy（eufyCam S4 T8172・SmartTrack T87B0） | `eufy-security-ws` 3.1.0（独立Compose。HAのComposeネットワーク内の `eufy-security-ws:3000` だけに公開し、LANへは出さない）＋HA統合 `eufy_security` v8.2.4 | S4はHomeBaseなしの単体。ログイン・デバイス一覧・Pushは動作。**ライブ映像は不可**（S4は新しいWebRTC方式で旧P2Pクライアントから接続できない。後継SDKでのRTSPブリッジは検討中）。イベント取り込みは確認中。録画は既存のEufyアプリ／内蔵ストレージを維持 |

SwitchBotはCloud統合（Hub Mini経由）を採用し、資格情報はHAのconfig entryにだけ保存します。ローカルBluetoothへ切り替える場合だけUSBドングルのパススルーが必要です。[Bluetooth公式](https://www.home-assistant.io/integrations/switchbot/)、[Cloud公式](https://www.home-assistant.io/integrations/switchbot_cloud/)。AlexaのCloud連携と独自Skill方式は別機能で、VPNだけでAmazon側から到達できるわけではありません。HAの8123はルータから公開しません。[Alexa公式](https://www.home-assistant.io/integrations/alexa.smart_home/)

Eufyの録画・映像保存・映像AIは別の容量／CPU設計です。services-01の保存領域を録画庫として流用しません。HA側で扱う範囲はイベント・Push・静止画までとし、確認できたものだけを利用可能として案内します。ライブ映像は新しいWebRTC方式への対応（後継SDKによるRTSPブリッジ等）を確認できたら別作業として追加します。中継サービスを増やす場合は、互換性・認証・メモリを確認してから配分表へ追記します。

### LocalSendとIoTのネットワーク

LocalSendは端末間転送で、専用VMは不要です。**media-01に非公式の常設受信機（`stacks/media/localsend/`）を置き、送信ファイルをNextcloudの `inbox` へ着地させます。** 標準のTCP 53317をLANのSGで許可し、アプリの自動検出は同一LANでのみ確認します（実送受信は未確認、[D06](../development/D06-localsend.md)）。VLANやVPNをまたぐ自動検出は当然には成立しないため、まず同一LANで確認します。[LocalSend公式](https://github.com/localsend/localsend)

Home Assistantを載せるservices-01は、対象IoT機器へ到達できるLANのbridgeへ接続し、固定IP（`192.168.10.200`）で運用します。IoTをVLAN分離する場合は必要な通信とmDNS等の検出経路を設計してから移します。IoT機器からProxmox管理・DBへのアクセスは許可しません。HAの操作は家庭内LANとHA自身の認証（Authentik OIDCまたは緊急用ローカル）から行い、8123はルータへ公開しません。

LLMはQwen3 4B／8Bの量子化版、EmbeddingはBGE-M3を初期比較候補にします。まずコンテキスト4K、同時実行1で確認します。Qwen3 8B Q4_K_Mのファイルは約5.2GBですが、実行には追加メモリが必要です。[Qwen3](https://ollama.com/library/qwen3/tags)、[BGE-M3](https://huggingface.co/BAAI/bge-m3)

RAGはOpen WebUI + pgvectorから開始します。Nextcloudの文書権限がRAGへ自動継承されるとは扱わず、Discordへ返してよい文書・チャンネルを制限します。[Open WebUI RAG](https://docs.openwebui.com/features/chat-conversations/rag/)

## ストレージ

| 種類 | 今回の配置・確認 |
| --- | --- |
| OS・VMディスク | 現有SSDの実プール使用量を測定。仮想ディスクの追加・拡張は既存データを保全して行う |
| DB・SQLite・アプリ状態 | 各VMの専用保存先。Kubernetes内の状態はローカルPVC |
| 音楽・本・動画 | media-01の共有原本領域。複数VMから同じボリュームを同時に書かない |
| ROM | game1のライブラリ領域。ゲーム・AIの状態と分離する |
| S3 | storage-s3の専用データディスク |
| ゲームセーブ・AI状態 | game1内で利用者・用途ごとに分離 |
| バックアップ | 既存の外部保存先をO01–O03で確認。保存先未確認なら復元完了としない |

今回の計画にNAS・メモリ・物理ホスト等の購入提案は含めません。現有容量に収まらない取り込みは範囲や保持期間を調整します。S3と通常のファイル共有は互換ではなく、ファイルの保存先を一律S3へ変更しません。

ローカルPVCはlocal-path-provisioner等で開始できますが、データは特定workerに結び付きます。Podだけを別workerへ再配置してもそのデータは移動しません。PVCの削除ポリシー、worker再作成、復元を確認します。[local-path-provisioner](https://github.com/rancher/local-path-provisioner)

単一SSDの上でVM間にLonghornの複製を作っても、物理障害への冗長性は増えません。今回も導入対象にしません。NFSは未マウント時に空ディレクトリへ書かないよう起動確認を入れます。

<a id="バックアップと復旧"></a>
## バックアップと復旧

- VM: 既存の外部保存先と利用可能なバックアップ手段を確認する。新規ハードの購入を解決策とせず、保存先未確定はO03の前提条件に残す。
- PostgreSQL: アプリ整合性のあるバックアップとWAL、または用途に合ったDBダンプ。通常のファイルコピーだけで取得しない。
- Nextcloud: DB・設定・ファイルの整合性を揃える。
- SQLite・ゲームセーブ: 書き込みを止めるか、アプリ／DBの整合性を保つ方法を使う。
- Garage: メタデータとオブジェクトを含む復旧可能なバックアップ。格納先のS3自身を唯一のバックアップにしない。
- monitor-01: Prometheusの時系列とGrafanaの宣言・秘密値。時系列は復旧の必須条件にしない。
- etcd: スナップショットと復旧手順。Gitからの再構築ではSecret・PVCデータを別途戻す。
- Secret: SOPS復号鍵、API資格情報、認証基盤の鍵は管理PCと外部コピーへ保持する。

Home AssistantはContainerの構成・履歴・秘密値を整合性を保ってバックアップし、既存の外部保存先への復元と必要な復号情報を確認します。USB機器の割り当てはVM復元後に再確認します。

復旧順序は、ネットワーク／K11外Tailscale → Proxmox → Home Assistantと必要なストレージ／認証（services-01にはVPNを追加予定） → Kubernetes → DBとPVC → API・アプリです。管理APIやFlux自身が正常でないと復旧できない循環依存を作りません。隔離VM／namespaceで実際の復元を確認します。[PBS](https://www.proxmox.com/en/products/proxmox-backup-server/features)、[restic](https://restic.readthedocs.io/en/stable/)

## Gitと構成の所有者

当面は既存の `shake-cloud` リポジトリへ設計を集約します。コードが増えたら、基盤、クラウドAPI／CLI、Terraform Providerの3リポジトリへ分離できます。名前は未確定です。

| 管理対象 | 所有者 |
| --- | --- |
| Proxmox上の基盤VM | 管理者のTerraform |
| ゲストOS、kubeadm、Wolfの基盤設定 | Ansible |
| KubernetesのOperator・共通基盤・常用アプリ | Flux |
| API経由で作ったVM・関数・バケット・DB | 自作APIとそのTerraform Provider |
| 原本、DB、セーブ、APIキーの秘密値 | バックアップ／Secret管理。通常のGitには含めない |

**同じオブジェクトをFluxと自作API、または2つのTerraform stateで管理しません。** FluxはOperatorと共通基盤、自作APIは専用namespace内の動的オブジェクトを担当します。管理用DBや基盤VMを利用者向け削除APIの対象にしません。

IP、ドメイン、ストレージ名、PCIアドレスを環境設定へ分離し、イメージ・Provider・Chart・collectionを固定します。RenovateのPRで更新を確認します。NetBoxを台帳の正本にする場合はGitと二重手更新せず、復旧用エクスポートを保存します。[Renovate Compose](https://docs.renovatebot.com/modules/manager/docker-compose/)

## 並列開発と切替の依存

[開発計画](../development/index.md)のW/A/G/H/N/I/O/Dは作業の分類で、番号は実施順ではありません。コード・設定・模擬応答による検証は各担当が並列に進め、実機配備に必要なVM・容量・認証・バックアップだけを個別の切替条件にします。

同じstateの適用、共通DNS/TLS設定、VM再起動、GPU負荷試験は担当間で調整します。DBや原本の移行は整合バックアップと隔離復元に合格してから切り替えます。初回構築の経緯は[Proxmox導入後の記録](bring-up.md)に残しますが、その章番号を今後の全体工程として使いません。

<a id="document-publishing"></a>
## この構成案の更新・公開

Git上の設計文書は `docs/architecture/`、図の原稿は `diagrams/*.mmd`、表示用は同名SVGです。SVGは静的ファイルなので、サイト表示時にMermaid用CDNへの接続は不要です。図を変えた場合は原稿からSVGも更新し、両方をコミットします。

図の再生成は管理環境でPlaywrightとChromiumを用意し、次のスクリプトを使います。MermaidのバージョンとスクリプトのSHA-256はスクリプト内で固定します。初回取得にネット接続を使用します。

```bash
python3 -m pip install playwright==1.62.0
python3 -m playwright install chromium --only-shell
python3 tools/render-architecture-diagrams.py
```

Gitの文書を変更した後は `python3 -m mkdocs build --strict` で検証します。現行のservices-01サイトはGitの `docs/` を入力に `platform/ansible/docs-site.yml` で配備します。旧メディアハブの `LIBRARY_ROOT/docs` と `hub/manage.py build` は別環境の手順です。今回の計画・README追加ではサイトへの配備を実行しません。

Gitの `docs/` を正本とし、Nextcloudで構成案を編集する旧ハブの運用は持ち込みません。旧ハブで編集した資料を取り込む場合だけ、Gitの `docs/architecture/` へ移してレビューしてから同じ版をサイトへ反映し、自動双方向同期は設けません。生成された `stacks/hub/site/` を編集したりGitへ追加したりしません。既存の他の手順書を一括上書きしません。

公開前にステージした差分と `tools/check-publication.py` を確認します。GitHub公開用の資料には、実際のAPIキー、個人用IP台帳、DB接続文字列、セーブ、Secretを入れません。
