---
title: Nextcloud MCPサーバ（管理者向け）
updated: 2026-10-24
section: 運用手順
audience: 管理者
tags:
  - ops
  - nextcloud
---

# Nextcloud MCPサーバ（管理者向け）

> **更新日** 2026-10-24 ・ **区分** 運用手順 ・ **読む人** 管理者

状態: **media-01へ配備済み・稼働中（v1.3.0、OAuthとBasicの両方を受ける`both`）**。`https://nextcloud-mcp.apextox.dpdns.org/healthz`が200、Let's Encrypt証明書取得済み。tarakoserverのPrometheusで`probe_success==1`も確認済み。Deckの読み取り・カード作成・コメント・移動は実データ（ホームラボ）で確認済み。タグ編集〜Navidrome反映は未確認（[#192](https://github.com/rurutheGeek/shake-cloud/issues/192)が正本）。

AIエージェント（opencode等）にNextcloudのファイル操作・MP3タグ編集・圧縮/解凍・
カレンダー予定の一覧/追加・Deckのボード/カード/コメントの読み書きを渡すMCPサーバーです。media-01に常設し、専用ユーザーや
サービスアカウントは作りません。詳細は[stacks/nextcloud-mcp/README.md](https://github.com/rurutheGeek/shake-cloud/blob/main/stacks/nextcloud-mcp/README.md)、
利用者向けは[Nextcloudファイルエージェントの使い方](../services/nextcloud-agent.md)。

## 正本

| 対象 | 場所 |
| --- | --- |
| 本体 | 公開リポジトリ [`rurutheGeek/nextcloud-mcp`](https://github.com/rurutheGeek/nextcloud-mcp)（`group_vars/media.yml` の `nextcloud_mcp_version` と各 `_sha256` で固定し、プレイがGitHub Releaseから `nextcloud_mcp.py`・`nextcloud_mcp_oauth.py`・`requirements-oauth.txt` を取得。依存は `/opt/nextcloud-mcp/venv`） |
| 認証方式 | `group_vars/media.yml` の `nextcloud_mcp_auth`（`both`） |
| NextcloudのOAuth2クライアント | `stacks/nextcloud-mcp/oauth_client.py`（プレイが冪等に登録。秘密値はmedia-01の `/opt/nextcloud-mcp/oauth-client.json` だけ） |
| OAuthの状態 | media-01の `/var/lib/nextcloud-mcp`（クライアント登録と暗号化したNextcloudトークン） |
| systemdユニット | `stacks/nextcloud-mcp/nextcloud-mcp.service.j2` |
| 配備 | `platform/ansible/media-nextcloud-mcp.yml` |
| DNS/Caddy | `platform/terraform/dns.yaml`（`nextcloud-mcp`レコード）・`tls_proxy`ロール |
| 監視 | `stacks/monitoring/prometheus/blackbox-targets.yml`（`/healthz`をhttps probe） |
| tag-apiの共有トークン | `platform/sops/music-tags.sops.yaml`（[W06](https://github.com/rurutheGeek/shake-cloud/issues/183)と共用） |
| テスト | `tests/test_nextcloud_mcp.py`・`tests/test_tls_proxy.py`・`tests/test_monitoring_stack.py` |

## 配備

```bash
# 構文チェック（実機なし）
ansible-playbook --syntax-check -i localhost, platform/ansible/media-nextcloud-mcp.yml

# 配備（tag-apiが既に動いていること。W06参照）
ansible-playbook -i <inventory> platform/ansible/media-nextcloud-mcp.yml

# DNS/Caddyの反映（新レコード追加後は必須）
ansible-playbook -i <inventory> media-tls.yml   # media-01のtls_proxyロールを再適用
```

`/etc/systemd/system/nextcloud-mcp.service`は`ProtectSystem=strict`で、
`ReadWritePaths`の`/var/tmp/nextcloud-mcp`と`/var/lib/nextcloud-mcp`だけ書き込み可能です。展開する
アーカイブが大きい場合はこのディレクトリのディスク空き容量に注意してください
（tmpfsではなく実ディスク）。

## 資格情報

- **OAuth（推奨）**: MCPクライアントはMCP仕様のOAuth 2.1でログインします。
  サーバーがNextcloud標準のOAuth2アプリへ利用者を送り、受け取った利用者の
  Nextcloudトークンを`/var/lib/nextcloud-mcp`へ暗号化して保存します。以後の
  操作はそのトークンで行うので、ACLは呼び出し元に従います。暗号鍵はOAuth2
  クライアントの秘密値から作るので、`oauth-client.json`を消して登録し直すと
  全員が再ログインになります。
- **Basic（移行中のため残す）**: 呼び出し元が送った`Authorization`ヘッダーを
  Nextcloudへそのまま転送し、何も保存しません。
- `.env`（`/opt/nextcloud-mcp/nextcloud-mcp.env`、モード0400）に入るのは
  tag-apiの共有トークン（`NEXTCLOUD_MCP_TAG_API_TOKEN`）だけです。値は
  `platform/sops/music-tags.sops.yaml`が正本（[W06](https://github.com/rurutheGeek/shake-cloud/issues/183)と共用、
  ローテーションは両方に影響します）。
- OIDCログイン（`user_oidc`）のNextcloudでも、アプリパスワードのBasicと
  OAuth2アプリのトークンの両方が通ることを実機で確認済みです。

## 監視・ヘルスチェック

```bash
curl -s http://127.0.0.1:5811/healthz
journalctl -u nextcloud-mcp -f
```

blackboxが`https://nextcloud-mcp.apextox.dpdns.org/healthz`をprobeします。
`/healthz`は認証不要で、Nextcloud本体・tag-apiの疎通は見ません（`initialize`
呼び出し時に実際の資格情報でwhoamiを叩いて初めて確認できます）。

## 書き込みの安全策

- `/music/Converted`配下（変換原本）は全ての書き込み系ツールから拒否されます。
- 圧縮解凍はファイル数・展開後の合計サイズ・パス脱出（`..`・絶対パス）・
  シンボリックリンクを検査してから書き戻します（`NEXTCLOUD_MCP_MAX_EXTRACT_*`）。
- 削除はNextcloudのゴミ箱へ入ります（完全削除はNextcloud側の操作）。
- `NEXTCLOUD_MCP_READ_ONLY=1`にすると書き込み系ツール全体を`tools/list`から
  隠し、呼んでも拒否します。読み取りだけ配りたい場合に使えます。

## カレンダー（CalDAV）

- ツールは `nextcloud_list_calendars`・`nextcloud_list_events`・
  `nextcloud_create_event`。Nextcloudのカレンダーは `nextcloud_apps`
  （`group_vars/media.yml`）の `calendar` で有効にする。未有効だとcapabilitiesに
  `calendar`が無く、3ツールは「Calendarアプリが有効ではない」と明示エラーを返す
  （汎用の通信失敗とは区別できる）。
- 呼び出し元自身のCalDAVコレクションと共有権限で動く。読み取り専用の共有
  カレンダー・VTODO専用カレンダーへの予定追加は拒否する。
- `nextcloud_create_event` は既存のbusy予定と重なる場合、競合を列挙して拒否する
  （`allow_overlap=true`で強制追加）。繰り返し予定は `DAILY`/`WEEKLY`/`MONTHLY`/
  `YEARLY`（`COUNT`/`UNTIL`/`BYDAY`/`BYMONTHDAY`/`BYMONTH`/`EXDATE`・上書き）を
  展開し、`TRANSP:TRANSPARENT`と`STATUS:CANCELLED`はbusy扱いしない。
- タイムゾーン: オフセット付きの入力はUTCで保存し、表示は
  `NEXTCLOUD_MCP_TIMEZONE`（既定はホストのローカル＝media-01のタイムゾーン）へ
  変換する。オフセット無しの入力と終日予定も同じ既定を使う。
- 予定の変更・削除ツールはまだ無い。必要ならNextcloudのカレンダー画面で行う。

## Deck

- Deckのツールは `nextcloud_deck_boards`・`nextcloud_deck_cards`・
  `nextcloud_deck_create_card`・`nextcloud_deck_update_card`・
  `nextcloud_deck_move_card`・`nextcloud_deck_comments`・
  `nextcloud_deck_add_comment` の7つ。ボードと列（スタック）はIDのほか名前でも
  指定でき、カードの説明は16 KiBまで返す（超えた分は `description_truncated`）。
- 呼び出し元のNextcloud権限で動く。読み取り専用の共有ボードでは書き込み系が
  Nextcloud側で403になる。コメント追加は説明文を書き換えないので、人が書いた
  本文を壊さずにissueのURLを残せる。
- Deckアプリが有効でない場合（capabilitiesに`deck`が無い場合）は、7ツールは
  「Deckアプリが有効ではない」と明示エラーを返す（`group_vars/media.yml`の
  `nextcloud_apps`に`deck`を入れて配備する。現在はmedia-01で有効）。
- ボード「ホームラボ」の共有はグループ`homelab`で行う（[Nextcloud](nextcloud.md)）。

## トラブルシュート

| 症状 | 確認 |
| --- | --- |
| `/mcp`が401を返す | OAuthなら`opencode mcp auth nextcloud`で再ログイン。BasicならアプリパスワードがNextcloudで失効していないか |
| OAuthのログインが終わらない | opencodeを動かす機械にブラウザーが無い（戻り先は`127.0.0.1:19876`）。その機械はアプリパスワードのBasicで使う（dev-02はこれ） |
| `initialize`だけ401 | Nextcloud側で資格情報が拒否されている（サーバーログに`initialize: Nextcloudが応答しません`と出ない場合はここ） |
| MP3タグ編集が失敗する | tag-api（`127.0.0.1:5810`）が起動しているか、`NEXTCLOUD_MCP_TAG_API_TOKEN`が空でないか（[W06](https://github.com/rurutheGeek/shake-cloud/issues/183)） |
| zip展開が途中で失敗する | `NEXTCLOUD_MCP_MAX_EXTRACT_FILES`/`_BYTES`の上限に触れていないか。大物はNextcloud UI（files_zip等）へ誘導する |
| カレンダーで「Calendar app is not available」 | NextcloudでCalendarアプリが有効か（capabilitiesの`calendar`）。`group_vars/media.yml`の`nextcloud_apps`に`calendar`がある（`media-nextcloud.yml`が導入する） |
| 予定が意図した時刻とずれて見える | `NEXTCLOUD_MCP_TIMEZONE`（既定はmedia-01のタイムゾーン）を確認。オフセット無しの入力・終日予定・一覧表示がこの値を基準にする |

## テスト

```bash
python3 -m unittest discover -s tests -p 'test_nextcloud_mcp.py'
python3 -m unittest discover -s tests -p 'test_tls_proxy.py'
python3 -m unittest discover -s tests -p 'test_monitoring_stack.py'
```

本体の単体テスト（疑似Nextcloud/tag-apiとの実ソケットHTTP往復を含む）は公開リポジトリ側にあります。
ここの`test_nextcloud_mcp.py`は、固定バージョン・取得・systemdユニット・playbook構文を守ります。
