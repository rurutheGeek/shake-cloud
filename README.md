# shake-cloud

Proxmox VE 上のホームラボを、コードで構築・運用するリポジトリです。認証（Authentik）、クラウドAPI（VM・S3・DB・関数）、台帳（NetBox）、メディア、家電、監視を用途別のVMに分け、Terraform・Ansible・Flux・Docker Composeで配備します。

**ドキュメントの入口**

手順書は `docs/` にあり、services-01 の <https://docs.apextox.dpdns.org> へ配備されます。目的から入ってください。

| 目的 | 入口 |
| --- | --- |
| サービスを使う | [利用ガイド](docs/services/index.md)・[全サービスの使い方](docs/services/usage.md) |
| 開発に参加する | [開発参加ガイド](docs/onboarding.md)・[開発計画](docs/development/index.md) |
| 環境を立ち上げる・運用する | [運用手順の入口](docs/operations/index.md)・[初回セットアップの順番](docs/operations/bootstrap.md) |
| 仕組みを知る | [ホームラボの全体像](docs/architecture/overview.md)・[設計](docs/architecture/index.md) |
| URL・用語を引く | [接続先一覧](docs/reference/urls.md)・[用語集](docs/reference/glossary.md) |
| 手順書を書き足す | [ドキュメントの書き方](docs/contributing-docs.md) |

[トップページ](docs/index.md)と[ドキュメント地図](docs/map.md)が全体の案内板です。実機の状態・進捗・TODOの正本は[配備台帳](docs/operations/handover.md)です。

## いまの構成

Proxmox VE ホスト `apextox` 上のVMに役割を分けています。各VMは独立したDocker Composeプロジェクト群です。

| VM | 役割 |
| --- | --- |
| identity | Authentik（共通ログイン。招待・復旧・パスキー） |
| cloud-01 | クラウドAPI・ポータル・管理DB（PostgreSQL） |
| services-01 | NetBox、ドキュメントサイト、Homarr、Vaultwarden、Home Assistant、CUPS、eufy-security-ws、print-api |
| media-01 | Nextcloud、Kavita、Navidrome、FreshRSS、MeTube、LocalSend受信機（クラウド管理下） |
| storage-s3 | Garage（S3互換オブジェクトストア） |
| monitor-01 | Prometheus、Alertmanager、Grafana、exporter（クラウド管理下） |
| k8s-cp-01 / k8s-worker-* | Kubernetes（AWX・CloudNativePG・Knative） |
| dev-a / dev-b | 開発VM |
| game1 | ゲームサーバ（クラウド管理下） |

サービスは `*.apextox.dpdns.org`（家庭内LAN専用。Let's Encrypt証明書をDNS-01で取得）で開きます。**インターネットには公開していません。** URLとアドレスの正本は `platform/terraform/dns.yaml` と[接続先一覧](docs/reference/urls.md)、停止・再開を含む実機の状態は[配備台帳](docs/operations/handover.md)です。

## 開発方針

このリポジトリの目的は、複数のセルフホストサービスを一つの入口から使い、別のサーバーへ移しても原本・設定・運用手順を引き継げる環境を作ることです。以下を今後の変更でも維持してください。

### 設計上の決定

