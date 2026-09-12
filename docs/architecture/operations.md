# 配備・Git管理・ストレージ・復旧

[構成案トップ](index.md)へ戻る。記載する容量は初期設計値で、実測保証値ではありません。

更新日: 2026-09-12。状態: **設計資料。実機のVM・配置は[配備台帳](../operations/handover.md)を正とする。** 下の表は初期設計で、VMID候補と役割の一部は実機と異なります（100 は game1 が使用、worker-01/02 の役割は構築時に変わっています）。

<a id="resource-budget"></a>
## VM/LXCと初期リソース配分

以下はK11の64GB構成に対する**配置先と初期上限の設計**です。全VMを初日に作る必要はありません。VMIDは未使用であることを確認して採番する候補です。

| VMID候補 / 配置 | 形式 | vCPU | RAM | 初期ディスク（GiB） | 内容・起動方針 |
| --- | --- | --- | --- | --- | --- |
| Proxmox | ホスト | — | 6GiB枠 | OS 64 | ホストとキャッシュの予算。実消費は監視 |
| 未定 / public-edge | VM | 1 | 1GiB | 16 | 公開Caddy。公開Web統合時に作成（VMID 100 は game1 が使用中） |
| 105 / vpn-01 | VM | 2 | 2GiB | 16 | セルフホストVPN。NetBird第一検証候補、製品選定中。常時 |
| 110 / identity | VM + Compose | 2 | 4GiB | 32 | Authentikと専用DB。常時 |
| 120 / home-assistant | HAOS VM | 2 | 4GiB | 32 | 家電連携・自動化・履歴。常時 |
| 130 / storage-s3 | VM | 2 | 1GiB | OS 16 + データ32 | Garage。利用開始後は常時 |
| 200 / k8s-cp-01 | VM | 2 | 3GiB | 32 | control plane、etcd。常時 |
| 210 / k8s-worker-01 | VM | 4 | 8GiB | OS 32 + データ64 | AWX 24.6.1・CloudNativePG・Knative/Kourier。常時 |
| 211 / k8s-worker-02 | VM | 4 | 8GiB | OS 32 + データ48 | 予備。今は停止のまま（必要時に join） |
| 100 / game1 | VM + Docker | 8 | 12GiB（最大16） | OS 48 + データ96 | Wolf、Azahar×2、必要時Ollama、OpenHome候補。`cloud` プールでクラウド管理下 |
| 400・401 / dev-a・dev-b | VM×2 | 各2 | 各8GiB（実機。当初計画は各2GiB） | 各32 | 個別インフラ開発。利用時 |
| DNS・VPN・監視 | 既存ラズパイ | — | K11枠外 | 既存容量を確認 | K11停止時も管理経路を維持 |
| **K11合計** | | **31 vCPU** | **53GiB（ゲーム16時57）** | **計724GiB（ホストOS込み）** | iGPU予約と未配分領域は別 |

<a id="measured-budget"></a>
### 実機の実測（2026-09-10）

**上の表は当初計画で、実機はこうなっています。**（`GET /v1/capacity` と Proxmox の API から取得。ポータルの「容量」で常に最新が見られます。）

| 項目 | 実測 |
| --- | --- |
| CPU | Ryzen 9 8945HS、8コア / 16スレッド |
| Proxmoxが認識したRAM | **59.7GiB**（64GB の公称からファーム・iGPU 予約を引いた値） |
| 稼働中VMの上限合計 | **40GiB**（game1 12 + dev-a 8 + dev-b 8 + identity 4 + services-01 4 + cloud-01 2 + probe-01 2） |
| そのときの実使用 | 35.1GiB。空き 23.8GiB |
| `local-lvm`（VMディスク） | 794GiB のうち使用 99GiB（13%） |
| `local` / `cloud-images` | 94GiB のうち使用 13GiB（14%） |

当初計画との差は、**開発VMが各2GiB→各8GiB**、そこへ計画に無かった `services-01`（4GiB）と `cloud-01`（2GiB）が加わったことです。表の合計値は当初計画のまま残してあります（何をどう見積もったかの記録なので、実測で上書きしません）。

