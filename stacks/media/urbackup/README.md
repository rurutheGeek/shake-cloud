# クライアントバックアップ UrBackup（media-01）

[W08 クライアント端末のバックアップ](../../../docs/development/W08-client-backup.md) の開発・配備ユニットです。Windows PC の**ファイルとシステムイメージの世代バックアップ**を media-01 の独立した Compose プロジェクト `media-urbackup` として構築します。Android は既存の Nextcloud で担保し、このユニットには含めません（[クライアントバックアップ運用](../../../docs/operations/client-backup.md)）。

## 保存先と公開範囲

- サーバー状態（DB・設定・識別鍵）: `${STORAGE_ROOT:-/srv/media-stack/storage}/urbackup` → `/var/urbackup`（ローカルデータディスク）
- バックアップ本体: `${CLIENT_BACKUP_ROOT:-/srv/media-stack/client-backups}/urbackup` → `/backups`（6TB HDD の NFS 共有）
- 実行ユーザー: `${URBACKUP_UID:-101}:${URBACKUP_GID:-101}`（HDD 側 export の `anonuid=101` と揃える）
- 公開:
  - バックアップポータル: `127.0.0.1:${PORTAL_PORT:-55416}`（`https://backup.apextox.dpdns.org`。Forward Auth）
  - UrBackup 管理画面: `127.0.0.1:${URBACKUP_WEB_PORT:-55414}`（`https://urbackup.apextox.dpdns.org`。Forward Auth）
  - クライアント通信: `${BIND_ADDRESS}:${URBACKUP_CLIENT_PORT:-55413}`（Forward Auth を通せないため LAN へ直接）
  - 自動発見: `${URBACKUP_BROADCAST_PORT:-35623}/udp`

`/backups` はイメージの entrypoint が `backupfolder` に書く固定パスです。ハードリンクでイメージを重複排除するため、バックアップ本体は**同一ファイルシステム**上へ置きます（NFS の `/srv/bulk/client-backups` がそれ）。

## バックアップポータル（portal）

`portal.py` が同じ Compose プロジェクトの `portal` サービス（`python:3.13-alpine`、読み取り専用）として動きます。UrBackup の `/x` API からクライアントの状態（オンライン・最終ファイル・最終イメージ）を読み、Windows の手順と、**USBでつないだ Galaxy をブラウザーから直接バックアップするボタン**（WebUSB）を1ページで出します。

- Android のバックアップは `portal-backup.js`（`portal-web/` を esbuild でバンドルした成果物）がブラウザー側で ADB over WebUSB を話し、ファイルを `/api/android/chunk`・`/api/android/finish`・`/api/android/manifest` へストリームします。保存先は `${CLIENT_BACKUP_ROOT}/android/<端末>/files/...` と `apk/`、インデックスは `index.json`。
- 管理パスワードは `secrets/urbackup_admin_password` を読み取り専用でマウントして API のログインにだけ使い、HTML には出しません。手順の文言は `portal.py` の `DEVICES` が正本です。
- **再ビルド**（`portal-web/src/main.js` を変えたとき。Node.js が要る）:

```bash
cd portal-web
npm install          # package-lock.json で固定
npm run build        # ../portal-backup.js を更新する
```

生成物 `portal-backup.js` はリポジトリに含め、Ansible が `portal.py` と一緒に配ります。

## 初期設定（settings.json）

`manage.py configure` が管理画面の Web API（`/x`）へ次の値を冪等に適用します。値は `settings.json` が正本です。

- `server_url`: クライアントの「バックアップへアクセス/復元」が開く URL（SSO 付きの HTTPS）
- `default_dirs`: `C:\Users|Users`（ファイルバックアップの既定）
- `image_letters`: `C`（システムイメージの対象。全ドライブに広げるなら `ALL`）
- `internet_mode_enabled`: `false`（LAN 内は 55413 直結。宅外バックアップは未設定）

管理者パスワードは `manage.py init` が `secrets/urbackup_admin_password`（0700 ディレクトリ・0400 ファイル）へ生成し、初回の `configure` が `urbackupsrv reset-admin-pw` で設定します。既存の値は上書きしません。

## 使い方（media-01）

```bash
sudo python3 manage.py init       # .env と保存先、secrets/ の管理者パスワードを用意する
sudo python3 manage.py lock       # compose.lock.yaml が無いときだけ digest を固定する
sudo python3 manage.py up         # 固定済みイメージで起動し、healthcheck を待つ
sudo python3 manage.py configure  # 管理者パスワードを設定し、settings.json を適用する
python3 manage.py status
sudo python3 manage.py down
```

`init` は `.env.example` から `.env` を 0600 で作り、`storage`・`client-backups` を `URBACKUP_UID:URBACKUP_GID` で用意します。`lock` と `up` は既存の digest 固定を書き換えません。`up` は `urbackup` と `portal` の2サービスを起動します。入口はポータルが `https://backup.apextox.dpdns.org`、管理画面が `https://urbackup.apextox.dpdns.org` です。

## バックアップと復元

```bash
sudo python3 manage.py backup                     # サーバー状態と配備ファイルを backups/ へ冷間取得
sudo python3 manage.py backup --destination /srv/backups/urbackup
```

`backup` は root で実行します。稼働中サービスを記録し、`stop --timeout 120` で止めてから、`${STORAGE_ROOT}/urbackup`（DB・設定・識別鍵）を `state.tar`、配備ファイル一式を `deployment.tar` にまとめ、`manifest.json` を書きます。終了時は元々動いていたサービスだけを再開します。失敗時は `*.incomplete` を残すので、`.incomplete` の無い成功世代だけを使います。

- **端末のバックアップ本体（`/srv/bulk/client-backups`）はこの `backup` に含みません。** それ自体がバックアップなので、[共有バルクストレージ](../../../docs/operations/bulk-storage.md)の方針どおり、別ディスク・別機器へのコピーを別途行います。
- 復元は同じ CPU アーキテクチャへ、サービスを止めて空のディレクトリへ展開します。`.env` のパスと UID/GID を合わせ、`secrets/urbackup_admin_password` も戻してから `manage.py up` → `configure` を実行します。
- **イメージからのベアメタル復元**は UrBackup の復元メディア（Restore CD/USB）を使う端末側の操作です。手順は[クライアントバックアップ運用](../../../docs/operations/client-backup.md)に書きます。

## Ansible で配備

```bash
.venv/bin/ansible-playbook -i <inventory> platform/ansible/media-urbackup.yml
```

`{{ project_dir }}/media/urbackup` へユニット（`portal.py` を含む）をコピーし、`storage_root`・`client_backup_root`・`ansible_host` から `.env` を生成して `manage.py init`・`up`・`configure` を実行します。`project_dir` などの変数は [group_vars/media.yml](../../../platform/ansible/group_vars/media.yml) が正本です。
