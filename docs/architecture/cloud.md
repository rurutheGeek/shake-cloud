# 最小クラウドとTerraform Provider

[構成案トップ](index.md)へ戻る。状態: 設計案。以下のAPI・Terraformリソースは未実装の提案です。

## クラウドの提供機能

| 機能 | 利用者へ提供するもの | 実装先 |
| --- | --- | --- |
| VM | イメージ、CPU、RAM、ディスク、ネットワーク、起動状態 | Proxmox API |
| サーバレス | コンテナイメージ、環境変数／Secret参照、HTTP URL、最小／最大レプリカ | Knative Serving |
| S3 | バケット、S3アクセスキー、バケットへの読み書き権限 | Garage管理API・S3 API |
| DBアプライアンス | PostgreSQLインスタンス、容量、接続先、DB資格情報、バックアップ | CloudNativePG |

自作するのはこれらを一つのAPIで扱う部分です。仮想化、スケジューラ、オブジェクト保存、PostgreSQLの監視・起動制御は既存基盤へ任せます。ユーザー、プロジェクト、組織、課金を初期APIへ追加しません。

## サーバレス: Knative Serving + Kourier

初期仕様は「HTTPリクエストを受けるOCIコンテナを配備し、未使用時はゼロまで縮退する」です。Knative Servingはリビジョン、HTTPルーティング、オートスケールを提供します。[Knative autoscaling](https://knative.dev/docs/serving/autoscaling/)

- ソースコードは開発VMまたはGitHub Actionsでイメージ化し、GHCRなどへ置く。クラウドAPIにソースのビルドまで持たせない。
- イメージのdigestを指定して再現性を確保する。private registryにはimagePullSecretなどの認証設定を用意する。
- `min_scale=0`、`max_scale=1` を初期既定とし、必要なサービスだけ増やす。
- 最大同時処理数、CPU／メモリ、タイムアウトを設定する。重い実行をゲームと競合させない。
- スケールゼロからの初回はコールドスタートがある。起動遅延を避けるサービスだけ最小1にする。
- 関数の一時ファイルは消える前提とし、永続データはS3やDBに保存する。
- 定期バッチはKubernetes Job/CronJobで始める。イベント配信が必要になった時点でKnative Eventingやキューを検討する。

KourierはKnative向けのネットワーク実装です。既存の内部HTTPS入口から、正しいHost情報を保ってKourierへ転送します。通常アプリ用Gatewayとは転送先・IPの担当を分けます。[ネットワークプラグイン](https://knative.dev/docs/install/)

Knative ServingだけではAWS Lambda API、ZIPアップロード、AWSの実行ロールは提供しません。Discord Gatewayへ常時接続するBotなどは、通常のDeploymentとして常駐させます。

## S3: Garageを第一候補にする

Garageは、バケット・キーの管理APIがあり、自作クラウドへ接続しやすい候補です。管理APIのトークンにはスコープと期限を設定できます。[Garage管理API](https://garagehq.deuxfleurs.fr/documentation/reference-manual/admin-api/)

初期配置はKubernetes外の小型VMとし、専用のデータ用仮想ディスクを渡します。メタデータ・オブジェクト・設定・鍵をバックアップ対象にします。Kubernetes復旧時に、バックアップ格納先まで同じクラスタの起動待ちになる依存を減らせます。

当初は単一ノード・replication factor 1なので、**データの冗長性はありません**。Garage公式も単一ノード手順を冗長性のない構成として説明しています。ホームラボでこの制約を受け入れる場合も、唯一の保存先や唯一のバックアップにはしません。[Garage Quick Start](https://garagehq.deuxfleurs.fr/documentation/quick-start/)

GarageはS3の全機能を実装しているわけではありません。公式互換表では署名v4、presigned URLなどに対応する一方、バケットバージョニングは未対応です。AWS IAM互換の任意ポリシーをそのまま適用できる前提にもせず、初期APIはバケット単位の許可に絞ります。[S3互換表](https://garagehq.deuxfleurs.fr/documentation/reference-manual/s3-compatibility/)

バージョニングなどが必須ならSeaweedFSも比較し、採用バージョンと実際のクライアントで確認してから選定を変更します。SeaweedFSには単一ノード向けの `weed mini` があり、S3エンドポイントを提供できます。[SeaweedFS公式](https://github.com/seaweedfs/seaweedfs)

S3 APIにはブラウザ用Forward Authを挟まず、S3署名で認証します。管理APIはクラウドAPIからだけ到達できるようにします。クラウドを作成するTerraform stateは、まず管理PCなどクラウド停止中も使える場所へ保持し、別途暗号化バックアップします。

## DBアプライアンス: CloudNativePG

初期エンジンはPostgreSQLだけに絞ります。1つのアプライアンスをCloudNativePGの `Cluster` に対応させ、最初はプライマリ1台で提供します。「アプライアンス」は利用者から見た提供単位であり、必ずしも専用VMを意味しません。

| 提供項目 | 初期案 |
| --- | --- |
| エンジン | PostgreSQL、採用メジャー版を固定 |
| サイズ | 小型のCPU／RAMプロファイルから選択 |
| ストレージ | ローカルSSDのPVC。自動フェイルオーバーを保証しない |
| 接続 | Kubernetes内用Serviceと、開発VMから届くVPN内のTCP接続先を区別 |
| 認証 | アプリ用DBロール。管理者パスワードを利用者へ配らない |
| 拡張 | pgvectorなど、検証済みの拡張だけを許可 |
| 保護 | 削除保護、バックアップ、復元方法をリソース仕様へ含める |

同じPostgreSQLインスタンス内に論理DB・ロールを作る軽量運用も可能です。これは専用インスタンスとは分離単位が異なるため、APIでは明示します。最初は専用インスタンスのライフサイクルを実装し、追加の軽量DB作成は必要になってから拡張します。

CloudNativePGは `Database` CRDで論理DBや拡張の管理ができます。ただしpgvectorの宣言だけではバイナリは導入されないため、使用するイメージ／拡張配布方法とPostgreSQL版を揃えます。[CloudNativePGのDB管理](https://cloudnative-pg.io/docs/1.30/declarative_database_management/)

DBバックアップはS3へ保存できますが、同じK11内のGarageだけでは筐体・SSD故障へのバックアップになりません。外部コピーを確保します。クラウドAPI自身の管理DBは通常の利用者向けリソース一覧から除き、自己削除できないようにします。

## APIキーだけの認証モデル

利用者アカウントを作らず、用途別のキーを発行します。初回管理キーの作成・失効は管理CLIまたはサーバー上の操作で始められます。

```yaml
# 設計例。キーの秘密値ではなくポリシーだけを記述する。
name: terraform-dev
scopes:
  - vm:read
  - vm:write
  - function:read
  - function:write
  - bucket:read
  - db:read
expires_at: "2026-12-31T00:00:00Z"
```

- スコープはAPI側で判定する。Providerのチェックだけに依存しない。
- 書き込みと削除は別スコープにし、初期既定で削除を許可しない。
- 高エントロピーの秘密値を発行時に一度だけ表示し、検証用ハッシュ・キーID・期限・失効状態を保存する。
- キーIDごとに操作履歴を残す。必要になればリソースID／ラベル単位の制限を追加する。
- APIキーはHTTPSで送信し、Gitやログへ保存しない。
- クラウド管理キー、S3 access key/secret、DBパスワード、関数の呼出し資格情報は別にする。

関数を作成できる権限と、そのHTTP URLを呼び出せる権限も別です。初期はVPN内に限定し、必要な関数には用途別Bearer tokenなどを追加します。公開関数は明示的に公開入口へ登録します。

## 自作APIとProviderの境界

[![最小クラウドの制御と実行経路](diagrams/cloud.svg)](diagrams/cloud.svg)

図を開くと拡大できます。

[編集用Mermaid](diagrams/cloud.mmd)

自作APIは小さな単一サービスから開始します。GoのHTTP API、OpenAPI、永続化されたジョブ／バックエンドIDを用意し、当初は専用メッセージブローカを増やしません。必要なワーカー処理は同じコードベースで実行できます。

| Terraformリソース案 | バックエンド | 主な入出力 |
| --- | --- | --- |
| `homelab_instance` | Proxmox VM | image、CPU、RAM、disk、network → ID、IP、状態 |
| `homelab_function` | Knative Service | image digest、env、limits、scale → URL、revision |
| `homelab_bucket` | Garage bucket | name → bucket名、S3 endpoint |
| `homelab_database` | CloudNativePG Cluster | version、size、storage → endpoint、資格情報参照 |

S3キーやDB資格情報の作成は関連APIとして扱います。Terraformへ秘密値を返す場合はstateに保存され得ます。`sensitive` 指定は暗号化ではありません。可能ならSecret参照を返し、秘密値を取得する経路を分離します。

```hcl
# 未実装のProviderに対する利用イメージ
provider "homelab" {
  endpoint = "https://api.cloud.example.net"
  # APIキーは環境変数などから取得する設計
}

resource "homelab_instance" "dev" {
  name    = "dev"
  image   = "debian-stable"
  flavor  = "small"
  network = "private"
}

resource "homelab_function" "hello" {
  name      = "hello"
  image     = var.function_image_digest
  min_scale = 0
  max_scale = 1
}

resource "homelab_bucket" "files" {
  name = "app-files"
}

resource "homelab_database" "app" {
  name                = "app"
  engine              = "postgresql"
  flavor              = "small"
  storage_gib         = 10
  deletion_protection = true
}
```

ProviderはCreate/Read/Update/Delete/importを備え、非同期作成が完了するまで待機します。APIは再試行しても重複作成しない識別子を扱い、作成途中の失敗から再照会・回収できるようにします。Readでバックエンドの実状態を取得し、権限エラーを「削除済み」と誤認しないようにします。[Terraform Plugin Framework](https://developer.hashicorp.com/terraform/plugin/framework/resources/read)

APIキーの利用量課金は不要ですが、ホストの空きRAM、ディスク上限、関数の最大並列数は保護します。物理容量不足の場合は作成を断ります。DBメジャー変更・ディスク縮小などは通常Updateで自動実行せず、対応範囲を明示します。

## 実装前に確保済みの枠

APIは未実装ですが、後から載せたときにVMIDの再採番や既存VMの移動が起きないよう、Proxmox側の枠だけ先に作ってあります。詳細は[IaCの所有境界](iac.md)を参照してください。

| 予約したもの | 値 | 現状 |
| --- | --- | --- |
| Proxmoxプール | `cloud` | 空のまま作成済み |
| VMID範囲 | 5000–5999 | 未使用 |
| ロール | `CloudApiOperator` | 作成済み。**未割り当て** |
| 実行アカウント | `cloudapi@pve` | 未作成 |
| NetBoxのPrefix | 動的採番用を静的用と分離 | 未作成 |

管理者Terraformが使う `terraform@pve` は `/pool/cloud` に権限を持ちません。逆に将来の `cloudapi@pve` は `/pool/platform` に権限を持ちません。利用者向けの削除APIが基盤VMへ届かないことを、運用規約ではなくACLで保証します。この枠の存在は、APIやProviderが動くことを意味しません。

## 最初の実装順

1. VMのCreate/Read/Delete/importと、APIキー・処理状態・重複防止。
2. Garageのバケット作成と用途別S3キー。実クライアントでPUT/GET/削除を確認。
3. CloudNativePGによるDB作成、接続、バックアップと隔離環境への復元。
4. Knativeへのコンテナ配備、HTTP応答、ゼロ縮退からの再起動。
5. Update、削除保護、タイムアウト、再試行、権限不足の受入テスト。

VM、通常の関数HTTP呼出し、S3オブジェクト転送、SQL通信は利用先へ直接接続します。自作クラウドAPIにデータ転送を集約せず、APIはリソース管理を担当します。
