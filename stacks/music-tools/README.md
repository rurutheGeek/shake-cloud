# music-tools の配備とタグ編集

media-01 の音楽導線（MeTube 取込 → Nextcloud 共有 music → タグ編集 → Navidrome 表示）を担うスタックです。仕様・進捗の正本は [W06](../../docs/development/W06-music-tools.md)、タグ編集の使い方は [Nextcloudの使い方](../../docs/services/nextcloud-guide.md)、Picard廃止の経緯は [D05](../../docs/development/D05-picard.md) です。

状態: **media-01 で MeTube・変換・タグAPIが稼働中（2026-09-13）。タグAPIはNextcloudの「タグを編集」が使う。同期タイマーは停止中（W06の残り）**。共有 Cookie の実物は未登録です。

## 構成

| サービス | 内容 | 入口 |
| --- | --- | --- |
| metube | 音源・動画の取込 | `127.0.0.1:${METUBE_PORT:-8081}` |
| convert | BCSTM 変換ワーカー | なし（常駐） |
| tag-api | タグの読み書きとMusicBrainz検索（Nextcloudの「タグを編集」用、[tag_api.py](tag_api.py)） | `0.0.0.0:${TAG_API_PORT:-5810}`（トークン認証） |
| tagger | 手動タグ付け（profile: tools） | なし |

共有 music の実体は `${LIBRARY_ROOT}/music`。タグAPIはそこを `/music` へ読み書き（rw）でマウントし、バックアップは `storage/tags`（コンテナ内 `/state/tag-backups`）へ保存します。BCSTM 原本と `music/Converted/` は直接編集しません。

YouTubeのCookieは `storage/state/cookies.txt`（0600）へ置き、compose の `YTDL_OPTIONS` が `cookiefile` として常に参照します（再起動後も有効）。MeTubeの **Upload Cookies** でも同じ場所へ保存されます。通常の公開動画はCookieなしで取得できます。

`.env.example` は秘密値を含まない参照用です。実値の `.env` は配備先で 0600 になります。共有 Cookie などの実値は Git に置かず、対象ホストへ配ります。

## Ansible での配備（正本）

```sh
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/music-tools.yml
```

既定では `metube`・`convert`・`tag-api` の全サービスを配備し、同期タイマーを有効化します。media-01 では W06 の切替が済むまで、タイマーを止めるため `-e music_tools_sync_enabled=false` を付けて再適用します。

一部のサービスだけを段階配備する場合（例: タグAPIだけ）:

```sh
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/music-tools.yml \
  -e music_tools_services=tag-api -e music_tools_sync_enabled=false
```

ポートや TZ を変える場合はホストの `.env` を直接編集せず、`-e music_tools_tag_port=5811` のように playbook 変数で渡します（playbook が `.env` を生成し直すためです）。

## Picard の撤去（2026-09-13）

タグ編集をNextcloudの `shake_tags` へ統合したため、compose・lock・検証から Picard を外しました。`manage.py up` は `--remove-orphans` 付きなので、再配備で picard コンテナは削除されます。設定データ `storage/picard` は残してあります。戻す場合は git で compose/lock/playbook を戻してください。

## バックアップと復元

```sh
sudo python3 manage.py backup                     # storage/ と配備ファイルを backups/ へ冷間取得
sudo python3 manage.py backup --destination /srv/backups/music-tools
```

`backup` は root で実行します（それ以外は `PermissionError`）。稼働中サービスを `docker compose ps --services --status running` で記録し、`stop --timeout 120` で停止してから、状態ディレクトリ `storage/`（`video`・`state`・`temp`・`convert`・`tags`）を `state.tar`、`compose.yaml`・`compose.lock.yaml`・`.env`・`.env.example`・`manage.py` を `deployment.tar` にまとめ、`manifest.json` を書きます。終了時は元々動いていたサービスだけを再開します。失敗時は `*.incomplete` を残すので、`.incomplete` の無い成功世代だけを使います。

