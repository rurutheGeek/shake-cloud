# Nextcloud MCPサーバ（media-01）

Nextcloudのアカウントを持つ全員が、AIエージェント（opencode等）からファイルの
読み書き・MP3タグ編集・圧縮/解凍をできるようにするMCPサーバーです。標準ライブラリ
だけで動きます。専用ユーザーやサービスアカウントは作らず、呼び出し元が送った
`Authorization` ヘッダーをそのままNextcloudへ転送します。権限・共有・クォータ・
ゴミ箱はすべてNextcloud側のACLに従います。

設計の背景・決定事項の一覧は[引き継ぎ文書](../../handoff/nextcloud-mcp.md)を
参照してください。

## 構成

| ファイル | 内容 |
| --- | --- |
| `nextcloud_mcp.py` | MCPサーバー本体。Streamable HTTP（`POST /mcp`、JSON-RPC、セッションなし）を実装する |
| `nextcloud-mcp.service.j2` | systemdユニット。`platform/ansible/media-nextcloud-mcp.yml` が `/etc/systemd/system/nextcloud-mcp.service` へ描画する |

## 受け口

- `POST /mcp` — MCPのJSON-RPCエンドポイント。`initialize`・`ping`・`tools/list`・`tools/call` に対応する。要 `Authorization`（Basicのユーザー資格情報、将来のOIDC Bearerも同じヘッダーで通す想定）
- `GET /healthz` — 200（`{"status": "ok", "read_only": ...}`）

`Authorization` が無いリクエストは401。`initialize` はその場でNextcloudへ
`whoami`（`/ocs/v2.php/cloud/user`）を投げ、資格情報が拒否されれば401を返す
（実際のツール呼び出しを待たずに気付けるようにするため）。

## ツール

読み取り: `nextcloud_whoami`・`nextcloud_list_files`・`nextcloud_file_info`・
`nextcloud_read_file`・`nextcloud_search_files`・`nextcloud_read_music_tags`・
`nextcloud_search_musicbrainz`・`nextcloud_list_archive`

書き込み: `nextcloud_write_file`・`nextcloud_create_folder`・`nextcloud_move_file`・
`nextcloud_copy_file`・`nextcloud_delete_file`・`nextcloud_write_music_tags`・
`nextcloud_create_zip`・`nextcloud_extract_archive`

各ツールの入出力は `tools/list` のJSON Schemaが正本です。破壊的なツールには
`annotations.destructiveHint: true` が付きます。`NEXTCLOUD_MCP_READ_ONLY=1` を
設定すると書き込み系ツールが `tools/list` から消え、呼んでも拒否されます。

## 仕組み

1. ファイル操作はすべてNextcloud WebDAV（`/remote.php/dav/files/<user>/`）を
   呼び出し元の資格情報で実行します。一覧・情報取得はPROPFIND、読み書きは
   GET/PUT、改名・移動はMOVE（`Destination`ヘッダー。fileidが維持されるため
   共有リンクが切れません）、削除はDELETE（Nextcloudのゴミ箱へ入ります）。
2. MP3タグの読み書きは自前でmutagenを叩かず、既存の
   [tag-api](../music-tools/README.md)（`127.0.0.1:5810`）へブリッジします。
   書き込み前にWebDAV PROPFINDで呼び出し元がそのファイルを書けることを確認して
   から、共有トークンでtag-apiを呼びます。対象は `/music` 配下の `.mp3` だけ。
3. 圧縮・解凍は `zipfile`/`tarfile` で行い、入出力はWebDAV経由です。展開先は
   `NEXTCLOUD_MCP_TMP`（既定 `/var/tmp/nextcloud-mcp`）に一時ダウンロードし、
   ファイル数・展開後の合計サイズ・パス脱出（`..`・絶対パス）・シンボリック
   リンクを検査してから書き戻します。
4. `/music/Converted` 配下は変換原本のため、書き込み系ツールすべてから拒否
   されます（読み取りは可能）。

## 設定（systemd EnvironmentFile）

`platform/ansible/media-nextcloud-mcp.yml` が `/opt/nextcloud-mcp/nextcloud-mcp.env`
（モード0400）へ書きます。値の一覧はスクリプト冒頭のdocstringが正本です。
主なもの:

| 変数 | 既定 | 内容 |
| --- | --- | --- |
| `NEXTCLOUD_MCP_PORT` | 5811 | 待受ポート（5810=tag-api、5820=khinsiderと衝突しない） |
| `NEXTCLOUD_MCP_BIND` | 127.0.0.1 | LANへは出さない。外部からは`nextcloud-mcp`のDNS+Caddy経由 |
| `NEXTCLOUD_MCP_BASE_URL` | http://127.0.0.1:8080 | Nextcloud本体 |
| `NEXTCLOUD_MCP_TAG_API_URL` | http://127.0.0.1:5810 | tag-apiのURL |
| `NEXTCLOUD_MCP_TAG_API_TOKEN` | (空) | tag-apiの共有トークン。`platform/sops/music-tags.sops.yaml` が正本 |
| `NEXTCLOUD_MCP_TMP` | /var/tmp/nextcloud-mcp | 圧縮/解凍の作業領域（ディスク。tmpfsではない） |
| `NEXTCLOUD_MCP_READ_ONLY` | 0 | 1で書き込み系ツールを隠す・拒否する |
| `NEXTCLOUD_MCP_MAX_*` | — | 読み取り/書き込み/展開/zipの上限バイト数・ファイル数（zip爆弾対策） |

サーバー自身はNextcloudの利用者資格情報を保存・ログしません
（メモリ上でも保持するのはリクエスト処理中だけ）。

## 配備と確認

`platform/ansible/media-nextcloud-mcp.yml` が本体・環境ファイル・unitを配備し、
`/healthz` の200を待ってから完了します。

```bash
# 構文チェック（実機なし）
ansible-playbook --syntax-check -i localhost, platform/ansible/media-nextcloud-mcp.yml

# 配備
ansible-playbook -i <inventory> platform/ansible/media-nextcloud-mcp.yml

# ヘルスチェック
curl -s http://127.0.0.1:5811/healthz

# 疎通確認（実機のアプリパスワードで）
curl -s -u '<user>:<アプリパスワード>' -X POST http://127.0.0.1:5811/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

## テスト

`tests/test_nextcloud_mcp.py` が純関数（パス正規化・アーカイブの安全性検査・
書き込み禁止パス）・ツールハンドラ（インメモリの疑似Nextcloudクライアント）・
JSON-RPCディスパッチ・実ソケットでのHTTP往復（疑似Nextcloudサーバー相手）・
Ansible配備の配線を検査します。

```bash
python3 -m unittest discover -s tests -p 'test_nextcloud_mcp.py'
```

## 未確認（実機で必ず確かめること）

この環境はOIDCログイン（`user_oidc`）です。Settings → Security でアプリパス
ワードを作れるか、WebDAV/OCSでBasic認証が通るかを実機で確認してください。
通らない場合はOIDCアクセストークンをBearerで渡す方式へ切り替えます（設計は
「Authorizationを転送するだけ」なので変更は小さい想定です）。opencodeへの
登録方法・利用者向けの使い方は
[利用者向けガイド](../../docs/services/nextcloud-agent.md)を参照してください。