- **可搬性**：書籍・音楽の原本は通常のファイルとして保持し、Nextcloudには外部ストレージとして登録します。Kavita・Navidromeには必要な原本だけを読み取り専用で渡します。サービスを変更しても原本を取り出すための専用エクスポートが不要な構成にします。
- **広く採用された形式を選ぶ**：ベンダーロックインを避けるのは、名前の付け方の問題ではなく**インターフェースの選び方**の問題です。複数の実装が存在し、多くのサービスが採用している形式・プロトコルを選びます。例：stateの置き場はS3互換APIなので、Cloudflare R2・Garage・MinIO・SeaweedFSのどれでも同じコードが動きます。特定の事業者にしか無いAPIへ依存するのは、それが本質的に必要なときだけにし、依存する範囲を1つのモジュールへ閉じ込めます。
- **手作業の最小化**：**コードで管理できるものはすべてコードにします。** GUIやシェルでの一度きりの操作を手順書に書いて済ませません。バケット、プール、ロール、ユーザー、トークン、VM、IPの採番はすべて宣言から作ります。残る手作業は「それ自体が最初の資格情報を生む操作」だけで、[残っている手作業](docs/operations/bootstrap.md)に理由付きで列挙し、増やしません。手順書は手作業の置き場ではなく、コードの実行順と判断根拠を書く場所です。
- **IaC（Infrastructure as Code）**：配備対象はNetBox、ホストへの導入はAnsible、サービス構成はDocker Compose、アプリ設定はAPI・occを使うPythonスクリプトで管理します。継続して必要な設定をGUIだけで変更せず、設定例・スクリプト・手順へ反映します。利用者の本棚・予定・お気に入りなどの日常データはアプリのDBに保持します。
- **再実行と再現性**：初期化では既存の秘密値・アカウント・データを保護します。コードで管理する設定は再配備で反映します。イメージは各 `compose.lock.yaml` のdigestで固定し、更新は明示的に行います。冪等性は全設定について保証済みではないため、変更箇所の再実行確認も必要です。
- **認証と権限の分離**：Authentikを共通認証基盤にし、対応アプリはOIDC、Navidrome・MeTubeはForward Authで接続します。SSOは各サービスの閲覧権限や既存データの自動統合を意味しません。VaultwardenにはSSO後も保管庫の暗号化用マスターパスワードが必要です。
- **秘密値と状態の分離**：Gitにはコード・設定例・Markdown・ロックファイルを置きます。実際の認証情報、Cookie、CA秘密鍵、ホスト台帳、原本、DB、ログは非公開領域へ分離します。Gitだけでは環境のデータ復元はできません。
- **利用の入口と日本語化**：サービスの入口はHomarr（services-01）で、タイルの正本は `stacks/homarr/apps.json` です。ドキュメントの原稿はGitの `docs/` が正本で、`platform/ansible/docs-site.yml` がservices-01へ配備します。生成済みサイトを直接編集しません。日本語化は各アプリの対応範囲で設定し、ブラウザー・利用者設定に依存する部分は手順で補います。
- **派生ファイルの管理**：BCSTM原本を残して再生用MP3を生成するなど、原本と派生物を分けて管理します。変換・タグ編集のコードは `stacks/music-tools/` にあります。

### コードの担当範囲

リポジトリは基盤（`platform/`）、サービス（`stacks/`）、クラウド（`cloud/`）、ツール（`tools/`）に分かれています。サービスは `stacks/<name>/` の独立Composeとしてホストごとに配備します（例: `stacks/home-assistant/` → services-01、`stacks/media/nextcloud/` → media-01）。Ansibleの `source_dir` が対応点なので、リポジトリ側を再編しても配備先の構成は変わりません。

