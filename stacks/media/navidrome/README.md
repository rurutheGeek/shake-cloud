# Navidrome（media-01）

[W05 Navidrome](../../../docs/development/W05-navidrome.md) の開発・配備ユニットです。media-01 のデータディスク `/srv/media-stack` 上に、独立した Compose プロジェクト `media-navidrome` として構築します。データ移行そのものは W05 の手順で行い、このユニットはアプリの再配備を再現するだけです。

## 保存先と公開範囲

- DB・設定・プレイリスト: `${STORAGE_ROOT:-/srv/media-stack/storage}/navidrome` → `/data`
- 音楽の原本: `${LIBRARY_ROOT:-/srv/media-stack/library}/music` → `/music:ro`（**読み取り専用**。追加・変換・タグ付けは取り込み側 W06 に限定する）
- 実行ユーザー: `${MEDIA_UID:-33}:${MEDIA_GID:-33}`
- 公開: `127.0.0.1:${NAVIDROME_PORT:-4533}` のみ。LAN へ直接公開しない
- 走査: `ND_SCANSCHEDULE=@every 1h`、表示言語: `ND_DEFAULTLANGUAGE=ja`

## 認証の前提（注意）

Navidrome は**前段の認証プロキシ（既存メディア SSO）配下で使う前提**です。バックエンドを直接公開したり、認証ヘッダーを偽装して迂回できる経路を作ったりしないでください。HTTPS と SSO は [N05](../../../docs/development/N05-https.md) と [W05](../../../docs/development/W05-navidrome.md) の条件に従います。Subsonic 互換クライアントの認証は別途確認が必要です。

Forward Auth は compose.yaml の環境変数で有効にします。

- `ND_EXTAUTH_USERHEADER: Remote-User` — Caddy（media-01 のホストで host ネットワーク動作）が認証後に付ける利用者名。Caddy 側で必ず上書きし、クライアントの同名ヘッダーを通さない。
- `ND_EXTAUTH_TRUSTEDSOURCES: 127.0.0.1/32,172.16.0.0/12` — このヘッダーを信頼する送信元。Caddy は `127.0.0.1`（host ネットワーク）から届き、コンテナ間は docker bridge の `172.16.0.0/12` になる。
- 公開ポートは `127.0.0.1:${NAVIDROME_PORT:-4533}` のみ。LAN やインターネットから直接ヘッダーを付けられる経路は作らない。

## 使い方（media-01）

```bash
sudo python3 manage.py init   # .env を作成し、保存先を MEDIA_UID:MEDIA_GID で用意する
sudo python3 manage.py lock   # compose.lock.yaml が無いときだけ digest を固定する
sudo python3 manage.py up     # 固定済みイメージで起動し、healthcheck を待つ
python3 manage.py status
sudo python3 manage.py down
```

`init` は `.env.example` から `.env` を作り、0600 にします。`compose.lock.yaml` は `stacks/compose.lock.yaml` の Navidrome digest を複製したもので、`lock` と `up` は既存の固定を書き換えません。`.env` と `compose.lock.yaml` 以外に秘密値は置きません。

## バックアップと復元

```bash
sudo python3 manage.py backup                     # 状態と配備ファイルを backups/ へ冷間取得
sudo python3 manage.py backup --destination /srv/backups/navidrome
```

`backup` は root で実行します（それ以外は `PermissionError`）。稼働中サービスを `docker compose ps --services --status running` で記録し、`stop --timeout 120` で停止してから、状態ディレクトリ `${STORAGE_ROOT}/navidrome`（DB・ユーザー・プレイリスト・お気に入り）を `state.tar`、`compose.yaml`・`compose.lock.yaml`・`.env`・`.env.example`・`manage.py` を `deployment.tar` にまとめ、`manifest.json` を書きます。終了時は元々動いていたサービスだけを再開します。失敗時は `*.incomplete` を残すので、`.incomplete` の無い成功世代だけを使います。

音楽の原本 `${LIBRARY_ROOT}/music` は**バックアップに含みません**。原本は別途バックアップしてください（[O03](../../../docs/development/O03-restore.md) 等）。

復元時は次の点に注意します。

- **同じ CPU アーキテクチャ**へ戻す（`manifest.json` の `architecture` を確認する）。
- サービスを停止してから展開する。稼働中に DB を差し替えない。
- 既存の状態ディレクトリへ上書きしない。空のディレクトリへ展開し、`.env` の `STORAGE_ROOT`・`MEDIA_UID`・`MEDIA_GID` を合わせてから `manage.py up` で起動する。
- 原本（music）の復元は [O03](../../../docs/development/O03-restore.md) の手順に従う。

## Ansible で配備

```bash
.venv/bin/ansible-playbook -i <inventory> platform/ansible/media-navidrome.yml
```

`{{ project_dir }}/media/navidrome` へユニットをコピーし、`storage_root`・`library_root` から `.env` を生成して `manage.py up` を実行します。`project_dir` などの変数は [group_vars/media.yml](../../../platform/ansible/group_vars/media.yml) が正本です。

## 移行元と引き継ぎ

- サービス定義: `stacks/compose.yaml` の navidrome サービス
- イメージ固定: `stacks/compose.lock.yaml` の navidrome digest
- 初期化・所有権: `stacks/scripts/stack.py` の `init` 流儀（保存先と音楽を `MEDIA_UID:MEDIA_GID`、`.env` 0600）
- 走査連携の既存運用: `stacks/scripts/sync-music.py`、[W06 音楽ツール](../../../docs/development/W06-music-tools.md)

DB・ユーザー・プレイリスト・お気に入りの実移行と、`sso_` 利用者のデータ保持の確認は [W05](../../../docs/development/W05-navidrome.md) の検証条件に従います。
