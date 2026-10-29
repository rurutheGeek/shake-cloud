# shake-cloud

Proxmox VE の上に小さなセルフホスト型クラウドを作るための一式です。ブラウザの
ポータルから VM（インスタンス）を作成・起動・停止し、ボリューム、セキュリティ
グループ、S3 互換のバケット、Kubernetes 上のデータベース、常時動くサービスや
関数を管理できます。VM の台帳は NetBox と同期し、操作は監査ログに残ります。

## 構成

| パス | 内容 |
| --- | --- |
| `api/` | API とポータルを配信する Go のサーバ。`api/internal/server/web` に画面がある |
| `client/` | API を叩く Go のクライアントライブラリ |
| `cli/` | `shakecloud` コマンド |
| `mcp/` | 読み取り専用のツールを公開する MCP サーバ |
| `provider/` | Terraform プロバイダ |
| `openapi/shakecloud.yaml` | API の定義。ルートと操作はここを正とする |
| `manage.py` | 配備先での初期化・起動・バックアップなどの管理コマンド |
| `render_site.py` | Terraform の宣言から API が読む `site.json` を作る |
| `compose.yaml` | API と PostgreSQL の Compose 定義 |

## 動かし方

### テスト

Python 3.13 と PyYAML が要ります。

```sh
python3 -m pip install pyyaml
python3 -m unittest discover -s tests
```

Lint と構文チェックは CI と同じコマンドで確認できます。

```sh
python3 -m pip install ruff==0.16.10
python3 -m ruff check --select E9,F .
python3 -m compileall -q .
```

Go の各モジュールは個別にテストします。`api` の結合テストは PostgreSQL を使う
ため、接続先を `SHAKECLOUD_TEST_DATABASE_URL` で渡します（未設定ならスキップ
されます）。

```sh
for dir in api client cli mcp provider; do
  (cd "$dir" && go vet ./... && go test ./...)
done
```

### 配備

配備先では Docker と Docker Compose を使います。秘密値はリポジトリに置かず、
`secrets/` に配備側の仕組みから写します。`manage.py init` は `.env`、データ用
ディレクトリ、管理用の秘密値を一度だけ作ります（既存の値は作り直しません）。

```sh
python3 manage.py init     # .env と secrets/ を用意する
python3 manage.py lock     # 取得するイメージを digest で固定する
python3 manage.py up       # API と PostgreSQL を起動する
python3 manage.py status   # 状態を見る
python3 manage.py backup --keep 7
```

API は Authentik の OIDC でブラウザログインし、CLI・Terraform・MCP は
`Authorization: Bearer sca_...` のアクセスキーで認証します。キーはポータルで
発行します。`site.json` は配備側の Terraform 宣言から `render_site.py` で生成し、
Compose が読み取り専用でマウントします。

## CI

`.github/workflows/ci.yml` が push と pull request で、Python の lint・構文
チェック・単体テスト、Go の整形・vet・テスト・脆弱性スキャン、API イメージの
ビルドを行います。
