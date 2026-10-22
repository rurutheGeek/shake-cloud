# AGENTS.md

このリポジトリで作業する AI エージェント（Claude Code・opencode など）への指示。どのツールもこのファイルを正本にする。

Proxmox VE（ホスト `apextox`）上のホームラボをTerraform・Ansible・Flux・Docker Composeで構築・運用するリポジトリ。ドキュメント・コミットメッセージは日本語で書く。

## 検証コマンド（CIの `.github/workflows/validate.yml` と同じ）

```bash
.venv/bin/python -m unittest discover -s tests            # 全体の回帰テスト
.venv/bin/python -m unittest tests.test_media_kavita      # 1ファイルだけ
.venv/bin/python -m unittest tests.<module>.<Class>.<test>  # 1テストだけ
terraform fmt -check -recursive platform/terraform
.venv/bin/yamllint -c .yamllint .
.venv/bin/ruff check .                           # 壊れたPython（ruff.toml）
git ls-files '*.sh' | xargs shellcheck --severity=warning  # シェルスクリプト（警告以上）
.venv/bin/mkdocs build --strict
python3 tools/check-publication.py               # 秘密値・禁止パスの公開前チェック
gofmt -l cloud
(cd cloud/api && go vet ./... && go test ./...)  # DBテストは SHAKECLOUD_TEST_DATABASE_URL 指定時のみ実行
(cd cloud/client && go vet ./... && go test ./...)
(cd cloud/cli && go vet ./... && go test ./...)
(cd cloud/mcp && go vet ./... && go test ./...)
(cd cloud/provider && go vet ./... && go test ./...)
go test ./internal/server -run TestName          # cloud/api 内で単一テスト
```

- テストは必ず `.venv/bin/python` で回す。`ansible-playbook` は `.venv` にしか無く、`python3` だとAnsibleの `--syntax-check` テスト（9件）が黙ってスキップされる。Ansibleを触ったら `platform/ansible/requirements.txt`／`requirements.yml` を入れて確認する。
- CIは追跡中の全 `.py` をコンパイルし、全YAMLを `yaml.safe_load` する。CIはさらに各Goモジュールで `govulncheck` も走らせる。

## 全体構成

- `platform/` 基盤：`terraform/10-platform`・`05-seed`（基盤VMとNetBox台帳）、`terraform/services/<name>/`（サービスVMを自作クラウドAPIのTerraform Providerで宣言、サービスごとに1 state）、`ansible/`（配備Playbook）、`flux/`（`main`を監視しAWX・CNPG・Knativeを配るk8s構成）。
- `stacks/<name>/` サービス：ホストごとの独立Docker Compose。外部のイメージは各 `compose.lock.yaml` のdigestで固定（自作の `ghcr.io/ruruthegeek/` は対象外）。各ユニットは `manage.py`（初期化・backup等）を持つ。Ansibleの `source_dir` がstackと配備先の対応点。
- `cloud/` 自作クラウド（VM・S3・database・function）：`api/`（Go、PostgreSQL管理DB、`internal/` にproxmox・garage・cnpg・knative・netbox連携とHTTPサーバ／ポータル `server/web/`）、`client/`（共通Goクライアント）、`cli/`、`mcp/`（読み取り専用MCPサーバ）、`provider/`（Terraform Provider）。**APIの正本は `cloud/openapi/shakecloud.yaml`**。API変更時はopenapi・client・cli・provider・ポータルを揃える。
- インベントリは NetBox 動的インベントリ（`platform/ansible/inventory.netbox.yml`）へ統一済み。グループはNetBoxのタグ（正本 `platform/terraform/tags.yaml`）で、クラウドVMはクラウドAPIが台帳へ登録し `cloud.yaml` の `ledger.tags_by_name` がタグを決める。クラウドVMのホスト名はインスタンスID（`i-...`）なので `--limit` はグループ名で絞る。`seed.ini` はNetBox自身の初回構築・復旧だけ、`pve.ini` はProxmoxホスト用（`docs/operations/services.md` の「Ansibleのインベントリ」）。
- Terraform実行は `tools/tf services/<name> plan|apply`（`SHAKECLOUD_ACCESS_KEY` が必要）。
- URL・DNSの正本は `platform/terraform/dns.yaml`、Homarrタイルは `stacks/homarr/apps.json`、ドキュメントは `docs/`（`mkdocs.yml`、生成サイトは直接編集しない）。

## 守る方針（README「開発方針」より）

- コード化できるものはすべてコードにする。GUI・シェルの一度きり操作を手順書で済ませない。残る手作業は `docs/operations/bootstrap.md` に理由付きで列挙し、増やさない。
- 生成された `.env` だけを直さず、生成元の設定例・スクリプトへ反映する。初期化は既存の秘密値・データを保護し、新しく管理する設定は保持か上書きかを明示する。
- 複数実装がある標準インターフェース（S3互換など）を選び、事業者固有APIへの依存は1モジュールに閉じ込める。
- 秘密値・状態・原本・ログはGitに置かない。
- 実機の状態・進捗・TODOの正本は `docs/operations/handover.md`。実機に関わる変更後はここを更新する（書き方は下の「ドキュメントを直すとき」）。既存ホストで初期化・イメージ更新を無条件に実行しない。
- 作業中に見つけた古い・良くない作りは、黙って回避せず、理由・利点・手間・代わりの案を添えて提案する。依存の追加や構成の変更は了承を得てから行う（README「改善の提案」）。
- GitHubへのpushとサーバー配備は別操作。

## ドキュメントを直すとき

規約の正本は `docs/contributing-docs.md`。とくに次を守る。

- **文書は「いま」だけ。** 経緯（いつ・何をしたか）はコミットメッセージに書き、文書へ追記しない。状態が変わったら上書きし、済んだ行は消す。
- `handover.md` は1行1〜2文。手順・設定値・実測はそのサービスの運用ページへ書き、台帳からはリンクだけ。`tests/test_docs_structure.py` が長さを検査する。
- 同じ事実を2か所に書かない。正本（`docs/map.md` の表）へリンクする。
- 調べて前提が確定したら、それを待っていた文書（計画書の「状態」行、`docs/development/index.md`）まで直す。
- 見出しの直後や表の前に、見出しの言い換えになる前置きを書かない。
- 実機と食い違う記述を見つけたら、コードと実機を確かめて直す。推測で書かない。
- ページを足したら `mkdocs.yml` の nav と節の `index.md` に載せ、`python3 tools/docs-map.py` を流す。
