---
title: A06 NextcloudファイルAIエージェント（nextcloud-mcp）
updated: 2026-09-26
section: 開発計画
audience: 開発者
tags:
  - plan
  - nextcloud
---

# A06 NextcloudファイルAIエージェント（nextcloud-mcp）

> **更新日** 2026-09-26 ・ **区分** 開発計画 ・ **読む人** 開発者

これは開発計画であり配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **media-01へ実機配備済み・稼働中。`https://nextcloud-mcp.apextox.dpdns.org/healthz`が200、Let's Encrypt証明書取得済み。monitor-01のPrometheusでも`probe_success==1`を確認済み。残るのは人間のNextcloudアカウントでの実データ確認（アプリパスワード・タグ編集反映・大きいzipの解凍）だけ**。

GeminiのGoogle Drive連携のように、AIエージェント（opencode等）がNextcloudの
ファイルを「ネイティブに」読み書きできるようにする。要求は3つ：ファイルの
読み書き・改名・圧縮解凍、既存のMP3タグ編集（[W06](W06-music-tools.md)の
tag-api）と同じ結果、そして専用ユーザーを作らず**Nextcloudのアカウントを持つ
全員**が使えること。設計と決定事項の一覧は`handoff/nextcloud-mcp.md`（引き継ぎ
文書、リポジトリ直下）が正本。

配備先・開発範囲: **media-01。`stacks/nextcloud-mcp/`（標準ライブラリのみの
Python・systemdユニット）を追加し、既存の`tag-api`（`:5810`、W06）へブリッジ
する。専用のAI用VM・コンテナ・独自SDKは使わない**。

## 実装手順

1. ~~MCPサーバー本体（`nextcloud_mcp.py`）・systemdユニット・Ansible配備playbookを実装する。~~ 完了。呼び出し元の`Authorization`をNextcloudへ転送し、資格情報は保存しない。
2. ~~純関数・アーカイブ展開ガード・ツールハンドラ・JSON-RPCディスパッチ・実ソケットでのHTTP往復を`tests/test_nextcloud_mcp.py`で検証する。~~ 完了（84件）。検証中に、未知のツール名・読み取り専用時の書き込み拒否・引数不正の`ToolError`がHTTPハンドラまで無捕捉で伝播しサーバースレッドを落とすバグと、`initialize`時にNextcloud接続不能（`ToolError`）を`NextcloudError`としてしか捕まえず同様に落ちるバグを発見し修正した。
3. ~~`platform/terraform/dns.yaml`に`nextcloud-mcp`レコード（SSOなし・`tls_proxy`のCaddy中継のみ）を追加し、監視の`blackbox-targets.yml`にも登録する。~~ 完了。`tests/test_tls_proxy.py`・`tests/test_monitoring_stack.py`が検査する。
4. ~~`platform/ansible/media-nextcloud-mcp.yml`の実機適用と`tls_proxy`ロールの再適用（DNS-01証明書取得）、`platform/ansible/monitoring.yml`でmonitor-01への監視反映を行う。~~ 完了（2026-09-26）。
5. **未確認: user_oidcユーザーのアプリパスワード。** この環境はOIDCログイン。Settings → Securityでアプリパスワードを作れるか、WebDAV/OCSでBasic認証が通るかを実機で確認する。通らない場合はOIDCアクセストークンをBearer転送へ切り替える（設計変更は小さい想定）。
6. 削除→ゴミ箱、MOVEでのfileid維持、タグ編集→[音楽同期タイマー](W06-music-tools.md)→Navidrome反映、大きいzipの解凍がopencodeのツールタイムアウトに収まるかを実データで確認する。
7. opencode側の登録手順・利用時の注意を利用者向け文書へ、運用手順を管理者向け文書へ記録する（[利用者向け](../services/nextcloud-agent.md)・[管理者向け](../operations/nextcloud-mcp.md)）。

## 依存と並列作業

- 開発開始: なし。本体・テストはdev VMだけで完結する（実機Nextcloudに触れない）。
- 配備・切替: [W03](W03-nextcloud.md)（Nextcloud本体）・[W06](W06-music-tools.md)（tag-api）が先に稼働している必要がある。DNS/Caddyの反映は`tls_proxy`ロールの再適用。
- 競合調整: media-01の他サービス（Nextcloud・Kavita・Navidrome・MeTube・khinsider・LocalSend）とポート・SGを共有しない。新しいポートをLANへ開けない（Caddy経由のみ）。

## 検証・完了条件

- `python3 -m unittest discover -s tests -p 'test_nextcloud_mcp.py'`・`test_tls_proxy.py`・`test_monitoring_stack.py`が通過する（dev VMで確認済み）。
- `ansible-playbook --syntax-check`が通過する（dev VMで確認済み）。`systemd-analyze verify`でユニットが警告なしであることを確認済み。
- 実機で`/healthz`が200、`initialize`→`tools/list`→代表的なツール（一覧・読み書き・MP3タグ・zip作成/展開）が実データで成功する。
- アプリパスワード（またはOIDCトークン）でのBasic/Bearer認証が実際に通ることを確認する。
- Nextcloudの共有・ACL・クォータ・ゴミ箱が呼び出し元の権限どおりに効くこと、`/music/Converted`配下への書き込みが拒否されることを実機で確認する。
- 実機確認が済むまで、[配備台帳](../operations/handover.md)に配備済み・動作確認済みと書かない。