`deployment.tar` の `.env` には共有 Cookie などの実値が入り得ます。保存先は 0700 の非公開領域にし、Git へ入れないでください。

音楽の原本 `${LIBRARY_ROOT}/music`（`YouTube`・`Converted` を含む）は**バックアップに含みません**。原本は別途バックアップしてください（[O03](../../docs/development/O03-restore.md) 等）。

復元時は次の点に注意します。

- **同じ CPU アーキテクチャ**へ戻す（`manifest.json` の `architecture` を確認する）。
- サービスを停止してから展開する。変換・タグAPI・同期が動いたまま状態を差し替えない。
- 既存の `storage/` へ上書きしない。空のディレクトリへ展開し、`.env` の `LIBRARY_ROOT`・ポート類を合わせてから `manage.py up` で起動する。
- 原本（music）の復元は [O03](../../docs/development/O03-restore.md) の手順に従う。復元後は同期タイマーの二重実行に注意する。

## タグ編集

通常はNextcloudの `music` にあるMP3の **…** → **タグを編集** を使います（[Nextcloudの使い方](../../docs/services/nextcloud-guide.md)）。MusicBrainz検索つきで、変更前のタグは `storage/tags/tag-backups/` に保存されます。Navidromeへの反映は通常1時間以内です。

## ライブラリ一括整理（organize.py）

`music/` のMP3をまとめて `アーティスト/アルバム/NN - 曲名.mp3` へ整理し、タグを書き、アルバムフォルダへ `cover.jpg` を置きます。`Converted/` とMP3以外（WAV・BCSTMなど）には触れません。plan（調査のみ）と apply（適用）を分けており、適用前に差分を確認できます。

```bash
cd /opt/media-stack/music-tools
# 1) 計画を作る（/music は変更しない。MusicBrainz照合とカバー収集）
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  run --rm --entrypoint python3 tagger /tools/organize.py plan \
  --aliases /tools/organize-aliases.json
# 2) storage/convert/organize/report.md と manifest.json を確認する
# 3) 適用（ID3バックアップと移動ジャーナルを残す）
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  run --rm --entrypoint python3 tagger /tools/organize.py apply \
  --manifest /state/organize/manifest.json --cleanup
# 4) 取り消しはジャーナルから（適用時と逆の操作をする）
sudo docker compose --env-file .env -f compose.yaml -f compose.lock.yaml \
  run --rm --entrypoint python3 tagger /tools/organize.py undo \
  --journal /state/organize/journal-<日時>.json
```

- 判定順: MusicBrainzリリース一致 → MusicBrainz録音一致 → 既存タグ/ファイル名。既存タグは可能な限り保持します。
- アルバムが無い曲は `アーティスト/Singles/` へ、アーティストも無い曲は移動せず `report.md` の「未解決」へ出します。
- カバーは Cover Art Archive → iTunes(JP) → Deezer → 既存のFolder.jpg の順。誤りを避けるため類似度しきい値未満は付けず、未取得として記録します。
- MusicBrainzで見つからない日本語ゲームBGMは `organize-aliases.json` の `albums`（アルバムタグ）/ `folders`（フォルダ相対パス）に `album`・`albumartist`・`genre`・`mb_release`・`title_prefix`・`itunes_term` を書き、再planすると反映されます。
- 同一曲がライブ版・コンピ盤など別アルバムへ解決されることがあります。適用前に `report.md` を確認してください。
- 状態は `storage/convert/organize/`（`cache/`・`covers/`・`manifest.json`・`report.md`・`journal-*.json`）、タグのバックアップは `storage/convert/tag-backups/` に置きます。
- 失敗時は plan をやり直してください。`cache/` が効くため2回目以降は速くなります。

## 手元での検証

```sh
.venv/bin/python -m unittest tests.test_music_tools_media -v
.venv/bin/ansible-playbook --syntax-check -i 'localhost,' platform/ansible/music-tools.yml
```
