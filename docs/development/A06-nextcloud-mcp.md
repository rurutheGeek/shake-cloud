---
title: A06 NextcloudファイルAIエージェント（nextcloud-mcp）
updated: 2026-10-02
section: 開発計画
audience: 開発者
tags:
  - plan
  - nextcloud
---

# A06 NextcloudファイルAIエージェント（nextcloud-mcp）

> **更新日** 2026-10-02 ・ **区分** 開発計画 ・ **読む人** 開発者

これは開発計画であり配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **media-01へ実機配備済み・稼働中（v1.1.0）。`https://nextcloud-mcp.apextox.dpdns.org/healthz`が200、Let's Encrypt証明書取得済み。monitor-01のPrometheusでも`probe_success==1`を確認済み。残るのは人間のNextcloudアカウントでの実データ確認（アプリパスワード・タグ編集反映・大きいzipの解凍）だけ**。アプリパスワード（Basic）でのログインは実機で確認済み（2026-09-28）。

2026-09-28に `v1.1.0` でカレンダー3ツールを追加した。要件を「ファイルの読み書き・圧縮解凍・タグ編集」から**CalDAVカレンダーの予定追加**へ広げ、AIが自然文から整えた予定を、既存の予定とかぶらない場合だけ追加できるようにした（かぶりは競合を列挙して拒否し、`allow_overlap=true`で強制）。繰り返し予定の展開・読み取り専用/VTODOカレンダーの拒否・Calendarアプリ未有効時の明示エラー・`NEXTCLOUD_MCP_TIMEZONE` を含む。予定の更新・削除は次版以降。