セルフホストVPNの2GiBとHome Assistantの4GiBを追加し、workerを各10→8GiBへ調整しました。workerの16GiBにはDB・Operator・Knative制御部も含みます。従来と同じ全サービス同時負荷を期待せず、AWX実行・関数・一括取り込みは直列から始めます。vCPU合計は物理16スレッドを超えるため、CPUも専有予約ではありません。

**メモリの配り方の方針を変更しました。**以前ここには「余白は約7GiB」と書き、クラウドの枠もそれに合わせて 8GiB にしていました。実測の 59.7GiB に対して稼働VMの上限合計が 40GiB、実使用は 35.1GiB です。**上限の合計を物理メモリ以下に収める方針では、16GiB のゲームVMをクラウドの管轄で作れません。**

そこで、**上限の合計が物理メモリを超えることを許し（バルーニングを前提とする）、実際の空きの検査でホストを守る**方針にしました。

- クラウド全体のメモリ枠（`cloud.yaml` の `memory_budget_mib`、既定 32GiB）は**方針の枠**で、物理の保証ではありません。
- **物理を見ているのは `node_memory_reserve_mib`（既定 4GiB）だけです。**作成のたびにノードの `available` を読み、その分を引いても 4GiB 残らなければ断ります。上限を無制限にしてもこの検査は残ります。
- したがって「上限の合計」と「実際の空き」は一致しません。ポータルの「容量」は**両方**を並べて出します。

**代償を承知しておく必要があります。**バルーニングで返ってくるのは、ゲストが実際に使っていないぶんだけです。ゲームVMのように実際に16GiB使う相手は返しません。全員が上限まで使えば、足りなくなるのは予約ぶんからで、**先に倒れるのはホストと基盤VM（認証・API・台帳）です**。上限を上げたぶんは、止める順番（開発VM → Ollama → バッチ）を実際に運用で守ることで払います。ゲーム・HAOS・DBを載せるworkerは固定RAMから開始し、バルーニングによる回収を余剰として数えません。

ディスク724GiBは論理的な計画値であり、既存パーティションをこの表に合わせて作り直す指示ではありません。1TBは約931GiBなので、差分約207GiBからISO・テンプレート・メタデータ・スナップショットを賄い、実プール使用率80%程度で増設・整理します。メディア原本もworkerデータ枠へ含め、現行データが収まらなければ移行前に別ディスクを確保します。thin provisioningでも物理容量は増えません。カメラ録画領域と別機器バックアップはこの724GiBに含みません。

LXCはDNSなど権限要求の少ない小型サービスをK11へ置く場合に非特権で使用します。Docker基盤、ゲーム、開発用にはVMを優先します。GPUは通常のPCIパススルーで1つのVMへ渡し、別のAI VMと同時共有できる前提にしません。

## 常用Kubernetes

- kubeadm + containerd、Ciliumを採用候補とする。Cilium Gatewayの前提とkube-proxy設定を一緒に固定する。
- 常用HTTPアプリの入口はCilium Gateway API、LoadBalancer IPはMetalLB、証明書はcert-managerで管理する。MetalLBとCiliumのIP払い出し機能を重複させない。
- Knative Servingには別途Kourierを入れ、内部入口から転送する。
- FluxでHelm/Kustomizeを反映し、SOPSでSecretを暗号化する。
- requests、必要なlimits、readiness/startup/liveness probe、NetworkPolicyを設定する。
- AWXはAnsibleの実行基盤として使うが、クラスタ自身の復旧は管理PCから実行できるようにする。
- 監視は既存ラズパイと連携する。Prometheus/Grafanaを追加する場合、保持期間と容量を抑える。

control plane 1台は、その停止中に新規配置・再配置・設定変更ができなくなる設計です。既存Podは動き続ける場合がありますが、正常性はアプリと障害内容に依存します。VMが3台でも物理ホスト・SSDは1つです。物理ホスト追加時にcontrol planeとストレージも分散させます。[kubeadm HA](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/high-availability/)

