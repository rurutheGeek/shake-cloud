# Kavita（media-01）

[W04 Kavita](../../../docs/development/W04-kavita.md) の開発・配備ユニットです。media-01 のデータディスク `/srv/media-stack` 上に、独立した Compose プロジェクト `media-kavita` として構築します。データ移行そのものは W04 の手順で行い、このユニットはアプリの再配備を再現するだけです。

## 保存先と公開範囲

- アプリの設定・DB: `${STORAGE_ROOT:-/srv/media-stack/storage}/kavita` → `/kavita/config`
- 本の原本: `${LIBRARY_ROOT:-/srv/media-stack/library}/books` → `/books:ro`（**読み取り専用**。原本を複製も変更もしない）
- 公開: `127.0.0.1:${KAVITA_PORT:-5000}` のみ。LAN へ直接公開せず、HTTPS と SSO は前段の入口（[N05](../../../docs/development/N05-https.md)）で行う
- タイムゾーン: `${TZ:-Asia/Tokyo}`

## 使い方（media-01）

```bash
sudo python3 manage.py init   # .env を作成し、保存先を 33:33 で用意する
sudo python3 manage.py lock   # compose.lock.yaml が無いときだけ digest を固定する
sudo python3 manage.py up     # 固定済みイメージで起動する
python3 manage.py status
sudo python3 manage.py down
```

`init` は `.env.example` から `.env` を作り、0600 にします。`compose.lock.yaml` は `stacks/compose.lock.yaml` の Kavita digest を複製したもので、`lock` と `up` は既存の固定を書き換えません。`.env` と `compose.lock.yaml` 以外に秘密値は置きません。

## 初回管理者と Books ライブラリ

`manage.py up` のあと、`bootstrap.py` が Kavita の API を叩いて初期状態を整えます。`bootstrap.py` と `configure-oidc.py` は **Python の `requests` モジュールを使う**ため、手動で動かす環境には `python3-requests` が要ります（Ansible は導入タスクを持つ）。

```bash
sudo python3 bootstrap.py
```

- 管理者 `admin` を `secrets/accounts.json`（ディレクトリ 0700・ファイル 0600）に一度だけ生成し、以降は既存を尊重する。パスワードは `Aa1!` + 乱数で、標準出力には出さない。
- 未登録なら `/api/Account/register` でメール `admin@localhost.localdomain` を付けて登録する。既に管理者が居ればログインだけする。
- `Books` ライブラリ（コンテナ内 `/books`）が無ければ作成し、Folder Watching を有効にする。あれば何もしない。
- 結果は `CHANGED:` / `OK:` で出す。Ansible は `CHANGED:` のときだけ changed と数える。

## SSO（ネイティブ OIDC）

`configure-oidc.py` が `/api/Settings` の `oidcConfig` を identity VM の Authentik に合わせます。`KAVITA_OIDC_CLIENT_ID` / `KAVITA_OIDC_CLIENT_SECRET` を環境変数で渡し、secret は標準出力に書きません。

```bash
sudo KAVITA_OIDC_CLIENT_ID=... KAVITA_OIDC_CLIENT_SECRET=... python3 configure-oidc.py
```

- authority: `https://auth.apextox.dpdns.org/application/o/kavita/`
- provisionAccounts / requireVerifiedEmail / defaultIncludeUnknowns を有効化、syncUserSettings は無効。既定ロールは `Pleb`・`Login`・`Download`・`Bookmark`、既定ライブラリは `Books` の ID。
- 設定が既に一致していれば `OK:` を出して再起動しない。差分があるときだけ POST して `docker compose restart kavita` する。
- 実行順は `bootstrap.py` が先（Books の ID が要る）。

Ansible では `media-kavita-sso.yml` が identity VM の `/opt/identity-stack/secrets/oidc-media.json` から client id/secret を読んで同じことをします。media-01 と identity の両方が解決できる inventory で、必要なら `--limit` を付けて実行します。

## バックアップと復元

```bash
sudo python3 manage.py backup                     # 状態と配備ファイルを backups/ へ冷間取得
sudo python3 manage.py backup --destination /srv/backups/kavita
```

`backup` は root で実行します（それ以外は `PermissionError`）。稼働中サービスを `docker compose ps --services --status running` で記録し、`stop --timeout 120` で停止してから、状態ディレクトリ `${STORAGE_ROOT}/kavita` を `state.tar`、`compose.yaml`・`compose.lock.yaml`・`.env`・`.env.example`・`manage.py` を `deployment.tar` にまとめ、`manifest.json` を書きます。終了時は元々動いていたサービスだけを再開します。失敗時は `*.incomplete` を残すので、`.incomplete` の無い成功世代だけを使います。

本の原本 `${LIBRARY_ROOT}/books` は**バックアップに含みません**。原本は別途バックアップしてください（[O03](../../../docs/development/O03-restore.md) 等）。

復元時は次の点に注意します。

- **同じ CPU アーキテクチャ**へ戻す（`manifest.json` の `architecture` を確認する）。
- サービスを停止してから展開する。稼働中に DB を差し替えない。
- 既存の状態ディレクトリへ上書きしない。空のディレクトリへ展開し、`.env` の `STORAGE_ROOT` を合わせてから `manage.py up` で起動する。
- 原本（books）の復元は [O03](../../../docs/development/O03-restore.md) の手順に従う。

## Ansible で配備

```bash
.venv/bin/ansible-playbook -i <inventory> platform/ansible/media-kavita.yml
```

`{{ project_dir }}/media/kavita` へユニットをコピーし、`storage_root`・`library_root` から `.env` を生成して `manage.py up` を実行し、続けて `bootstrap.py` で管理者と Books ライブラリを整えます。`project_dir` などの変数は [group_vars/media.yml](../../../platform/ansible/group_vars/media.yml) が正本です。

## 移行元と引き継ぎ

- サービス定義: `stacks/compose.yaml` の kavita サービス
- イメージ固定: `stacks/compose.lock.yaml` の kavita digest
- 初期化・所有権: `stacks/scripts/stack.py` の `init` 流儀（保存先 33:33、`.env` 0600）

本の原本・ライブラリ ID・読書進捗・ブックマークの実移行と SSO の紐付けは [W04](../../../docs/development/W04-kavita.md) の検証条件に従います。