GeminiのGoogle Drive連携のように、AIエージェント（opencode等）がNextcloudの
ファイルを「ネイティブに」読み書きできるようにする。要求は3つ：ファイルの
読み書き・改名・圧縮解凍、既存のMP3タグ編集（[W06](W06-music-tools.md)の
tag-api）と同じ結果、そして専用ユーザーを作らず**Nextcloudのアカウントを持つ
全員**が使えること。設計と決定事項の一覧は下の[設計と決定事項](#design-decisions)。

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

<a id="design-decisions"></a>

## 設計と決定事項

実装を公開リポジトリへ切り出す前に決めた設計の要点です。実装の詳細・全ツール・全環境変数は[公開リポジトリのREADME](https://github.com/rurutheGeek/nextcloud-mcp)、配備と運用は[管理者向け](../operations/nextcloud-mcp.md)を見てください。

| 論点 | 決定 | 理由 |
| --- | --- | --- |
| 実装 | **自作の`nextcloud-mcp`**（標準ライブラリのみのPython1ファイル） | OSSの[cbcoutinho/nextcloud-mcp-server](https://github.com/cbcoutinho/nextcloud-mcp-server)はWebDAV CRUDはあるがMP3タグ・解凍が無く、CVE-2026-55640（0.117.2未満）がある。公式Context AgentはAppAPI/HaRPの導入が要り、タグ・解凍ツールが無い |
| 実行場所 | **media-01の常設HTTPサービス**（systemd） | tag-api（`127.0.0.1:5810`）はmedia-01のSGでLAN非公開（SGは22/80/443/53317のみ）。解凍・圧縮はサーバー側が速い。各利用者にバイナリを配らずに済む。配備規約は`tag-api`・`localsend-send`と同じ |
| 認証 | **呼び出し元の`Authorization`をそのままNextcloudへ転送**。Basic（`user:アプリパスワード`）を推奨し、将来のOIDC Bearerも同じ経路 | 共有資格情報を持たず、NextcloudのACL・共有・クォータがそのまま効く。「アカウントがあれば誰でも」を満たす |
| 資格情報の保存 | **サーバーは保存しない**（メモリにも残さない）。tag-apiの共有トークンだけSOPSから`.env`（0400）へ | 漏えい面を増やさない |
| HTTPの入口 | `dns.yaml`の`nextcloud-mcp`レコード（host: media-01、upstream: `127.0.0.1:5811`、`auth: true`を**付けない**） | `navidrome-api`と同じ「TLSあり・SSOなし・アプリ自前認証」。SGの追加開放は不要（443済み）。5811は5810（tag-api）・5820（khinsider）と衝突しない |
| ファイル操作 | すべて**Nextcloud WebDAV**（`/remote.php/dav/files/<user>/`）を呼び出し元の資格情報で実行 | ACL・共有・クォータ・ゴミ箱がそのまま効き、`occ files:scan`が要らない |
| 改名・移動 | WebDAVの`MOVE`（`Destination`ヘッダ） | **fileidが維持される**ので共有リンク・添付が切れない。削除→再アップロードは切れる |
| 圧縮・解凍 | サーバー内で`zipfile`/`tarfile`を実行し、入出力はWebDAV経由 | 公式`files_zip`（Zipper）はOCS APIで圧縮はできるが解凍APIが無い。将来の高速化候補として記録（`POST /ocs/v2.php/apps/files_zip/api/v1/zip`、`fileIds`＋`target`） |
| MP3タグ | 既存の**tag-api**（`GET /tags`・`POST /tags`・`GET /musicbrainz`）へブリッジ | ID3バックアップ・対応フィールド限定・`.mp3`限定・MusicBrainz検索が既にある。MCPからmutagenを直接叩かない |
| タグ編集の権限 | 先にWebDAV PROPFINDで**呼び出し元が書ける**ことを確認してから、内部トークンでtag-apiを呼ぶ | tag-apiは共有トークンなので、利用者の権限確認をMCP側で担保する。対象は`/music`配下の`.mp3`だけ |
| 反映 | タグ・ファイル操作のNextcloud/Navidrome反映は既存の**音楽同期タイマー**（`media-stack-music-sync.timer`、1時間ごと）に任せる | 即時反映が要るようならrescanツールを足す |
| MCPの形 | **Streamable HTTP**（`POST /mcp`、JSON-RPCを単一JSONで返す、セッションなし）。`initialize`・`ping`・`tools/list`・`tools/call`を実装 | opencodeの`type: "remote"`で使える。公式SDKを入れない分、実装は小さく保つ |
| 書き込みの安全 | 破壊的ツールに`destructiveHint`、削除はNextcloudのゴミ箱、解凍は件数・展開サイズ・パス脱出・シンボリックリンクのガード、操作ログをjournaldへ | 生成AIに広い権限を渡すため |
| 一時ファイル | `/var/tmp/nextcloud-mcp`（実ディスク）。systemdは`ProtectSystem=strict`＋`ReadWritePaths=`でそこだけ許可 | `/tmp`はtmpfsでGB級アーカイブに不適 |
| 書き込み禁止パス | 書き込み系は`NEXTCLOUD_MCP_WRITE_DENY`のパスを拒否する（実機では`/music/Converted`が拒否される。[管理者向け](../operations/nextcloud-mcp.md)参照）。設計時は、Vaultwardenの保管庫・Nextcloudの`Converted`・`storage/`もMCPの対象外にする方針だった | 変換原本・秘密を持つ領域をAIに触らせない。**実際に拒否される範囲は実機の設定値で確かめること** |

### 採用しなかった案

- **OSSのcbcoutinho/nextcloud-mcp-server**: 高機能だがMP3タグ・解凍が無い。CVE未修正版の事故を避けるため見送り（使うなら0.117.2以上の固定が必須）。
- **公式Context Agent（ExApp）**: AppAPI/HaRPの配備が必要で、欲しいタグ・解凍ツールが無い。Nextcloud内のチャット（AssistantとContext Chat）が欲しくなったら別途。
- **利用者ごとのstdio MCP**: 各端末にビルド・配布が要り、tag-apiがLAN非公開のためタグ編集が届かない。
- **files_zip（Zipper）**: 解凍はAPI付きのアプリが無い。全面自作に統一した。

### 実機配備で見つけた教訓

- **systemdの`PrivateTmp=true`は`ReadWritePaths=/var/tmp/...`と両立しない。** `/var/tmp`ごと専用の空tmpfsに差し替わり、`status=226/NAMESPACE`で起動に失敗する。`systemd-analyze verify`・Ansibleの`--check`・単体テストのどれも検出できず、実機起動で初めて表面化した。ユニット（`stacks/nextcloud-mcp/nextcloud-mcp.service.j2`）は`PrivateTmp`を付けない。
- **DNSレコードを足すと、`tests/test_tls_proxy.py`（Caddyのサイト数）と`tests/test_monitoring_stack.py`（blackboxが`dns.yaml`の全サービスレコードを網羅するか）に波及する。** `blackbox-targets.yml`への追加を忘れない。
- アプリパスワード・OIDCトークンを会話・コミット・メモに残さない。

## 実データでの確認項目（未了）

人間のNextcloudアカウントが要るため、実装側では確認できていない項目です。**確認が済むまで動作確認済みと書かない。** 済んだら[配備台帳](../operations/handover.md)へ記録する。

- アプリパスワードでBasic認証が通り`initialize`が成功すること（2026-09-28にログインは確認済み）。通らない環境ではOIDCアクセストークンをBearerで渡す方式（`user_oidc`の`oidc_provider_bearer_validation`）へ切り替える。
- 代表的なツール（一覧・読み書き・タグ・zip作成/展開）を実データで呼ぶ。tag-apiは`127.0.0.1:5810`への到達（無認証で401）までは確認済みで、**トークン付きの実呼び出しは未確認**。
- 削除→ゴミ箱、`MOVE`でのfileid維持、タグ編集→音楽同期タイマー→Navidrome反映。
- 大きいzipの解凍がopencodeのツールタイムアウトに収まること。収まらなければ上限を下げ、大物はNextcloudのUI（files_zip等）へ誘導する。

## 依存と並列作業

- 開発開始: なし。本体・テストはdev VMだけで完結する（実機Nextcloudに触れない）。
- 配備・切替: [W03](W03-nextcloud.md)（Nextcloud本体）・[W06](W06-music-tools.md)（tag-api）が先に稼働している必要がある。DNS/Caddyの反映は`tls_proxy`ロールの再適用。
- **2026-09-26: 実装を公開リポジトリ [`rurutheGeek/nextcloud-mcp`](https://github.com/rurutheGeek/nextcloud-mcp) へ切り出し、`v1.0.0` をリリース。**2026-09-26に外部レビューを受けて `v1.0.1` へ更新（tools/call前のwhoami必須化、タグreadのstat、write-denyの祖先拒否と展開メンバー検査、max_bytesの負値/非整数拒否、アーカイブの事前サイズ検査、Origin検証、-32600応答。テスト139件）**。media-01へはプレイがリリース資産（`nextcloud_mcp.py`、sha256固定）を取得する方式へ移行。** パス設定（`NEXTCLOUD_MCP_MUSIC_ROOT`・`NEXTCLOUD_MCP_WRITE_DENY`）と、tag-api連携のオプション化（URLとトークンの両方が設定されたときだけタグ3ツールを公開）を追加した。単体テストは公開リポジトリ側（103件）。実機は`/healthz`が`version: 1.0.1`・`tag_tools: true`を返し、MCP経由の`whoami`とMusicBrainz検索が成功することを確認。
- 競合調整: media-01の他サービス（Nextcloud・Kavita・Navidrome・MeTube・khinsider・LocalSend）とポート・SGを共有しない。新しいポートをLANへ開けない（Caddy経由のみ）。

## 検証・完了条件

- `python3 -m unittest discover -s tests -p 'test_nextcloud_mcp.py'`・`test_tls_proxy.py`・`test_monitoring_stack.py`が通過する（dev VMで確認済み）。
- `ansible-playbook --syntax-check`が通過する（dev VMで確認済み）。`systemd-analyze verify`でユニットが警告なしであることを確認済み。
- 実機で`/healthz`が200、`initialize`→`tools/list`→代表的なツール（一覧・読み書き・MP3タグ・zip作成/展開）が実データで成功する。
- アプリパスワード（またはOIDCトークン）でのBasic/Bearer認証が実際に通ることを確認する。
- Nextcloudの共有・ACL・クォータ・ゴミ箱が呼び出し元の権限どおりに効くこと、`/music/Converted`配下への書き込みが拒否されることを実機で確認する。
- 実機確認が済むまで、[配備台帳](../operations/handover.md)に配備済み・動作確認済みと書かない。