| 場所 | 変更する内容 |
| --- | --- |
| `platform/terraform/` | Proxmoxのプール・ロール・基盤VMとNetBox台帳（`10-platform`・`05-seed`）、サービスVMの宣言（`services/<name>/`） |
| `platform/ansible/`、`ansible.cfg` | Docker導入、NetBox／クラウドのインベントリ、配備順序・ホスト変数、ゲストOSのロール |
| `platform/flux/` | Fluxが反映するクラスタ構成（`main` を監視）。AWX・CNPG・Knative などを配る |
| `platform/awx/` | AWX移行用のEE・Playbook例（AWX本体は `platform/flux/apps/` で配備済み） |
| `cloud/` | 自作クラウドAPI・CLI・Terraform Provider・読み取り専用MCPサーバ・共通クライアント（APIの正本は `cloud/openapi/`） |
| `stacks/identity/` | Authentik（招待・復旧・パスキー、`platform/ansible/identity.yml`）とポータル用OIDC |
| `stacks/netbox/` | NetBox本体、配備先の初期登録、認証設定 |
| `stacks/docs/` | ドキュメントサイトを配るnginx（services-01、`platform/ansible/docs-site.yml`） |
| `stacks/tls-proxy/` | 各ホストのHTTPS入口（CaddyとCloudflare DNSモジュール）。受ける名前は `platform/terraform/dns.yaml` |
| `stacks/media/` | media-01のNextcloud・Kavita・Navidrome・FreshRSS（共通RSSタイムライン）・LocalSend |
| `stacks/music-tools/` | MeTube・タグAPI・BCSTM変換・同期（media-01） |
| `stacks/homarr/`・`stacks/vaultwarden/`・`stacks/librespeed/`・`stacks/home-assistant/`・`stacks/eufy-security-ws/`・`stacks/print-api/`・`stacks/monitoring/` | services-01・monitor-01の新しい基盤のサービス（ホストごとの独立Compose） |
| `stacks/game/`・`stacks/romm/`・`stacks/pokemon-ai/`・`stacks/rag-bot/` | game1へ載せるゲーム・AIの開発コード（実装・移行は進行中） |
| `docs/`、`mkdocs.yml` | 日本語の利用・運用手順とサイト構成 |
| `tools/` | 公開前チェック、Terraform／Kubernetesの実行補助 |
| `tests/`、`.github/workflows/validate.yml` | 回帰テスト、公開対象チェック、ドキュメント検証 |

生成された `.env` だけを直して完了にせず、生成元の設定例・スクリプトへ変更を戻してください。全アプリの全設定をコード化済みではありません。新しく管理対象にする設定は、既存値を保持するかコードで上書きするかを明示します。

### 引き継いだら行うこと

1. [配備台帳](docs/operations/handover.md)・[接続先一覧](docs/reference/urls.md)・[設定と拡張](CONFIGURATION.md)を読み、Git差分と稼働中のコンテナを確認します。既存ホストで初期化・イメージ更新を無条件に実行しないでください。
2. 非公開の `.env`・秘密値・各サービスの状態領域と、原本の実際の保存先を確認します。新規ホストではNetBoxを先に構築し、対象を登録してAnsibleインベントリの `--graph` と配備の `--list-hosts` を確認します。
3. 基盤VMは `platform/terraform/10-platform` と `05-seed`、サービスVMは `platform/terraform/services/<name>/`（クラウドAPIのTerraform Provider）で作ります。中身の配備は、基盤がNetBoxの動的インベントリ、クラウドVMが `platform/ansible/inventory.cloud.py` を使います。対象ホストは `--limit` で絞ります。
4. 変更は設定の正本と対応する日本語手順へ反映し、下記の検証を実行します。実機へ反映する場合は対象サービスの起動・認証・目的の操作を確認し、再配備による秘密値やデータの保持も確認します。
5. バックアップは各ユニットの `manage.py backup` と、cloud-01の管理DBの定期バックアップ（`cloud-backup.timer`）です。別ホストへのコピーは未実装のため、重要な変更の前には対象範囲を別途バックアップします。

### 検証

リポジトリのルートで、CIと同じ検査を流します。Pythonの検査には mkdocs・yamllint などを入れた `.venv` を使います。

```bash
python3 -m unittest discover -s tests
terraform fmt -check -recursive platform/terraform
.venv/bin/yamllint -c .yamllint .
.venv/bin/mkdocs build --strict
python3 tools/check-publication.py
gofmt -l cloud
```

クラウドAPIのテストは次のとおりです。DBを使うテストは `SHAKECLOUD_TEST_DATABASE_URL` を渡したときだけ走ります。

```bash
cd cloud/api && go vet ./... && go test ./...
```

読み取り専用MCPサーバのテストはDBを使いません。

```bash
cd cloud/mcp && go vet ./... && go test ./...
```

Ansibleを変更した場合は `platform/ansible/requirements.txt` と `platform/ansible/requirements.yml` の依存も導入し、対象Playbookの `--syntax-check` と対象一覧を確認します。公開チェックは既知の秘密値・禁止パスの検出を補助するもので、ステージした差分の目視確認も必要です。GitHubへのpushとサーバー配備は別操作です。

### 現状と未完了事項