SQLite等を使うアプリを単に複数レプリカへ変更しません。NextcloudやOpen WebUIも、複数稼働時のDB・セッション・共有ファイル要件を確認します。

## アプリの配置と維持する機能

workerの記載は初期の配置方針です。実際にはnamespace・PVC・node affinity等へ反映します。ローカルPVCを持つPodは元のworkerの復旧またはデータ復元が必要です。

| サービス／構成要素 | 配置先 | 永続化・依存／状態 |
| --- | --- | --- |
| Nextcloud、Calendar、Tasks | worker-01 / media | ファイル・設定・DB、Redis、cronを一組で移行 |
| Kavita、Navidrome、MeTube、RomM | worker-01 / media | 原本・アプリDB・設定。RomM等の固有DB要件を保持し、全DBをPostgreSQLへ強制統一しない |
| Homarr、MkDocs | worker-01 / portal | Homarr設定・鍵、文書原稿とビルド設定。**Kubernetes ができるまでMkDocsのサイトは services-01 に仮置き**（`platform/ansible/docs-site.yml`） |
| Vaultwarden | worker-01 / vault | DB・添付・鍵。独立復元を検証して移行 |
| Open WebUI、pokemon-agent | worker-01 / pokemon-ai | WebUI状態・鍵・接続設定。agentの管理者権限なし |
| ポケモンRDB、図鑑VDB | worker-01 / pokemon-aiのCloudNativePG | 専用PostgreSQLクラスタ1インスタンスから。次節のDB・ロールを保持 |
| 汎用RAG・Discord Bot | worker-01 / ai | ポケモン用途と文書権限を分離。Bot Secretと対象チャンネルを管理 |
| Ollama | game-01 | モデル専用ディレクトリ。ゲーム時は推論停止・モデル解放 |
| OpenHome（製品未特定） | game-01同居候補 | URL・Linux対応・GPU／音声要件確認まで未導入。必要RAMはゲーム枠内で再見積もり |
| AWX・NetBoxと各専用DB | worker-02 / automation・inventory | ジョブ並列数を制限。DB・暗号鍵・メディアを保存 |
| 自作クラウドAPI・ジョブ・管理DB | worker-02 / cloud-system | 利用者作成DBと管理DBを分離 |
| 利用者向けDBアプライアンス | worker-02 / 動的専用namespace | CloudNativePG。ポケモンDBを削除APIの対象にしない |
| Knative Serving・Kourier・関数 | worker-02中心 | 関数の同時実行数と合計requestsを制限 |
| Cilium・MetalLB・cert-manager・Flux・CNPG Operator | Kubernetes共通基盤 | chartが要求するnode配置を尊重。予算はworker枠に含む |
| Authentik・専用DB | identity | クラスタ外。設定・鍵・DBを保存 |
| Garage | storage-s3 | メタデータ・オブジェクトを保存 |
| Home Assistant・家電連携 | home-assistant | HAOS内。構成・自動化・履歴とバックアップ復号情報を保存 |
| Wolf・Azahar×2・非公開ルーム | game-01 | ユーザー別セーブ・設定・ペアリング |
| MusicBrainz Picard | 利用者PC。必要ならgame-01のGUI | 自動タグ照合。作業コピー→確認／保存→共有musicへ反映。無人ジョブは未配備 |
| LocalSend | PC・スマホ。必要ならゲームVMのデスクトップ | 常設サーバー不要。受信先フォルダを端末側で指定 |
| 公開Caddy | public-edge | 設定・証明書状態。内部アプリへの許可経路のみ |
| セルフホストVPN | vpn-01 | NetBird／Headscale等から1製品を選定。DB・設定・鍵・端末登録を保存。詳細は[VPN比較](vpn.md) |
| Tailcat | 管理PC／dev-a | 一時的なファイル・ポート接続。常設VM不要。接続情報は非公開 |
| AdGuard Home・Tailscale・既存監視 | ラズパイ | DNS設定・VPN復旧情報・監視設定。容量と現状負荷を確認 |

