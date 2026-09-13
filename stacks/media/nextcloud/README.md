# Nextcloud・Calendar・Tasks（media-01）

[W03 Nextcloud・Calendar・Tasksのmedia-01移行](../../../docs/development/W03-nextcloud.md) の開発・配備ユニットです。media-01 のデータディスク `/srv/media-stack` 上に、独立した Compose プロジェクト `media-nextcloud` として構築します。データ移行そのものは W03 の手順で行い、このユニットはアプリの再配備を再現するだけです。

## 構成

- PostgreSQL（DB）と Redis（キャッシュ）は `backend` ネットワークだけで使い、ホストへ公開しません。
- アプリの状態: `${STORAGE_ROOT:-/srv/media-stack/storage}` 配下の `postgres` と `nextcloud/{html,config,data}`
- 共有の原本: `${LIBRARY_ROOT:-/srv/media-stack/library}` 配下の `books`・`music`・`docs` を Nextcloud の外部ストレージとしてマウント
- 公開: `127.0.0.1:${NEXTCLOUD_PORT:-8080}` のみ。LAN へ直接公開せず、HTTPS と SSO は前段の入口（[N05](../../../docs/development/N05-https.md)）で行う
- `cron` コンテナが Nextcloud のバックグラウンドジョブを実行する
- 自作アプリ `shake_print`（ファイル一覧の「…」→「印刷」）を `html/custom_apps/` へ置き、印刷APIのURLとトークンを `occ` で設定する。イメージは固定のままで、コンテナには html ボリューム越しに見える
- Vaultwarden は含まない（[W02](../../../docs/development/W02-vaultwarden.md) で services-01 へ分離）

## 使い方（media-01）

```bash
sudo python3 manage.py init   # .env を作成し、保存先を 33:33 で用意し、secrets/ を生成する
sudo python3 manage.py lock   # compose.lock.yaml が無いときだけ digest を固定する
sudo python3 manage.py up     # 固定済みイメージで起動する
python3 manage.py setup       # files_external と background:cron を有効化し、共有ライブラリを外部ストレージへ登録する
python3 manage.py apps --apps calendar,tasks,text,user_oidc,shake_print
PRINT_API_URL=http://192.168.10.200:6320 PRINT_API_TOKEN=... \
  python3 manage.py config-print   # 印刷APIのURLとトークン（AnsibleはSOPSから渡す）
python3 manage.py status
sudo python3 manage.py down
```

`init` は `.env.example` から `.env` を 0600 で作り、`secrets/postgres_password` と `secrets/nextcloud_admin_password` を既存値を上書きせずに生成します（ディレクトリ 0700、ファイル 0444）。`books`・`music`・`docs` はコンテナの www-data（33:33）が読めるように 33:33 とし、`postgres` のデータ領域はコンテナ自身に任せます。所有権の変更には root が必要で、sudo なしではエラーになります。

`setup` は `occ` を `docker compose exec -T --user 33:33 nextcloud php occ` で実行し、`files_external` と `background:cron` を有効化したうえで、`/books`→`/library/books`・`/music`→`/library/music`・`/docs`→`/docs`・`/inbox`→`/library/inbox` を**ログインできる全員に見える形**（適用先の指定なし）で登録します。既存マウントは上書きせず、同名で `datadir` が違う場合は競合としてエラーにします（アクセス権の手動調整は残したまま再配備できます）。`apps --apps a,b,c` は有効なアプリをそのまま `OK:`、無効なアプリを `app:enable`、未導入のアプリを `app:install` し、変更したものだけ `CHANGED:` と表示します。どちらも繰り返し実行でき、2 回目以降は変更ゼロになります。

初回起動後、`manage.py setup` と `manage.py apps` が Calendar・Tasks・Text・user_oidc・自作の shake_print と外部ストレージを冪等に整えます。移行時は既存 DB の状態を引き継ぐため、アプリを再インストールしません。`docs` の見える範囲は [Nextcloudの手順書アクセス権限](../../../docs/operations/nextcloud-permissions.md) に従います。

`shake_print` のJSは esbuild でバンドルし、`js/shake_print.js` をリポジトリに含めます（ビルドは `npm install && npm run build`、`node_modules` は配備しません）。`config-print` は `occ config:app:set` で `print_api_url` と `print_api_token` を設定し、同じ値なら `OK:` を出します。

## Ansible で配備

```bash
.venv/bin/ansible-playbook -i <inventory> platform/ansible/media-nextcloud.yml
```

`{{ project_dir }}/media/nextcloud` へユニットをコピーし、`storage_root`・`library_root` から `.env` を生成して `manage.py init`・`manage.py up`・`manage.py setup`・`manage.py apps --apps ...`・`manage.py config-print` を実行します。アプリ一覧は [group_vars/media.yml](../../../platform/ansible/group_vars/media.yml) の `nextcloud_apps` を正本とし、このプレイが自作の `shake_print` を足します（ストアに無いアプリを旧スタックの `deploy.yml` に渡さないため）。印刷APIのURLは同じ group_vars の `nextcloud_print_api_url`、トークンは `platform/sops/print-api.sops.yaml` から読みます。`CHANGED:` を含む出力だけが変更として数えられ、再実行では変更ゼロになります。`project_dir` などの変数は同じ group_vars が正本です。手動 SSH や手動 `docker compose` は前提にしません。既存ホストへの再実行は、このユニットのディレクトリと `/srv/media-stack` の該当サブディレクトリだけを冪等に更新します。

## 移行元と引き継ぎ

- サービス定義: [既存Compose](../../compose.yaml) の nextcloud・postgres・redis・cron
- イメージ固定: [stacks/compose.lock.yaml](../../compose.lock.yaml) の nextcloud・postgres・redis digest
- 初期化・所有権: [stacks/scripts/stack.py](../../scripts/stack.py) の `init` 流儀（保存先 33:33、`.env` 0600、秘密値は上書きしない）

## バックアップと復元

- Nextcloud を停止してから `storage` と `library` を `tar --numeric-owner` で取ります。DB は `storage/postgres` にあり、コールド状態のコピーとして同じ PostgreSQL 17 イメージへ戻します。
- `secrets/`（DB パスワードと管理者パスワード）と `.env`・`compose.yaml`・`compose.lock.yaml` も一緒に保管します。秘密値を Git へ入れません。
- 復元先は元と同じ `/srv/media-stack` のパスにし、UID/GID 33 を保ったまま展開します。別ホストへ戻す場合は `NEXTCLOUD_TRUSTED_DOMAINS` と `BIND_ADDRESS` を見直します。
- 戻したら `manage.py up` の後、アップロード・ダウンロード・共有、Calendar/Tasks、スマホの CalDAV 同期、cron の実行を確認します。移行の完了条件は [W03](../../../docs/development/W03-nextcloud.md) を正とします。
