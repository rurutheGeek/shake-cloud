# FreshRSS（media-01）

全員で1つのRSSタイムラインを共有するための [FreshRSS](https://freshrss.org/) ユニットです。media-01 のデータディスク `/srv/media-stack` 上に、独立した Compose プロジェクト `media-freshrss` として構築します。SSO は identity の Authentik へ**ネイティブ OIDC**で接続し、購読リストは同梱の **SharedFeeds 拡張**が全ユーザーで共有します。

## サービスと保存先

- 公開URL: <https://freshrss.apextox.dpdns.org>（Caddy が TLS を終端）
- 公開ポート: `127.0.0.1:${FRESHRSS_PORT:-8082}` のみ。LAN へ直接公開しない
- データ: `${STORAGE_ROOT:-/srv/media-stack/storage}/freshrss/data` → `/var/www/FreshRSS/data`（SQLite の実体は `data/users/<user>/db.sqlite`）
- 実行ユーザー: `${MEDIA_UID:-33}:${MEDIA_GID:-33}`（Debian の www-data）
- フィード取得: `CRON_MIN=${FRESHRSS_CRON_MIN:-2,17,32,47}`（15分間隔）
- 表示言語: `ja`

## 認証（ネイティブ OIDC）

FreshRSS の Debian 版イメージは `mod_auth_openidc` を同梱し、`OIDC_*` 環境変数で Authentik に接続します。コールバックは `https://freshrss.apextox.dpdns.org/i/oidc/` で、identity の `configure.py` がこの厳密一致のリダイレクト URI を持つクライアント `freshrss` を作ります。

- `OIDC_REMOTE_USER_CLAIM=preferred_username` — Authentik のユーザー名をそのまま FreshRSS のユーザー名にする
- 初回ユーザーは `FRESHRSS_DEFAULT_USER`（既定 `akadmin`）。**既定ユーザーは FreshRSS の管理者**になる（`FreshRSS_Auth::hasAccess('admin')`）。`akadmin` の `preferred_username` と一致させること
- `OIDC_X_FORWARDED_HEADERS` は Caddy の `X-Forwarded-Proto/Host/Port` から戻り URL を作るために必須
- `TRUSTED_PROXY=127.0.0.0/8 172.16.0.0/12` — Caddy（host ネットワーク）とコンテナ間だけを信頼する

## 共通タイムライン（SharedFeeds 拡張）

FreshRSS は購読リストをユーザーごとに持つため、そのままでは「別アカウントなのに全員同じタイムライン」になりません。`extensions/xExtension-SharedFeeds/` は **system 拡張**で、標準フックを使って購読を全ユーザーへ同報します。

- 追加: `feed_before_insert`（`app/Controllers/feedController.php`）で、その場で他の全ユーザーのDBへ同じフィードを複製
- 削除: `action_execute`（`lib/Minz/Dispatcher.php`）で、削除前に他の全ユーザーから同じURLを削除
- 初回ログイン: `freshrss_init` で、購読がまだ無いユーザーへ既存分をまとめて配布
- 既読・未読はユーザーごとのDBに残る。共有するのは**購読リストだけ**
- 他ユーザーへの書き込みは `FreshRSS_Factory::createFeedDao($username)`（ユーザー名を受け取れるDAO）と `FreshRSS_user_Controller::listUsers()` を使う。タイマーや外部ファイル編集は使わない

有効化は `manage.py configure` が `data/config.php` の `extensions_enabled` に `SharedFeeds` を足します（初回インストール時に限らず冪等）。拡張のソースはリポジトリの `stacks/media/freshrss/extensions/` が正本で、コンテナへは読み取り専用で渡します。

### 制約

- 追加・削除は**そのリクエスト内で**他ユーザーのDBへ書く。SQLite は同時書き込みに弱いため、複数人が同時に操作したときは片方の同報が `database is locked` で失敗し得る（拡張は警告ログを出して本人の操作は続ける）。
- **削除の同報はWeb UIからのみ**。Google Reader API（スマホアプリ）の解除は `FreshRSS_feed_Controller::deleteFeed` を直接呼ぶためフックが発火せず、他ユーザーには残る。フィードを消すときはWeb UIで行う。追加はAPIでも同報される。
- **新規ユーザーは初回のWebログインで共通リストを受け取る**。APIだけを使うユーザーには配られない。`data/opml.xml` を空にして FreshRSS の既定フィード（FreshRSS releases）を無効化している（既定フィードがあると「購読が空」と見なされず配布がスキップされるため）。
- 共有するのは購読リストだけで、記事・既読・お気に入りはユーザーごとに独立する。
- カテゴリ名も引き継ぐ。相手側に同じ名前が無ければ作る。同名カテゴリが別用途で存在する場合は same 扱いになる点に注意する。
- Reddit（`r/...`）は同じIPからの大量取得を強く制限する（HTTP 429）。`feeds.opml` の Reddit 行には Reddit が要求する形式の `frss:CURLOPT_USERAGENT`（`linux:shakecloud.freshrss:1.0 (by /u/shakecloud)`）を付けている。それでも初回は一部しか取れないことがあり、成功したフィードは1時間スキップされるため、15分ごとの取得で順次そろっていく。

## 使い方（media-01）

```bash
sudo python3 manage.py init        # .env・データ領域・秘密値を用意する
sudo python3 manage.py lock        # compose.lock.yaml が無いときだけ digest を固定する
sudo python3 manage.py up          # 起動し、healthcheck を待って拡張を有効化＋初期フィード投入
sudo python3 manage.py configure   # 拡張の有効化だけをやり直す
sudo python3 manage.py seed        # 初期フィード（feeds.opml）の投入だけをやり直す
python3 manage.py status
sudo python3 manage.py down
```

`init` は `.env.example` から `.env` を作り、0600 にします。秘密値は `secrets/` に生成し（0600のディレクトリ、0400のファイル）、`manage.py` が環境変数として Compose へ渡します。`.env` には秘密値を置きません。OIDC クライアントの `secrets/oidc_client.json` は identity 側から Ansible が配ります。

`feeds.opml` は共通タイムラインの初期フィード（ゲーム・IT・ポケモンの3タイムライン＋サブレディットをまとめた **Reddit**＋追加候補を試す **Review**）です。`up` の最後に**一度だけ**既定ユーザー（`akadmin`）へ取り込みます。以後の追加・削除は FreshRSS の画面から全員で行い、SharedFeeds 拡張が反映します。取り込み済みかは `secrets/feeds_seeded` で管理するため、再配備で消したフィードが復活しません。

> `xmlUrl` は**リダイレクト後の正規URL**を書くこと。FreshRSS は取得後に正規URLを保存するため、違うURLで再インポートすると重複する（2026-09-13に5組発生）。

## バックアップと復元

```bash
sudo python3 manage.py backup                     # 状態と配備ファイルを backups/ へ冷間取得
sudo python3 manage.py backup --destination /srv/backups/freshrss
```

`backup` は root で実行します。稼働中サービスを記録し、`stop --timeout 120` で停止してから、状態ディレクトリ `${STORAGE_ROOT}/freshrss`（SQLite の実データ）を `state.tar`、`compose.yaml`・`compose.lock.yaml`・`.env`・`.env.example`・`manage.py`・`extensions`・`secrets` を `deployment.tar` にまとめ、`manifest.json` を書きます。終了時は元々動いていたサービスだけを再開します。失敗時は `*.incomplete` を残すので、`.incomplete` の無い成功世代だけを使います。

復元時は次の点に注意します。

- **同じ CPU アーキテクチャ**へ戻す（`manifest.json` の `architecture` を確認する）。
- サービスを停止してから展開する。稼働中に SQLite を差し替えない。
- 既存の状態ディレクトリへ上書きしない。空のディレクトリへ展開し、`.env` の `STORAGE_ROOT`・`MEDIA_UID`・`MEDIA_GID` を合わせてから `manage.py up` で起動する。
- `secrets/` を復元しないと OIDC ログインができない。identity 側の `oidc-media.json` と対になっていることを確認する。

## Ansible で配備

```bash
.venv/bin/ansible-playbook -i platform/ansible/inventory.cloud.py platform/ansible/media-freshrss.yml
```

`{{ project_dir }}/media/freshrss` へユニットをコピーし、`storage_root` から `.env` を生成、identity VM の `oidc-media.json` から `secrets/oidc_client.json` を配り、`manage.py up` を実行します。`project_dir` などの変数は [group_vars/media.yml](../../../platform/ansible/group_vars/media.yml) が正本です。identity がまだ配備されていない場合は OIDC クライアントが無いため、先に identity を配備してください。

## 正本

- 受ける名前と中継先: `platform/terraform/dns.yaml` の `freshrss`（正本）
- 拡張: `stacks/media/freshrss/extensions/xExtension-SharedFeeds/`（正本）
- identity のクライアント: `stacks/identity/configure.py` の `MEDIA_OIDC_CLIENTS`
- 利用手順: [RSSタイムラインの使い方](../../../docs/services/rss.md)