<a id="pokemon-db"></a>
### ポケモンRDBの配置と移行単位

**最終配置はworker-01上の専用PostgreSQL（CloudNativePG）です。ゲームVMには置きません。** ゲームVMやOllama停止中にもSQL検索・既存のSakura経由の回答を維持する設計です。

現行の `pokemon-ai-lab/compose.yaml` とREADMEでは、同じPostgreSQLに `pokemon_rdb` と `openwebui` があり、図鑑本文・Embeddingは `openwebui.rag.pokedex_documents` にあります。ポケモンのダンプだけでは全体を復元できません。

- `pokemon_rdb`、`openwebui` の両DB、必要なロール・権限・pgvector拡張を移す。`pokemon_reader` と `rag_reader` の読み取り専用権限を維持する。
- 初期候補はPostgreSQL 17互換のpgvector対応CNPGイメージ。現行実稼働版・拡張版を確認して固定する。既存ComposeのイメージをCNPGでそのまま利用できるとは扱わない。
- Open WebUIのデータボリューム、`WEBUI_SECRET_KEY`、agent設定・APIキー、migration／provision処理も移行対象。秘密値はGit本文へ保存しない。
- 保存済みEmbeddingのモデル・次元は現行設定を保持する。下記BGE-M3候補へ移行と同時に切り替えない。既存データは自動再取り込みされない。
- 初期予算はDB 2GiB、Open WebUI 1.5GiB、agent 0.5GiBの計4GiBをworker-01の8GiB内で見込む。残りで基盤とメディアを賄えるか実測し、重い走査を止める。ディスクはworker-01の64GiB内からDB用32GiBを仮置きし、実データ＋索引＋WAL＋復元作業領域を測って確定する。
- CNPG未構築の間は現行環境を維持する。先にK11へ移す必要がある場合だけ、一時 `pokemon-ai-01` VM（4vCPU／4GiB、OS32＋データ32GiB、容量実測必須）へComposeを復元する。この間はworker-02を作成しない／停止して枠を使い、最終配分へ追加で積まない。

切替手順は、更新・取り込み停止 → 両DBとWebUI状態の整合バックアップ → 隔離した移行先へ復元 → ロール再設定・agent接続 → 全表件数と `fingerprint_data.py` の比較 → SQL・図鑑検索・WebUI/SSEの確認 → 接続先切替、です。元環境は停止して保持し、合格前にボリュームを消しません。切替後に新規チャット等の書き込みが入った場合は、その差分を保全してから切り戻します。

<a id="home-devices"></a>
### Home Assistant・SwitchBot・Echo・Eufy

