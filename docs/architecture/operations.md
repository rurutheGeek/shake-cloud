# 配備・Git管理・ストレージ・復旧

[構成案トップ](index.md)へ戻る。記載する容量は初期設計値で、実測保証値ではありません。

<a id="resource-budget"></a>
## VM/LXCと初期リソース配分

| 配置 | 形式 | vCPU | RAM目安 | 用途 |
| --- | --- | --- | --- | --- |
| Proxmox | ホスト | — | 6GiB枠 | ホスト、キャッシュ等 |
| public-edge | VM | 1 | 1GiB | 公開用Caddy |
| identity | VM + Compose | 2 | 4GiB | Authentikと専用DB |
| storage-s3 | 小型VM | 1〜2 | 1GiBから | Garage。負荷・メタデータ量で再評価 |
| k8s-cp-01 | VM | 2 | 3GiB | control plane、etcd |
| k8s-worker-01 | VM | 4 | 10GiB | 常用アプリ・API・DB・Knative |
| k8s-worker-02 | VM | 4 | 10GiB | 常用アプリ・AWX・NetBox等 |
| game-01 | VM + Docker | 8 | 12〜16GiB | Wolf、Azahar×2、必要時Ollama |
| dev-a / dev-b | VM×2 | 各2 | 各2GiB | 個別のインフラ開発 |
| DNS・VPN・監視 | 既存ラズパイ | — | K11の枠外 | モデルと現状負荷を確認 |
| **K11合計** | | | **51〜55GiB** | iGPU固定予約・追加消費・動的VMの余裕は別 |

workerの20GiBにはKnativeの制御コンポーネントやCloudNativePG、API用管理DBも含める想定です。全サービスの高負荷同時実行を保証しません。新規DBアプライアンスや関数を無制限に追加できる枠ではありません。

例えばiGPU固定予約が4GiBなら残りは概算5〜9GiBですが、実際の利用可能RAM・ハイパーバイザ消費を確認して動的VMの上限を決めます。16GiB固定予約はこの配分では過大です。ゲーム停止時に検証VMへ枠を回す運用が可能です。

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

| 分類 | 方針 |
| --- | --- |
| Nextcloud、Calendar、Tasks | Kubernetesへ段階的移行。Redis・cron・DB整合性を含める |
| Kavita、Navidrome、MeTube、RomM | Kubernetesへ。原本は取り出せる普通のファイルで保持 |
| Homarr、MkDocs | ハブと文書を維持。MkDocsの入力と生成物を区別 |
| Vaultwarden | Kubernetes候補。認証基盤と別に復旧できるデータ・鍵を保存 |
| Open WebUI、Discord Bot | Kubernetes。Botは実装に応じて常駐Deployment |
| Ollama | GPU用VM。ゲームと負荷を分ける |
| PostgreSQL／pgvector | CloudNativePG。アプリ用と管理用の権限を分離 |
| NetBox | 台帳として維持。クラウドAPIの依存必須にはしない |
| LocalSend | 端末へ導入。常設サーバー不要 |

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

復旧順序は、ネットワーク／VPN → Proxmox → 必要なストレージ／認証 → Kubernetes → DBとPVC → API・アプリです。管理APIやFlux自身が正常でないと復旧できない循環依存を作りません。隔離VM／namespaceで実際の復元を確認します。[PBS](https://www.proxmox.com/en/products/proxmox-backup-server/features)、[restic](https://restic.readthedocs.io/en/stable/)

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
python3 scripts/render-architecture-diagrams.py
```

Gitの文書を変更した後は `python3 -m mkdocs build --strict` で検証します。既存サイトは配備先の `LIBRARY_ROOT/docs` を入力にするため、今回の `architecture/` をそこへ反映してから `hub/manage.py build` を実行します。入力先は環境によって異なるので、`.env` の保存先を確認し、公開ログへ秘密値を出さないようにします。

Nextcloudで構成案を編集した場合は、その変更をGitの `docs/architecture/` に取り込んでレビューしてから、同じ版をサイトへ反映します。自動双方向同期は設けません。生成された `hub/site/` を編集したりGitへ追加したりしません。既存の他の手順書を一括上書きしません。

公開前にステージした差分と `scripts/check-publication.py` を確認します。GitHub公開用の資料には、実際のAPIキー、個人用IP台帳、DB接続文字列、セーブ、Secretを入れません。