- クラウドは VM・S3・database・function の4機能を API・Provider・CLI・ポータルまで実装・実機確認済みです。Kubernetes は kubeadm + Cilium + Flux で構築し、AWX・CloudNativePG・Knative を配備しています（[クラウド開発の引き継ぎとTODO](docs/operations/handover.md)）。アクセスキーの読み取り専用スコープと、それを前提にした読み取り専用MCPサーバ（`cloud/mcp`、22ツール）を実装しました。**MCPのクライアント登録と実機確認はこれから**です（[MCPサーバ](docs/operations/mcp.md)）。
- メディア系は media-01 へ配備済みで、`https://nextcloud.apextox.dpdns.org` ほか `*.apextox.dpdns.org`（Let's Encrypt）と identity の OIDC／Forward Auth を使います。**既存環境からのメディアデータ移行と、ブラウザでのログイン実測は未完です**（[配備台帳](docs/operations/handover.md)）。
- Home Assistant Container は services-01 へ配備済みです。SwitchBot Cloud（Hub Mini）とEufy（`eufy-security-ws`）を連携していますが、**Eufyのライブ映像は新しいWebRTC方式のため当面不可**、スマートスピーカー連携は見送りです（[Home Assistantと家電](docs/services/home-assistant.md)・[H04](docs/development/H04-eufy.md)）。
- identity は外部SMTPリレーで招待・復旧メールを送信済みです（[メール設定](docs/operations/smtp.md)）。MeTube・音楽変換・タグ編集は media-01 へ配備済みです（W06）。**同期タイマーの切替と、共有Cookieを使う実ダウンロードは未確認です。**
- AWX 24.6.1 は構築済みです。ジョブテンプレート・プロジェクトの整備はこれからです（[AWXの使い方](docs/operations/awx.md)）。
- VPN（宅外アクセス）は未構築です（[VPN比較・Tailscale併用](docs/architecture/vpn.md)）。管理DBの外部バックアップも未着手です。
- 実際のゲーム由来BCSTMの網羅的互換性は未検証です。バックアップからの復元は drill を継続します。

## データの分離

media-01 では、データディスク `/srv/media-stack` の下にアプリの状態と原本を分けて置きます。

| 対象 | ホスト側（media-01） | コンテナ内 |
| --- | --- | --- |
| 書籍原本 | `/srv/media-stack/library/books` | Nextcloud: `/library/books`、Kavita: `/books:ro` |
| 音楽原本 | `/srv/media-stack/library/music` | Nextcloud: `/library/music`、Navidrome: `/music:ro` |
| 手順書・受け渡し | `/srv/media-stack/library/docs`・`inbox` | Nextcloud: `/docs`・`/library/inbox` |
| Nextcloudアプリ・設定・データ | `/srv/media-stack/storage/nextcloud/{html,config,data}` | `/var/www/html` ほか |
| Nextcloud専用PostgreSQL | `/srv/media-stack/storage/postgres` | `/var/lib/postgresql/data` |
| Kavita状態 | `/srv/media-stack/storage/kavita` | `/kavita/config` |
| Navidrome状態 | `/srv/media-stack/storage/navidrome` | `/data` |
| Vaultwarden DB・添付・鍵 | services-01 の `/srv/services/vaultwarden/data` | `/data` |
| HTTPS証明書・状態 | 各ホストの `/srv/tls-proxy/storage/data` | `/data`、`/config` |

`stacks/media/nextcloud/` の Redis は Nextcloud だけが接続する内部ネットワークで利用し、DB・Redisのポートはホストに公開しません。Vaultwardenの保管庫をNextcloudやlibraryへ渡しません。

Nextcloudの権限はKavita・Navidromeへ継承されません。原本ライブラリには各サービスでも公開してよいものを置き、サービスごとにユーザーと権限を設定してください。Nextcloudの外部ストレージは初回作成時に指定管理者だけへ公開し、再実行では既存の公開範囲を保持します。

## VMと配備

