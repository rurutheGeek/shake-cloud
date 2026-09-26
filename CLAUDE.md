# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Proxmox VE（ホスト `apextox`）上のホームラボをTerraform・Ansible・Flux・Docker Composeで構築・運用するリポジトリ。ドキュメント・コミットメッセージは日本語で書く。

## 検証コマンド（CIの `.github/workflows/validate.yml` と同じ）

```bash
python3 -m unittest discover -s tests            # 全体の回帰テスト
python3 -m unittest tests.test_media_kavita      # 1ファイルだけ
python3 -m unittest tests.<module>.<Class>.<test>  # 1テストだけ
terraform fmt -check -recursive platform/terraform
.venv/bin/yamllint -c .yamllint .
.venv/bin/mkdocs build --strict
python3 tools/check-publication.py               # 秘密値・禁止パスの公開前チェック
gofmt -l cloud
(cd cloud/api && go vet ./... && go test ./...)  # DBテストは SHAKECLOUD_TEST_DATABASE_URL 指定時のみ実行
(cd cloud/client && go vet ./... && go test ./...)
(cd cloud/cli && go vet ./... && go test ./...)
(cd cloud/provider && go vet ./... && go test ./...)
go test ./internal/server -run TestName          # cloud/api 内で単一テスト
```

- `tests/` のAnsible `--syntax-check` テストは `ansible-playbook` が無いとスキップされる。Ansibleを触ったら `platform/ansible/requirements.txt`／`requirements.yml` を入れて確認する。
- CIは追跡中の全 `.py` をコンパイルし、全YAMLを `yaml.safe_load` する。

## 全体構成

- `platform/` 基盤：`terraform/10-platform`・`05-seed`（基盤VMとNetBox台帳）、`terraform/services/<name>/`（サービスVMを自作クラウドAPIのTerraform Providerで宣言、サービスごとに1 state）、`ansible/`（配備Playbook）、`flux/`（`main`を監視しAWX・CNPG・Knativeを配るk8s構成）。
- `stacks/<name>/` サービス：ホストごとの独立Docker Compose。イメージは各 `compose.lock.yaml` のdigestで固定。各ユニットは `manage.py`（初期化・backup等）を持つ。Ansibleの `source_dir` がstackと配備先の対応点。
- `cloud/` 自作クラウド（VM・S3・database・function）：`api/`（Go、PostgreSQL管理DB、`internal/` にproxmox・garage・cnpg・knative・netbox連携とHTTPサーバ／ポータル `server/web/`）、`client/`（共通Goクライアント）、`cli/`、`provider/`（Terraform Provider）。**APIの正本は `cloud/openapi/shakecloud.yaml`**。API変更時はopenapi・client・cli・provider・ポータルを揃える。
- インベントリは3系統：基盤はNetBox動的インベントリ、クラウドVMは `platform/ansible/inventory.cloud.py`、services-01は `seed.ini`、monitor-01は `monitor.ini`。**クラウドとNetBoxのインベントリを併用しない**（群が和集合になる）。
- Terraform実行は `tools/tf services/<name> plan|apply`（`SHAKECLOUD_ACCESS_KEY` が必要）。
- URL・DNSの正本は `platform/terraform/dns.yaml`、Homarrタイルは `stacks/homarr/apps.json`、ドキュメントは `docs/`（`mkdocs.yml`、生成サイトは直接編集しない）。

## 守る方針（README「開発方針」より）

- コード化できるものはすべてコードにする。GUI・シェルの一度きり操作を手順書で済ませない。残る手作業は `docs/operations/bootstrap.md` に理由付きで列挙し、増やさない。
- 生成された `.env` だけを直さず、生成元の設定例・スクリプトへ反映する。初期化は既存の秘密値・データを保護し、新しく管理する設定は保持か上書きかを明示する。
- 複数実装がある標準インターフェース（S3互換など）を選び、事業者固有APIへの依存は1モジュールに閉じ込める。
- 秘密値・状態・原本・ログはGitに置かない。
- 実機の状態・進捗・TODOの正本は `docs/operations/handover.md`。実機に関わる変更後はここを更新する。既存ホストで初期化・イメージ更新を無条件に実行しない。
- GitHubへのpushとサーバー配備は別操作。
