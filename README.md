# Nextcloud × Kavita × Navidrome × Vaultwarden

将来の構成は[ホームラボ／最小プライベートクラウド構成案](docs/architecture/index.md)にまとめています。VM・サーバレス・S3・DB、2人用ゲーム、VPNと公開Web、SSO、Git管理を整理した設計資料です。[ローカルサイトで読む](http://localhost:8090/architecture/)。

NetBoxで配備先を管理し、AnsibleからDocker Composeを配備する構成です。
Homarrを入口に、Authentik SSO・日本語Markdown手順書・MeTubeを組み合わせています。[接続と配備手順](docs/operations/hub.md)、[SSO](docs/services/sso.md)、[音楽の取り込み](docs/services/music.md)を参照してください。
**AWX本体の構築は今回保留**。将来はkubeadmのKubernetes上に構築し、同じPlaybook・NetBoxインベントリを使います。AWX移行用のEE・登録Playbook例だけを `platform/awx/` に置いています。

## 開発方針・引き継ぎ

このリポジトリの目的は、複数のセルフホストサービスを一つの入口から使い、別のサーバーへ移しても原本・設定・運用手順を引き継げる環境を作ることです。以下を今後の変更でも維持してください。

### 設計上の決定

- **可搬性**：書籍・音楽の原本は通常のファイルとして保持し、Nextcloudには外部ストレージとして登録します。Kavita・Navidromeには必要な原本だけを読み取り専用で渡します。サービスを変更しても原本を取り出すための専用エクスポートが不要な構成にします。
- **IaC（Infrastructure as Code）**：配備対象はNetBox、ホストへの導入はAnsible、サービス構成はDocker Compose、アプリ設定はAPI・occを使うPythonスクリプトで管理します。継続して必要な設定をGUIだけで変更せず、設定例・スクリプト・手順へ反映します。利用者の本棚・予定・お気に入りなどの日常データはアプリのDBに保持します。
- **再実行と再現性**：初期化では既存の秘密値・アカウント・データを保護します。コードで管理する設定は再配備で反映します。イメージは各 `compose.lock.yaml` のdigestで固定し、更新は明示的に行います。冪等性は全設定について保証済みではないため、変更箇所の再実行確認も必要です。
- **認証と権限の分離**：Authentikを共通認証基盤にし、対応アプリはOIDC、MeTube・Navidromeは認証プロキシで接続します。SSOは各サービスの閲覧権限や既存データの自動統合を意味しません。既存のローカル管理者を残し、移行は別工程にします。VaultwardenにはSSO後も保管庫の暗号化用マスターパスワードが必要です。
- **秘密値と状態の分離**：Gitにはコード・設定例・Markdown・ロックファイルを置きます。実際の認証情報、Cookie、CA秘密鍵、ホスト台帳、原本、DB、ログは非公開領域へ分離します。Gitだけでは環境のデータ復元はできません。
- **利用の入口と日本語化**：リンクの正本は `stacks/hub/apps.json`、手順書の初期テンプレートとサイト構成は `docs/`・`mkdocs.yml` です。配備後の手順書原本は `${LIBRARY_ROOT}/docs` とし、Nextcloudの「docs」から編集します。生成済みサイトを直接編集しません。日本語化は各アプリの対応範囲で設定し、ブラウザー・利用者設定に依存する部分は手順で補います。
- **派生ファイルの管理**：BCSTM原本を残して再生用MP3を生成します。原本削除は確認を挟んで管理対象の派生ファイルへ反映し、一時退避を経て削除します。既存の無関係なMP3を巻き込まないことを優先します。MeTubeは共有Cookie方式で、一般利用者はURL入力だけで使います。Cookieの更新は運用作業です。

### コードの担当範囲

リポジトリは基盤（`platform/`）、サービス（`stacks/`）、リポジトリ用ツール（`tools/`）に分かれています。**`stacks/` の直下が配備先 `/opt/media-stack` の構成にそのまま対応します。** Ansibleの `source_dir` だけがこの対応点なので、リポジトリ側を再編しても配備先の構成は変わりません。

| 場所 | 変更する内容 |
| --- | --- |
| `platform/terraform/` | Proxmoxのプール・ロール・VMと、NetBox台帳の宣言 |
| `platform/ansible/`、`ansible.cfg` | Docker導入、NetBox動的インベントリ、配備順序・ホスト変数、ゲストOSのロール |
| `platform/kubernetes/` | Fluxが反映するクラスタ構成。未構築 |
| `platform/awx/` | 将来のAWX移行用の例。AWX本体は未構築 |
| `stacks/compose.yaml`、`stacks/scripts/` | 基本サービス、初期化、スキャン、バックアップ |
| `stacks/netbox/` | NetBox本体、配備先の初期登録、認証設定 |
| `stacks/hub/` | Homarr、Authentik、リンク一覧、SSO利用者の宣言的管理、ドキュメント配信 |
| `stacks/sso/` | Caddy、OIDC・認証プロキシ、ローカルTLS、アプリへの信頼設定 |
| `stacks/music-tools/` | MeTube、BCSTM変換・削除同期、タグ編集、定期反映 |
| `docs/`、`mkdocs.yml` | 日本語の利用・運用手順とサイト構成 |
| `tools/` | 公開前チェック、構成図の再生成 |
| `tests/`、`.github/workflows/validate.yml` | 回帰テスト、公開対象チェック、ドキュメント検証 |

生成された `.env` や `compose.sso.yaml` だけを直して完了にせず、生成元の設定例・スクリプトへ変更を戻してください。全アプリの全設定をコード化済みではありません。新しく管理対象にする設定は、既存値を保持するかコードで上書きするかを明示します。

### 引き継いだら行うこと

1. [ハブ運用](docs/operations/hub.md)、[SSO](docs/services/sso.md)、[音楽](docs/services/music.md)、[設定と拡張](CONFIGURATION.md)を読み、Git差分と稼働中のコンテナを確認します。既存ホストで初期化・イメージ更新を無条件に実行しないでください。
2. 非公開の `.env`・秘密値・各サービスの状態領域と、原本の実際の保存先を確認します。新規ホストではNetBoxを先に構築し、対象を登録してAnsibleインベントリの `--graph` と配備の `--list-hosts` を確認します。
3. 配備は基本スタック → `platform/ansible/hub.yml` → `platform/ansible/music-tools.yml` → `platform/ansible/sso.yml` の順です。初回構築・ローカル実行の詳細は下記とハブ運用を参照してください。対象ホストは `--limit` で絞ります。
4. 変更は設定の正本と対応する日本語手順へ反映し、下記の検証を実行します。実機へ反映する場合は対象サービスの起動・認証・目的の操作を確認し、再配備による秘密値やデータの保持も確認します。
5. DB・イメージ・保存先を変更する前には対象範囲をバックアップします。基本スタックのバックアップだけでは追加サービス全体を網羅しません。[バックアップ範囲と移設手順](docs/operations/hub.md#データと移設)に従い、復元確認を別環境で行います。

```bash
python3 -m venv .venv
.venv/bin/pip install -r stacks/hub/requirements.txt
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m mkdocs build --strict
# 公開対象を選んでgit addした後に実行
.venv/bin/python tools/check-publication.py
git diff --cached --check
git diff --cached --stat
```

Ansibleを変更した場合は `platform/ansible/requirements.txt` と `platform/ansible/requirements.yml` の依存も導入し、対象Playbookの `--syntax-check` と対象一覧を確認します。公開チェックは既知の秘密値・禁止パスの検出を補助するもので、ステージした差分の目視確認も必要です。GitHubへのpushとサーバー配備は別操作です。

### 現状と未完了事項

- 単一ホストのCompose構成です。複数ノードへのサービス分散・HAは未実装です。NetBoxへホストを増やすと各ホストへ独立した一式を配備します。
- ドメイン未取得のため、現在はSSH転送とローカルCAで利用します。端末ごとのCA登録が必要です。公開ドメインへ移行するときはサービスURL・OIDC issuer・redirect URI・証明書・プロキシ設定をまとめて変更します。ローカルSSOには固定サブネットもあり、移設時はネットワーク衝突を確認します。
- SMTPは事業者・認証情報の決定待ちです。共有Cookie未提供のため、実際のYouTubeダウンロードは未確認です。SSOの実利用者は `stacks/hub/users.example.json` をもとに非公開マニフェストで管理し、メール確認は事実に基づいて設定します。検証用Authentikアカウントは無効化済みです。
- AWX本体は後回しです。導入時のKubernetesは **kubeadm** を使用し、既存PlaybookとNetBoxインベントリを引き継ぎます。
- 別ホストへのSSH配備、公開ACME証明書の発行、バックアップからの復元、実際のゲーム由来BCSTMの網羅的互換性は未検証です。移設・公開前に該当部分を検証してください。

## データの分離

| 対象 | ホスト側（ローカル既定） | コンテナ内 |
| --- | --- | --- |
| 書籍原本 | library/books | Nextcloud: /library/books、Kavita: /books:ro |
| 音楽原本 | library/music | Nextcloud: /library/music、Navidrome: /music:ro |
| 手順書原本 | library/docs | Nextcloud: /docs、MkDocsの入力 |
| Nextcloudアプリ・追加アプリ | storage/nextcloud/html | /var/www/html |
| Nextcloud設定 | storage/nextcloud/config | /var/www/html/config |
| Nextcloud私有データ | storage/nextcloud/data | /var/www/data |
| Nextcloud専用PostgreSQL | storage/postgres | /var/lib/postgresql/data |
| Kavita状態 | storage/kavita | /kavita/config |
| Navidrome状態 | storage/navidrome | /data |
| Vaultwarden DB・添付・鍵 | storage/vaultwarden | /data |
| HTTPS証明書・状態 | storage/caddy | /data、/config |

RedisはNextcloudだけが接続する内部ネットワークで利用し、DB・Redisのポートはホストに公開しません。Nextcloud用cronは5分間隔で動く公式イメージの /cron.sh を利用します。Vaultwardenの保管庫をNextcloudやlibraryへ渡しません。

Nextcloudの権限はKavita・Navidromeへ継承されません。原本ライブラリには各サービスでも公開してよいものを置き、サービスごとにユーザーと権限を設定してください。Nextcloudの外部ストレージは初回作成時に指定管理者だけへ公開し、再実行では既存の公開範囲を保持します。

## NetBox → Ansibleで配備

NetBox本体も新規構築します。まず [NetBoxの初回構築](stacks/netbox/README.md) に従って起動し、配備先と読み取り専用APIトークンを登録してから下の手順へ進みます。通常のアプリ利用にAPIキーは不要です。

管理端末: Python 3.10以降、venv、SSH。配備先: sudo可能なUbuntu/Debian。AnsibleがDocker公式APTリポジトリからEngineとComposeプラグインを導入します。既存Dockerを使う場合は `install_docker: false` を設定します。

1. NetBoxのDeviceまたはVirtual Machineに `media-stack` タグを付け、StatusをActive、Primary IPを設定します。同名Device/VMを作らないでください。
2. 配備先にSSH公開鍵を登録し、初回はSSH接続してホスト鍵を確認します。
3. 管理端末で以下を実行します。

```bash
cd shake-cloud
python3 -m venv .venv
. .venv/bin/activate
pip install -r platform/ansible/requirements.txt
ansible-galaxy collection install -r platform/ansible/requirements.yml

cp platform/ansible/netbox.env.example platform/ansible/netbox.env
chmod 600 platform/ansible/netbox.env
# netbox.envのURLとトークンを編集
set -a
. platform/ansible/netbox.env
set +a

ansible-inventory -i platform/ansible/inventory.netbox.yml --graph
ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/deploy.yml \
  --list-hosts --limit media1
ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/deploy.yml \
  --limit media1 -u ubuntu --ask-become-pass
```

`media1` はNetBox上の実際のホスト名に変更します。パスワード不要sudoなら `--ask-become-pass` は省略できます。SSH鍵は `--private-key` やssh-agentで指定します。Playbookは各対象へ独立した一式を配備します。複数ホストで1つのDBを共有するクラスタではありません。

配備先の既定は `/opt/media-stack`、状態は `/srv/media-stack/storage`、原本は `/srv/media-stack/library` です。変更は `platform/ansible/group_vars/media.yml` またはホスト変数で行います。NetBoxカスタムフィールドを自動的にAnsible変数へ展開しません。AWXへ移行後も配備対象の選択はNetBox側で行います。

環境変数はGit内の.env.exampleと `stack_env` から生成します。秘密値をGitやAWXの通常のExtra Variablesへ入れないでください。DBパスワード・初期管理パスワード・Vaultwarden管理トークンは配備先で初回のみ生成します。

## ローカルのCompose例

Docker EngineとCompose v2が必要です。設定ファイルにはシェル展開を使わず、`KEY=値` を記載します。

```bash
cd shake-cloud/stacks
cp -n .env.example .env
# 必要なら.envを編集
sudo python3 scripts/stack.py init
sudo python3 scripts/stack.py lock
sudo python3 scripts/stack.py up
```

初期化は既存の秘密値を上書きしません。`secrets/` はホスト上で0700、ファイルはコンテナユーザーが読める0444です。各ファイルは必要なコンテナだけにマウントされます。これは通常のComposeのファイルSecretであり、暗号化された秘密管理サービスではありません。

localhost既定のURL:
- Nextcloud: http://localhost:8080 （ユーザーadmin、パスワードは secrets/nextcloud_admin_password）
- Kavita: http://localhost:5000
- Navidrome: http://localhost:4533
- Vaultwarden: http://localhost:8222 （管理画面 /admin、トークンは secrets/vaultwarden_admin_token）

リモート配備先へはSSH転送で接続できます。

```bash
ssh -N -L 8080:127.0.0.1:8080 -L 5000:127.0.0.1:5000 \
  -L 4533:127.0.0.1:4533 -L 8222:127.0.0.1:8222 ubuntu@media1
```

リポジトリルートから `sudo .venv/bin/python stacks/scripts/bootstrap-accounts.py` を実行すると、Kavita・Navidromeの管理者とBooksライブラリをAPIで初期化します。Ansibleでは自動実行します。Kavitaのライブラリは `/books`、Navidromeの音楽は `/music` です。Vaultwardenはサインアップを無効にしています。localhostの/adminから利用者メールアドレスを招待し、そのアドレスで登録します。SMTP未設定時はメール送信されないので招待対象本人が登録画面へ進みます。Vaultwardenの管理設定を保存すると/data/config.jsonが環境変数より優先されるため、その後の設定変更は管理画面と整合させてください。

現在のVaultwarden Web保管庫はAPIにもHTTPSを要求します。SSO配備で `https://vault.localhost:8243` を構成するか、下のHTTPS公開例を使ってください。Nextcloud管理者の初期パスワードも初回インストール用で、ファイルを書き換えるだけでは既存アカウントのパスワードは変更されません。

## HTTPS公開

ドメイン4個を配備先IPへ向け、80/tcp・443/tcpへ到達できるようにします。IPv6のAAAAを設定した場合はIPv6経路も必要です。アプリのBIND_ADDRESSは127.0.0.1を保持します。

Ansible: `platform/awx/job-vars.example.yml` を参考にドメインを実値へ変更した変数ファイルを作り、`-e @変数ファイル.yml` を付けて配備します。`enable_https: true` でCaddyを追加します。

Composeのみの場合: `stacks/compose.https.example.yaml` を `stacks/compose.https.yaml` にコピーし、.envへNEXTCLOUD_HOST、KAVITA_HOST、NAVIDROME_HOST、VAULTWARDEN_HOST、ACME_EMAILを追記。NEXTCLOUD_TRUSTED_DOMAINSへホスト名を追加し、VAULTWARDEN_DOMAINをhttps://から始まる公開URLへ変更します。その後lock、upを再実行します。

CaddyはHTTP challengeで証明書を取得するため、DNS APIキーは不要です。Nextcloudが信頼するプロキシはCaddyの固定IPだけです。172.30.90.0/24が既存ネットワークと衝突する場合はHTTPS用Composeのsubnet・ipv4_address・TRUSTED_PROXIESをまとめて変更します。Vaultwardenの/adminはCaddy側で遮断し、SSH転送経由で管理します。

SMTP・Last.fm APIキーの例は `stacks/compose.integrations.example.yaml` です。Compose手動運用時に `stacks/compose.integrations.yaml` として有効化できます。Ansibleで追加連携を管理する場合は専用のSecret配備を追加してください。

## 原本とNFS

NextcloudのDebian apacheイメージはUID/GID 33で書き込みます。Navidromeも既定では33:33で実行します。Kavita公式イメージの実行ユーザーはイメージの既定を利用し、原本は読み取り専用マウントで保護します。

外部ツールから原本を入れた場合、ディレクトリには走査権限、ファイルにはUID 33の読み取り権限が必要です。既存ファイルを再帰的にchownする処理は自動実行しません。必要に応じて管理者が所有者・ACLを調整してください。Nextcloud外で変更した後は以下でキャッシュを更新し、Kavita側でもスキャンします。Navidromeは1時間間隔でスキャンします。

```bash
sudo docker compose -f stacks/compose.yaml -f stacks/compose.lock.yaml exec -T -u 33:33 \
  nextcloud php occ files:scan --all
```

NFSは事前にホストへマウントし、`LIBRARY_ROOT` で指定します。books/music/docsをNextcloudへ見せるため、NFSサーバー側でUID/GID 33が読み書きできるようにします。NFS未マウントのまま空ディレクトリへ書かないよう、ホスト側で起動順序・mountpointチェックを設定します。PostgreSQL・SQLiteを含むstorageは各ホストのローカルディスクに保持してください。

## バックアップ・復元・移行

```bash
sudo python3 stacks/scripts/stack.py backup --destination /mnt/backup/media-stack
```

全サービスを停止し、state.tar・library.tar・deployment.tar・manifest.jsonを作成後、元々稼働していたサービスだけを再開します。途中失敗時も再開を試み、バックアップは.incomplete名のまま残します。原本も含むためコピー中は停止時間が発生します。NFSなど他の書き込み元も、その間は別途停止してください。アーカイブには保管庫、秘密値、証明書が含まれるため、保存先のアクセス制限と暗号化を行ってください。

復元は稼働中の領域へ上書きせず、新しい空のディレクトリへ行います。同じCPUアーキテクチャ・PostgreSQLメジャー版で、バックアップ内の固定済みイメージを使用します。例:

```bash
sudo mkdir -p /opt/media-restored /srv/media-restored/storage /srv/media-restored/library
sudo tar --numeric-owner -xpf /mnt/backup/media-stack/SNAPSHOT/deployment.tar -C /opt/media-restored
sudo tar --numeric-owner -xpf /mnt/backup/media-stack/SNAPSHOT/state.tar -C /srv/media-restored/storage
sudo tar --numeric-owner -xpf /mnt/backup/media-stack/SNAPSHOT/library.tar -C /srv/media-restored/library
sudoedit /opt/media-restored/.env
# STORAGE_ROOTとLIBRARY_ROOTを復元先へ変更し、必要に応じてドメインも調整。
cd /opt/media-restored
sudo python3 scripts/stack.py up
```

旧ホストは停止したままにし、各アプリへのログイン、書籍閲覧、音楽再生、Vaultwardenの同期・添付ダウンロードを確認してから切り替えます。初期化スクリプトでは既存DBを復元しません。異なるCPUアーキテクチャやPostgreSQLメジャーへ移る場合は、旧環境でpg_dumpを取得して新DBへpg_restoreする別のDB移行工程が必要です。原本libraryはそのまま利用できます。

`lock` は既存のdigestを保持し、追加サービスだけを固定します。意図的な更新はバックアップ後に `lock --refresh-images` → `up`。Nextcloudメジャーは順に更新し、PostgreSQLメジャー更新はデータ移行を行ってください。ロールバックには更新前バックアップを使用します。複数ホストで同一イメージを使う場合はレビュー済みの各compose.lock.yamlをGitで管理して配布します。

## 検証範囲

`python3 -m unittest discover -s tests -v` で原本のマウント分離、秘密値の保持、外部ストレージ登録、digest保持、バックアップ失敗時のサービス復帰を確認します。Compose展開・Ansible構文も検証対象です。

このホストへDocker EngineとComposeを導入し、基本サービス・NetBox・ハブ・SSO・音楽ツールを実起動しました。HTTP応答、管理者認証、原本の共有と読み取り専用制約、Nextcloud cron、NetBox動的インベントリ、Ansibleによるlocal接続での配備・再配備を確認済みです。追加構成では各サービスのSSO（Vaultwardenは初回マスターパスワード設定画面まで）、NetBoxの一般利用者のアクセス拒否、BCSTMテストデータからのMP3変換・原本削除同期を確認しました。別ホストへのSSH配備・ACME発行・バックアップからの復元は未検証です。AWXは構築保留です。

## 参照

- [Nextcloud Local external storage](https://docs.nextcloud.com/server/stable/admin_manual/configuration_files/external_storage/local.html)
- [Nextcloud Docker](https://github.com/nextcloud/docker)
- [Kavita Docker](https://wiki.kavitareader.com/installation/docker/github/)
- [Navidrome Docker](https://www.navidrome.org/docs/installation/docker/)
- [Vaultwarden Compose](https://github.com/dani-garcia/vaultwarden/wiki/Using-Docker-Compose)
- [NetBox inventory plugin](https://docs.ansible.com/projects/ansible/latest/collections/netbox/netbox/nb_inventory_inventory.html)

## 書籍の追加と設定の拡張

PDFは `library/books/作品名/作品名.pdf` のように作品別フォルダへ置きます。books直下には置かないでください。Kavitaではサーバー全体と対象ライブラリの両方でFolder Watchingを有効にすると、変更検出後約10分でスキャンされます。即時反映はライブラリメニューのScanを実行します。bootstrap-accounts.pyでBooksを新規作成する際には監視を有効にします。既存ライブラリの設定は再実行で上書きしません。

設定範囲と拡張時の制約は[CONFIGURATION.md](CONFIGURATION.md)を参照してください。

利用者は[全サービスの使い方](docs/services/usage.md)から始めてください。[Homarrの編集方法](docs/services/homarr.md)や[日本語表示](docs/services/language.md)も利用者向けにまとめています。SSO、SMTP、Nextcloud追加アプリ、配備などの管理作業は[運用ドキュメント](docs/overview.md)から参照できます。

## ハブ・SSO・音楽取り込み

基本配備後、同じNetBoxインベントリで `platform/ansible/hub.yml`、`platform/ansible/music-tools.yml`、`platform/ansible/sso.yml` を順に実行します。[CAとSSH転送の設定](docs/operations/hub.md)を先に確認してください。上記の基本Compose用URLと、SSO有効時の入口は異なります。

- Homarr: http://localhost:7575。`stacks/hub/apps.json` からサービス一覧を反映。
- 日本語手順書: http://localhost:8090。Nextcloudの「docs」で編集し、正本は配備先の `LIBRARY_ROOT/docs`。Gitの `docs/` は初期テンプレート。
- Authentik: https://login.localhost:9443。各サービスの認証連携は[SSO手順](docs/services/sso.md)を参照。
- MeTube: http://localhost:8081。音声を `music/YouTube` へ保存。共有Cookieは画面から登録し、期限切れ時に更新。
- BCSTM: `music` 内の原本を保持し、`music/Converted` へMP3を生成して原本削除も同期。
- タグ: `stacks/music-tools/edit-tags.py` とJSONでMP3タグを変更。
- 自動反映: `media-stack-music-sync.timer` が変更時にNextcloudとNavidromeを更新。

詳細は[ハブ運用](docs/operations/hub.md)、[音楽](docs/services/music.md)、[ディスク増設](docs/operations/disk.md)にあります。

## GitHubへ置くもの

コード、初期Markdownテンプレート、Ansible、設定例、イメージdigestのロックファイルを管理します。Nextcloudで編集した配備先のMarkdownはアプリ状態・原本と同様にバックアップ対象です。`.env`、秘密値、Cookie、実データ、状態、CA、実ホスト台帳、実行ログは `.gitignore` で除外します。公開前に `git diff --cached --stat` と `git diff --cached` で対象を確認してください。

検証は `python3 -m unittest discover -s tests`、ドキュメントは `python -m mkdocs build --strict` です。GitHubへのpushは配備とは別の操作です。