基盤VM（identity・cloud-01・services-01・storage-s3・Kubernetesノード・開発VM）は `10-platform` と `05-seed` が作り、NetBoxを動的インベントリにしてAnsibleで中身を配備します。services-01 は静的インベントリ `platform/ansible/seed.ini` を使うPlaybook（`homarr.yml`・`vaultwarden.yml`・`home-assistant.yml`・`cups.yml`・`docs-site.yml` など）で更新します。monitor-01 は `platform/ansible/monitor.ini`、Garage は NetBox インベントリから配備します。

サービスVMはクラウドAPIのTerraform Providerで作ります（`platform/terraform/services/<name>/`、サービスごとに1 state）。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'
tools/tf services/media plan
tools/tf services/media apply
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/inventory.cloud.py platform/ansible/media.yml
```

`media.yml` は Nextcloud → Kavita → LocalSend → Navidrome → FreshRSS → music-tools → 確認 → HTTPS の順に流します。手順と境界の正本は[サービスの置き場所とクラウドVMでの作り方](docs/operations/services.md)、VMの説明は `platform/terraform/services/media/README.md` です。**クラウドインベントリとNetBoxインベントリは併用しません**（`media` 群が和集合になります）。

## バックアップ

各ユニットの `manage.py backup` が、サービスを停止して状態と配備ファイルを tar で取得します（Nextcloud・Kavita・Navidrome・music-tools・Vaultwarden・Home Assistant・NetBox）。

```bash
ssh debian@192.168.10.101 'cd /opt/media-stack/media/kavita && sudo python3 manage.py backup --destination /srv/backups/kavita'
```

cloud-01 の管理DBは `cloud-backup.timer` が毎日 `/var/backups/cloud-api` へ取得します（`--keep 14`）。**別ホストへの転送は未実装です。** 原本（`library`）は状態のバックアップに含まれないため、別途バックアップしてください。復元は稼働中の領域へ上書きせず、新しい空のディレクトリへ行います。

## 書籍の追加

PDFは `/srv/media-stack/library/books/作品名/作品名.pdf` のように作品別フォルダへ置きます（books直下には置かないでください）。Nextcloudの `books` から作品フォルダを作ってアップロードできます。KavitaはBooksライブラリのフォルダ監視（Folder Watching）が有効で、変更を検知して取り込みます。反映されないときはKavitaのライブラリでScanを実行します。初期管理者とBooksライブラリの作成は `stacks/media/kavita/bootstrap.py` が行います。

設定範囲と拡張時の制約は[CONFIGURATION.md](CONFIGURATION.md)を参照してください。利用者は[全サービスの使い方](docs/services/usage.md)から始めてください。運用の管理作業は[運用手順の入口](docs/operations/index.md)から参照できます。

## GitHubへ置くもの

コード、Ansible、設定例、Markdown、イメージdigestのロックファイルを管理します。`.env`、秘密値、Cookie、実データ、状態、CA、実ホスト台帳、実行ログは `.gitignore` で除外します。公開前に `git diff --cached --stat` と `git diff --cached` で対象を確認してください。

`docs/` がドキュメントの正本です。書き方・検証・公開の決まりは[ドキュメントの書き方](docs/contributing-docs.md)にあります。ページを足したら `python3 tools/docs-map.py` で[ドキュメント地図](docs/map.md)を更新してください（CIが差分を検査します）。GitHubへのpushは配備とは別の操作です。

## 参照

- [Nextcloud Local external storage](https://docs.nextcloud.com/server/stable/admin_manual/configuration_files/external_storage/local.html)
- [Nextcloud Docker](https://github.com/nextcloud/docker)
- [Kavita Docker](https://wiki.kavitareader.com/installation/docker/github/)
- [Navidrome Docker](https://www.navidrome.org/docs/installation/docker/)
- [Vaultwarden Compose](https://github.com/dani-garcia/vaultwarden/wiki/Using-Docker-Compose)
- [NetBox inventory plugin](https://docs.ansible.com/projects/ansible/latest/collections/netbox/netbox/nb_inventory_inventory.html)
- [Garage](https://garagehq.deuxfleurs.fr/documentation/)
