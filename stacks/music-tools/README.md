# music-tools の配備と Picard の使い方

media-01 の音楽導線（MeTube 取込 → Nextcloud 共有 music → Picard でタグ付け → Navidrome 表示）を担うスタックです。仕様・進捗の正本は [W06](../../docs/development/W06-music-tools.md)、Picard の位置づけは [D05](../../docs/development/D05-picard.md) です。

状態: **media-01 で MeTube・Picard・変換・タグAPIが稼働中（2026-09-13）。タグAPIはNextcloudの「タグを編集」が使う。同期タイマーは停止中（W06の残り）**。共有 Cookie の実物は未登録です。

## 構成

| サービス | 内容 | 入口 |
| --- | --- | --- |
| metube | 音源・動画の取込 | `127.0.0.1:${METUBE_PORT:-8081}` |
| picard | MusicBrainz Picard の Web GUI | `127.0.0.1:${PICARD_PORT:-5800}` |
| convert | BCSTM 変換ワーカー | なし（常駐） |
| tag-api | タグの読み書きとMusicBrainz検索（Nextcloudの「タグを編集」用、[tag_api.py](tag_api.py)） | `0.0.0.0:${TAG_API_PORT:-5810}`（トークン認証） |
| tagger | 手動タグ付け（profile: tools） | なし |

共有 music の実体は `${LIBRARY_ROOT}/music`。Picard はそこを `/storage` へ読み書き（rw）でマウントし、設定・作業状態は `storage/picard`（コンテナ内 `/config`）へ分離しています。BCSTM 原本と `music/Converted/` は直接編集しません。

`.env.example` は秘密値を含まない参照用です。実値の `.env` は配備先で 0600 になります。共有 Cookie などの実値は Git に置かず、対象ホストへ配ります。

## Ansible での配備（正本）

```sh
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/music-tools.yml
```

既定では `metube`・`picard`・`convert` の全サービスを配備し、同期タイマーを有効化します。既存ホスト（services-01・media-01）への再実行もこの既定で同じ結果になります。

Picard だけを段階配備する場合:

```sh
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/music-tools.yml \
  -e music_tools_services=picard
```

同期タイマーは既定で有効のままです。Nextcloud／Navidrome がまだ同居していない媒体では、タイマーが無駄に失敗しないよう止めておきます。

```sh
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/music-tools.yml \
  -e music_tools_services=picard -e music_tools_sync_enabled=false
```

ポートや TZ を変える場合はホストの `.env` を直接編集せず、`-e music_tools_picard_port=5801` のように playbook 変数で渡します（playbook が `.env` を生成し直すためです）。

## 先行配備からの収束

Picard は 2026-09-12 に手動 SSH の `manage.py init` と `docker compose up -d --wait picard` だけで先行配備しました。これは一時手段であり、以後の正本は playbook です。media-01 へ次を再適用すると、playbook が `compose.yaml`・`compose.lock.yaml`・`manage.py`・`.env` を配り直し、`manage.py up --services picard` で収束します（Nextcloud／Navidrome が未同居の間はタイマーも止める）。

```sh
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/music-tools.yml \
  -e music_tools_services=picard -e music_tools_sync_enabled=false
```

手動配備で作られた `storage/picard` の設定データはそのまま残ります。Nextcloud／Navidrome を含む全サービスを配備する段階になったら `-e` を外し、同期タイマーを有効にします。手元で再現する場合は `manage.py up --services picard` のようにサービスを限定できます（`--services` 未指定は従来どおり全サービス）。

## バックアップと復元

```sh
sudo python3 manage.py backup                     # storage/ と配備ファイルを backups/ へ冷間取得
sudo python3 manage.py backup --destination /srv/backups/music-tools
```

`backup` は root で実行します（それ以外は `PermissionError`）。稼働中サービスを `docker compose ps --services --status running` で記録し、`stop --timeout 120` で停止してから、状態ディレクトリ `storage/`（`video`・`state`・`temp`・`convert`・`picard`）を `state.tar`、`compose.yaml`・`compose.lock.yaml`・`.env`・`.env.example`・`manage.py` を `deployment.tar` にまとめ、`manifest.json` を書きます。終了時は元々動いていたサービスだけを再開します。失敗時は `*.incomplete` を残すので、`.incomplete` の無い成功世代だけを使います。

`deployment.tar` の `.env` には共有 Cookie などの実値が入り得ます。保存先は 0700 の非公開領域にし、Git へ入れないでください。

音楽の原本 `${LIBRARY_ROOT}/music`（`YouTube`・`Converted` を含む）は**バックアップに含みません**。原本は別途バックアップしてください（[O03](../../docs/development/O03-restore.md) 等）。

復元時は次の点に注意します。

- **同じ CPU アーキテクチャ**へ戻す（`manifest.json` の `architecture` を確認する）。
- サービスを停止してから展開する。変換・同期・Picard が動いたまま状態を差し替えない。
- 既存の `storage/` へ上書きしない。空のディレクトリへ展開し、`.env` の `LIBRARY_ROOT`・ポート類を合わせてから `manage.py up` で起動する。
- 原本（music）の復元は [O03](../../docs/development/O03-restore.md) の手順に従う。復元後は同期タイマーの二重実行に注意する。

## Picard の使い方

media-01 では `https://picard.apextox.dpdns.org`（Let's Encrypt・Authentik Forward Auth）から開きます。初回は `auth.apextox.dpdns.org` のログインへ移動し、認証後に Picard へ戻ります。

アプリ自身の 5800 は 127.0.0.1 に閉じているため、直接確認する場合は SSH ポート転送も使えます。

```sh
ssh -N -L 5800:127.0.0.1:5800 <user>@media-01
# ブラウザで http://127.0.0.1:5800 を開く
```

1. 対象アルバムを作業コピーとして `/storage`（共有 music）から読み込む。
2. Lookup（クラスタ単位）または Scan（ファイル単位）で照合する。
3. 内容を確認して Save。BCSTM 原本と生成物 `music/Converted/` は編集しない。
4. 保存後は同期タイマー `media-stack-music-sync.timer` が Nextcloud のキャッシュと Navidrome へ反映する。今すぐ反映したい場合は `sudo systemctl start media-stack-music-sync.service` を使う。**media-01 では移行中（W06）のためタイマーは停止している。**

変換・同期と同じファイルを同時に触らないよう、Picard の保存中は変換や同期の手動実行を重ねません。

## 手元での検証

```sh
.venv/bin/python -m unittest tests.test_music_tools_media -v
.venv/bin/ansible-playbook --syntax-check -i 'localhost,' platform/ansible/music-tools.yml
```
