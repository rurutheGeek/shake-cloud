# Nextcloud MCPサーバ（media-01）

Nextcloudのアカウントを持つ全員が、AIエージェント（opencode等）からファイルの
読み書き・MP3タグ編集・圧縮/解凍・カレンダー予定の一覧/追加をできるようにする
MCPサーバーです。標準ライブラリだけで動きます。

**実装の正本は公開リポジトリ
[`rurutheGeek/nextcloud-mcp`](https://github.com/rurutheGeek/nextcloud-mcp)**
に移しました（2026-09-26）。このディレクトリに残るのは配備用のsystemdユニットだけです。

- 使い方・設計・全ツール・全環境変数: 上記リポジトリのREADME
- 配備: `platform/ansible/media-nextcloud-mcp.yml` が
  `nextcloud_mcp_version` / `nextcloud_mcp_sha256`（`group_vars/media.yml`）で
  固定したGitHub Releaseの `nextcloud_mcp.py` を `/opt/nextcloud-mcp/` へ取得し、
  `nextcloud-mcp.service.j2` を設置する
- バージョンを上げるとき: リポジトリでリリースを作り、
  `group_vars/media.yml` の `nextcloud_mcp_version` と `nextcloud_mcp_sha256` を更新して
  プレイを再実行する
- テスト: 本体のテストは公開リポジトリ側。ここでは
  `tests/test_nextcloud_mcp.py` が固定バージョン・取得・ユニット・playbook構文を守る
