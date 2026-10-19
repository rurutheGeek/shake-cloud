# Nextcloud MCPサーバ（media-01）

Nextcloudのアカウントを持つ全員が、AIエージェント（opencode等）からファイルの
読み書き・MP3タグ編集・圧縮/解凍・カレンダー予定の一覧/追加をできるようにする
MCPサーバーです。標準ライブラリだけで動きます。

**実装の正本は公開リポジトリ
[`rurutheGeek/nextcloud-mcp`](https://github.com/rurutheGeek/nextcloud-mcp)**
に移しました（2026-09-26）。このディレクトリに残るのは配備用のsystemdユニットと、
NextcloudへOAuth2クライアントを冪等に登録する `oauth_client.py` だけです。

- 使い方・設計・全ツール・全環境変数: 上記リポジトリのREADME
- 配備: `platform/ansible/media-nextcloud-mcp.yml` が
  `nextcloud_mcp_version` と各 `_sha256`（`group_vars/media.yml`）で固定した
  GitHub Releaseの `nextcloud_mcp.py`・`nextcloud_mcp_oauth.py`・`requirements-oauth.txt`
  を `/opt/nextcloud-mcp/` へ取得し、依存を `/opt/nextcloud-mcp/venv` に入れ、
  OAuth2クライアントを登録して `nextcloud-mcp.service.j2` を設置する
- バージョンを上げるとき: リポジトリでリリースを作り、
  `group_vars/media.yml` の `nextcloud_mcp_version` と3つの `_sha256` を更新して
  プレイを再実行する
- テスト: 本体のテストは公開リポジトリ側。ここでは
  `tests/test_nextcloud_mcp.py` が固定バージョン・取得・ユニット・playbook構文を守る