HAOS専用VM（2vCPU／4GiB／32GiB）を選び、Kubernetes更新やゲームVM再起動で家電自動化が止まらない構成にします。ただしK11自体の再起動中は停止します。初期はHAOSの標準履歴DBを使い、PostgreSQLクラスタへの依存を増やしません。[HAOS VM導入](https://www.home-assistant.io/installation/alternative/)

| 対象 | 接続方針 | 導入時の確認・合格条件 |
| --- | --- | --- |
| SwitchBot | 対応機器はBluetoothローカル接続。USB BluetoothをHAOSへ渡すか、対応Bluetooth proxyを検討。Cloud連携は型番・Hubに応じて選択 | 機器とHubの型番を記録。1台の操作・状態更新・再起動後再接続を確認。K11内蔵Bluetoothが使える前提にはしない |
| Echo Gen2 / Alexa | Echoは既存端末。HAの機器をAlexaから操作する入口として扱う。Home Assistant Cloudを簡易な候補とし、料金・アカウント条件を選定時に確認 | 「Echoから家電操作」と「HAからEchoへ音声通知」は別機能。後者は個別検証。Echo Gen2を汎用Bluetooth proxyやThread border routerと見なさない |
| Anker EufyCam S4 | 当面はEufyアプリ／既存録画先を維持し、HAへのイベント・静止画・ライブ映像を個別検証 | 正確な型番・HomeBase・FW・アプリ内NAS/RTSP項目を確認。S4の直接対応は未確認。NAS対応機種の一般資料をS4対応保証にしない |

SwitchBotはローカルBluetoothとCloudで要件が異なります。[Bluetooth公式](https://www.home-assistant.io/integrations/switchbot/)、[Cloud公式](https://www.home-assistant.io/integrations/switchbot_cloud/)。AlexaのCloud連携と独自Skill方式も異なり、VPNだけでAmazon側から到達できるわけではありません。接続方式の決定前にHAの8123をルータから公開しません。[Alexa公式](https://www.home-assistant.io/integrations/alexa.smart_home/)

Eufyの映像保存・常時録画・映像AIは別の容量／CPU設計です。HAOSの32GiBを録画庫にはしません。RTSPが実機で利用可能な場合に、映像表示とイベント連携を別々に試します。追加の非公式連携や中継サービスが必要なら、その互換性・認証・メモリを確認してから配分表へ追記します。[Eufy NAS/RTSP一般手順](https://service.eufy.com/article-description/Device-NAS-RTSP-Configuration-Guide)

### LocalSendとIoTのネットワーク

LocalSendは端末間転送で、専用VMは不要です。同じLANで送受信し、標準のTCP/UDP 53317を端末FWで必要範囲に許可します。VLANやVPNをまたぐ自動検出は当然には成立しないため、まず同一LANで確認します。[LocalSend公式](https://github.com/localsend/localsend)

HAOSも最初は対象IoT機器へ到達できるLANのbridgeへ接続し、DHCP予約等でIPを安定させます。IoTをVLAN分離する場合は必要な通信とmDNS等の検出経路を設計してから移します。IoT機器からProxmox管理・DBへのアクセスは許可しません。HAの操作はLAN／VPNとHA自身の認証から開始します。

LLMはQwen3 4B／8Bの量子化版、EmbeddingはBGE-M3を初期比較候補にします。まずコンテキスト4K、同時実行1で確認します。Qwen3 8B Q4_K_Mのファイルは約5.2GBですが、実行には追加メモリが必要です。[Qwen3](https://ollama.com/library/qwen3/tags)、[BGE-M3](https://huggingface.co/BAAI/bge-m3)

RAGはOpen WebUI + pgvectorから開始します。Nextcloudの文書権限がRAGへ自動継承されるとは扱わず、Discordへ返してよい文書・チャンネルを制限します。[Open WebUI RAG](https://docs.openwebui.com/features/chat-conversations/rag/)

## ストレージ

| 種類 | 当初 | 将来 |
| --- | --- | --- |
| OS・VMディスク | 内蔵SSD | 容量追加・移設 |
| DB・SQLite・アプリ状態 | ローカルSSDのPVC／仮想ディスク | 整合性・ロック要件を確認して拡張 |
| 音楽・本・動画・ROM | 分離したデータ領域 | NASのNFS共有へ |
| S3 | Garage VMの専用データディスク | 別筐体ノードやディスクを検討 |
| ゲームセーブ・設定 | ユーザー別永続ディレクトリ | 別機器へバックアップ |
| バックアップ | 別ディスク／既存機器 | 重要データの遠隔コピーも追加 |

NASは保存先を提供する機器・システム、NFSは共有プロトコルです。将来はNASからNFSを提供し、ファイル用PVCにNFS CSIを使えます。S3とNFSは用途が違い、任意のアプリのファイル領域をそのままS3へ置換できるわけではありません。[NFS CSI](https://github.com/kubernetes-csi/csi-driver-nfs)

ローカルPVCはlocal-path-provisioner等で開始できますが、データは特定workerに結び付きます。Podだけを別workerへ再配置してもそのデータは移動しません。PVCの削除ポリシー、worker再作成、復元を確認します。[local-path-provisioner](https://github.com/rancher/local-path-provisioner)

単一SSDの上でVM間にLonghornの複製を作っても、物理障害への冗長性は増えません。当初は導入せず、複数物理ホストへ拡張するときに再検討します。NFSは未マウント時に空ディレクトリへ書かないよう起動確認を入れます。

## バックアップと復旧

- VM/LXC: Proxmox Backup Serverを候補とする。別機器がなければ当面の別ディスクへのバックアップから開始する。
- PostgreSQL: アプリ整合性のあるバックアップとWAL、または用途に合ったDBダンプ。通常のファイルコピーだけで取得しない。
- Nextcloud: DB・設定・ファイルの整合性を揃える。
- SQLite・ゲームセーブ: 書き込みを止めるか、アプリ／DBの整合性を保つ方法を使う。
- Garage: メタデータとオブジェクトを含む復旧可能なバックアップ。格納先のS3自身を唯一のバックアップにしない。
- etcd: スナップショットと復旧手順。Gitからの再構築ではSecret・PVCデータを別途戻す。
- Secret: SOPS復号鍵、API資格情報、認証基盤の鍵は管理PCと外部コピーへ保持する。

Home AssistantはHAOSのバックアップを別機器へ出し、必要な復号情報も外部へ保管します。USB機器の割り当てはVM復元後に再確認します。

復旧順序は、ネットワーク／K11外Tailscale → Proxmox → Home Assistantと必要なストレージ／認証 → vpn-01 → Kubernetes → DBとPVC → API・アプリです。管理APIやFlux自身が正常でないと復旧できない循環依存を作りません。隔離VM／namespaceで実際の復元を確認します。[PBS](https://www.proxmox.com/en/products/proxmox-backup-server/features)、[restic](https://restic.readthedocs.io/en/stable/)

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

## 移行順序

到着したK11で最初に進める作業と完了条件は、[Proxmox導入後の手順](bring-up.md)を参照してください。

1. 現行データと構成をバックアップし、ネットワーク・VPN・復旧経路を確認する。
2. Proxmoxと小型VMを準備し、780Mパススルーと2人ゲームの実測を先に行う。
3. kubeadmクラスタ、ストレージ、Flux、監視を構築し、軽い常用アプリから移行する。
4. GarageとCloudNativePGを構築し、実クライアントの接続と復元を確認する。
5. 自作API／ProviderのVM機能を実装し、次にS3・DB・Knativeへ拡張する。
6. Nextcloud・Vaultwardenなどの重要サービスを、データ復元・スマホ接続確認後に切り替える。
7. 既存公開Webは公開入口と内部隔離の確認後に統合する。

<a id="document-publishing"></a>
## この構成案の更新・公開

Git上の設計文書は `docs/architecture/`、図の原稿は `diagrams/*.mmd`、表示用は同名SVGです。SVGは静的ファイルなので、サイト表示時にMermaid用CDNへの接続は不要です。図を変えた場合は原稿からSVGも更新し、両方をコミットします。

図の再生成は管理環境でPlaywrightとChromiumを用意し、次のスクリプトを使います。MermaidのバージョンとスクリプトのSHA-256はスクリプト内で固定します。初回取得にネット接続を使用します。

```bash
python3 -m pip install playwright==1.62.0
python3 -m playwright install chromium --only-shell
python3 tools/render-architecture-diagrams.py
```

Gitの文書を変更した後は `python3 -m mkdocs build --strict` で検証します。既存サイトは配備先の `LIBRARY_ROOT/docs` を入力にするため、今回の `architecture/` をそこへ反映してから `hub/manage.py build` を実行します。入力先は環境によって異なるので、`.env` の保存先を確認し、公開ログへ秘密値を出さないようにします。

Nextcloudで構成案を編集した場合は、その変更をGitの `docs/architecture/` に取り込んでレビューしてから、同じ版をサイトへ反映します。自動双方向同期は設けません。生成された `stacks/hub/site/` を編集したりGitへ追加したりしません。既存の他の手順書を一括上書きしません。

公開前にステージした差分と `tools/check-publication.py` を確認します。GitHub公開用の資料には、実際のAPIキー、個人用IP台帳、DB接続文字列、セーブ、Secretを入れません。
