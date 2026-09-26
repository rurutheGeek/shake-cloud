# NextcloudファイルAIエージェント（nextcloud-mcp）設計引き継ぎ

> **更新日** 2026-09-26 ・ **区分** 設計引き継ぎ ・ **状態** **media-01へ実機配備・DNS/TLS反映・monitor-01の監視反映まで完了して稼働中**。残るのはNextcloudの実データでの動作確認（アプリパスワードでの`initialize`、タグ編集の反映、大きいzipの解凍）だけ

NextcloudのファイルをAIエージェント（opencode等）から**読み書き**できるようにする作業の引き継ぎです。設計と、作成済みファイル・残作業をまとめます。[A06 NextcloudファイルAIエージェント](../docs/development/A06-nextcloud-mcp.md)が開発計画の正本、この文書は設計の経緯です。

## このセッションでの進捗（2026-09-25 続き）

「残り」の1〜6を完了した。

1. **構文・テスト**: `tests/test_nextcloud_mcp.py`（85件、純関数・アーカイブ展開ガード・インメモリ疑似Nextcloudクライアントでのツールハンドラ・JSON-RPCディスパッチ・実ソケットでのHTTP往復・Ansible配線）を作成し全件合格。作成中に本体の実バグを2件発見・修正した（`stacks/nextcloud-mcp/nextcloud_mcp.py`）。
   - `call_tool`が「未知のツール名」「読み取り専用時の書き込み拒否」「引数不正」の`ToolError`をtry/exceptの**外**で送出しており、`handle_message`→`do_POST`まで無捕捉のまま伝播してリクエストスレッドを落としていた（HTTPレスポンスが返らない）。3つのチェックをtry節の内側へ移動して修正。
   - `do_POST`の`initialize`処理が、Nextcloud接続不能（`ToolError`、`NextcloudError`ではない）を捕まえておらず同様に落ちていた。`except ToolError`を追加して修正。
   - どちらも「呼び出し元が変な入力を送る／Nextcloudが落ちている」という起こり得る状況で、サーバー全体を巻き込む実バグだった。テスト（`JsonRpcDispatchTests`・`HttpEndToEndTests`）に回帰テストとして残してある。
2. **systemdユニット検証**: `systemd-analyze verify`（変数をAnsible相当の値へ置換して）で警告0・exit 0を確認。`ProtectSystem=strict`＋`ReadWritePaths`の組み合わせは妥当。
3. **README作成**: `stacks/nextcloud-mcp/README.md`を作成（構成・受け口・ツール一覧・仕組み・設定・配備・テスト・未確認事項）。
4. **DNS配線**: `platform/terraform/dns.yaml`に`nextcloud-mcp`レコード（host: media-01、upstream: 127.0.0.1:5811、`auth`なし）を追加。`tests/test_tls_proxy.py`の`test_the_rendered_caddyfile_guards_only_the_auth_sites`が`len(sites)`を7→8に固定していたため合わせて更新し、他のスポットチェックにも`nextcloud-mcp`を追加した。
5. **計画書・利用者/管理者向け文書**: `docs/development/A06-nextcloud-mcp.md`（`index.md`の表・`mkdocs.yml`のnavにも追加）、`docs/services/nextcloud-agent.md`（利用者向け）、`docs/operations/nextcloud-mcp.md`（管理者向け）を作成。`python3 -m mkdocs build --strict`で自分の追加分は警告ゼロを確認（既存の壊れたリンク約20件は本セッション開始前からの未追跡差分に起因し、対象外）。
6. **Ansible構文チェック**: venvに`ansible-core`（`platform/ansible/requirements.txt`と同じ版）を入れて`--syntax-check`を実行し合格を確認。**副作用として**、DNSレコード追加が`tests/test_monitoring_stack.py`の`test_blackbox_covers_every_service_record_in_dns`を壊すことが判明（`ansible-playbook`が無い開発機ではこのテスト自体はスキップされないため気付けた）。`stacks/monitoring/prometheus/blackbox-targets.yml`に`https://nextcloud-mcp.apextox.dpdns.org/healthz`を追加して解消。

`python3 -m unittest discover -s tests`はansible-core込みで1179件全合格。ansible-core無しでも1178件（構文チェック系がスキップされるだけ）合格を確認済み。

## 実機配備（2026-09-26）

ユーザーの許可のもと、このセッションの公開鍵をmedia-01の`debian`ユーザーへ認可してもらい、実機へ配備した。

1. `tools/tf 20-dns plan`→`apply`で`nextcloud-mcp`のDNSレコードを作成（Cloudflareへ実際に1件追加。他レコードへの変更なし）。
2. `platform/ansible/media-nextcloud-mcp.yml`を適用。**1回目は失敗**（下記バグ）。修正後、再適用して成功。`/healthz`が200。
3. `platform/ansible/media-tls.yml`（`tls_proxy`ロール）を再適用してCaddyへ`nextcloud-mcp`のサイトブロックを追加。Let's EncryptからHTTPS証明書を取得済み（`https://nextcloud-mcp.apextox.dpdns.org/healthz`が200、`/mcp`への無認証POSTは401）。既存の media-01 サービス（nextcloud・kavita・navidrome・navidrome-api・metube・khinsider・freshrss）はすべて応答継続を確認済み（回帰なし）。

### 実機で見つけた3つ目のバグ（修正済み）

`stacks/nextcloud-mcp/nextcloud-mcp.service.j2`の`PrivateTmp=true`が、`ReadWritePaths={{ nextcloud_mcp_tmp }}`（`/var/tmp/nextcloud-mcp`）と衝突し、`systemd[1]: Failed to set up mount namespacing: /var/tmp/nextcloud-mcp: No such file or directory`（`status=226/NAMESPACE`）で起動に失敗した。`PrivateTmp=true`は`/var/tmp`ごと専用の空tmpfsへ差し替えてしまうため、実ディスク上のサブディレクトリを指す`ReadWritePaths`と原理的に矛盾する。`systemd-analyze verify`・Ansibleの`--check`・単体テストのいずれも検出できず、**実機起動で初めて表面化した**。`PrivateTmp=true`を削除して解消（GB級アーカイブをtmpfsに置かない設計上、そもそも不要だった）。

4. **monitor-01への監視反映も完了（2026-09-26）。** `platform/ansible/monitor.ini`の実インベントリで`platform/ansible/monitoring.yml`を適用（`ok=39 changed=0 failed=0`。既にこの内容で収束していた）。Prometheus APIで`probe_success{instance="https://nextcloud-mcp.apextox.dpdns.org/healthz"} == 1`を確認済み。docker/tls_proxy/monitoringの各ロールとも既存のGrafana/PeaNUTに影響なし。

### 未完了

- **user_oidcのアプリパスワードは未確認。** 実際のNextcloudユーザーでのBasic認証（`initialize`の成功）、MP3タグ編集→音楽同期タイマー→Navidrome反映、大きいzip展開のタイムアウトは、人間のユーザーが実データで確認する必要がある（このセッションは実在のNextcloudアカウントを持たない）。

## 目的

GeminiのGoogle Drive連携のように、AIエージェントがNextcloudのファイルを「ネイティブに」扱えるようにする。要求は次の3つ。

1. **読み書き・改名**: 一覧・読み・書き・フォルダ作成・移動/改名・コピー・削除
2. **MP3タグ編集**: 既存のタグ編集（MusicBrainz検索・バックアップ付き）と同じ結果
3. **圧縮・解凍**: zip/tar の作成と展開

利用者は**Nextcloudのアカウントを持つ全員**（専用ユーザーや共有サービスアカウントは作らない）。

## 決定事項

| 論点 | 決定 | 理由 |
| --- | --- | --- |
| 実装 | **自作 `nextcloud-mcp`**（推奨案で確定） | OSSの [cbcoutinho/nextcloud-mcp-server] はWebDAV CRUDはあるがMP3タグ・解凍が無く、CVE-2026-55640（<0.117.2）がある。公式Context AgentはAppAPI/HaRP導入が要り、タグ・解凍ツールが無い |
| 実行場所 | **media-01 の常設HTTPサービス** | tag-api（`127.0.0.1:5810`）はmedia-01のSGでLAN非公開（SGは22/80/443/53317のみ）。解凍/圧縮はサーバー側が速い。各利用者にバイナリを配らずに済む |
| 認証 | **呼び出し元の `Authorization` をそのままNextcloudへ転送**。Basic（`user:アプリパスワード`）推奨、将来のOIDC Bearerも同経路 | 共有資格情報を持たず、NextcloudのACL・共有・クォータがそのまま効く。「アカウントがあれば誰でも」を満たす |
| 資格情報の保存 | **サーバーは保存しない**（メモリにも残さない）。tag-apiトークンだけSOPSから.envへ（0400） | 漏えい面を増やさない |
| HTTPの入口 | `platform/terraform/dns.yaml` に `nextcloud-mcp` レコード（host: media-01、upstream: `127.0.0.1:<port>`、`auth: true` を**付けない**） | `navidrome-api` と同じ「TLSあり・SSOなし・アプリ自前認証」パターン。SGの追加開放は不要（443済み） |
| 実装形態 | **Python標準ライブラリ＋systemd**（`localsend-send` と同じ形）。コンテナ・独自イメージ・Go SDKは使わない | 既存の tag-api / localsend-send / media-stack-music-sync と同じ配備規約。pip依存なしでテスト可能 |
| 一時ファイル | `/var/tmp/nextcloud-mcp`（ディスク）。systemdは `ProtectSystem=strict` ＋ `ReadWritePaths=` でそこだけ許可 | `/tmp` はtmpfsでGB級アーカイブに不適（個人ルール） |
| ファイル操作 | すべて**Nextcloud WebDAV**（`/remote.php/dav/files/<user>/`）をユーザー資格情報で実行 | NextcloudのACL・共有・クォータ・ゴミ箱がそのまま効き、`occ files:scan` も不要 |
| 改名・移動 | WebDAV `MOVE`（`Destination` ヘッダ） | **fileidが維持される**ため共有リンク・添付が切れない。削除→再アップは切れる |
| 圧縮・解凍 | MCPサーバー内で `zipfile` / `tarfile` を実行し、入出力はWebDAV経由 | 公式 `files_zip`（Zipper、NC33対応、OCS APIあり）は圧縮のみで解凍APIが無い。将来の高速化候補として記録 |
| MP3タグ | 既存の **tag-api**（`stacks/music-tools/tag_api.py`、`:5810`）にブリッジ。`GET /tags`・`POST /tags`・`GET /musicbrainz` を使う | ID3バックアップ・対応フィールド限定・`.mp3`限定・MusicBrainzが既にある。MCPからmutagenを直接叩かない |
| タグ編集の権限 | 先にWebDAV PROPFINDで**呼び出し元が書ける**ことを確認してから、内部トークンでtag-apiを呼ぶ | tag-apiは共有トークンなので、ユーザー権限の確認をMCP側で担保する。対象は `/music` 配下の `.mp3` だけ |
| 反映 | タグ・ファイル操作のNextcloud/Navidrome反映は既存の**音楽同期タイマー**（`media-stack-music-sync.timer`）に任せる | 2026-09-24に修正済みで1時間ごとに動作。即時反映が要るようならrescanツールを足す |
| MCP | **Streamable HTTP**（`POST /mcp`、JSON-RPCを単一JSONで返す、セッションなし）。`initialize`・`ping`・`tools/list`・`tools/call` を実装 | opencodeの `type: "remote"` で使える。公式SDKを入れない分、実装は小さく保つ |
| 書き込みの安全 | 破壊的ツールに `destructiveHint`、削除はNextcloudゴミ箱、解凍は件数/展開サイズ/パス脱出/シンボリックリンクのガード、操作ログをjournaldへ | 生成AIに全権を渡すため |

### 採用しなかった案

- **OSSのcbcoutinho/nextcloud-mcp-server**: 高機能だがMP3タグ・解凍が無い。CVE未修正版の事故を避けるため見送り（使うなら0.117.2以上固定が必須）。
- **公式Context Agent（ExApp）**: AppAPI/HaRPの配備が必要で、欲しいタグ・解凍ツールが無い。NC内チャット（Assistant＋Context Chat）が欲しくなったら別途。
- **利用者ごとのstdio MCP**: 各端末にビルド・配布が必要で、tag-apiがLAN非公開のためタグ編集が届かない。
- **files_zip（Zipper）**: 圧縮はOCS API（`POST /ocs/v2.php/apps/files_zip/api/v1/zip`、`fileIds`＋`target`）で可能だが、解凍はAPI付きアプリが無い。全面自作に統一。

## ツール一覧（案）

読み取り:

| ツール | 内容 |
| --- | --- |
| `nextcloud_whoami` | 資格情報の確認（ユーザーID・表示名）。疎通確認用 |
| `nextcloud_list_files` | フォルダの一覧（PROPFIND Depth 1） |
| `nextcloud_file_info` | etag・サイズ・権限・fileid |
| `nextcloud_read_file` | 中身を返す（テキストはそのまま、バイナリは上限付きbase64） |
| `nextcloud_search_files` | 統合検索（OCS `/ocs/v2.php/search/providers/files/search`） |
| `nextcloud_read_music_tags` | tag-api `GET /tags` |
| `nextcloud_search_musicbrainz` | tag-api `GET /musicbrainz` |
| `nextcloud_list_archive` | 解凍前にzip/tarの中身を一覧 |

書き込み:

| ツール | 内容 |
| --- | --- |
| `nextcloud_write_file` | PUT（任意でetag照合） |
| `nextcloud_create_folder` | MKCOL |
| `nextcloud_move_file` | MOVE（改名兼用。fileid維持） |
| `nextcloud_copy_file` | COPY |
| `nextcloud_delete_file` | DELETE（ゴミ箱へ） |
| `nextcloud_write_music_tags` | tag-api `POST /tags`。書込権限をWebDAVで事前確認 |
| `nextcloud_create_zip` | 複数パスをzip化してPUT |
| `nextcloud_extract_archive` | zip/tar(.gz)を展開してPUT |

## 配備の形（案）

- 追加するもの
  - `stacks/nextcloud-mcp/nextcloud_mcp.py`（本体。標準ライブラリのみ）
  - `stacks/nextcloud-mcp/nextcloud-mcp.service.j2`（`localsend-send` を踏襲。`ProtectSystem=strict`＋`ReadWritePaths=/var/tmp/nextcloud-mcp`）
  - `stacks/nextcloud-mcp/README.md`
  - `platform/ansible/media-nextcloud-mcp.yml`（Python配布・`.env` 0400・unit設置）
  - `platform/terraform/dns.yaml` に `nextcloud-mcp` レコード
  - `tests/test_nextcloud_mcp.py`（純関数・Ansible配線・DNSの検査）
  - 計画書 `docs/development/A06-nextcloud-mcp.md`（A01–A05は使用済み・A05=OpenHome）
  - 利用者向け `docs/services/nextcloud-agent.md`、管理者向け `docs/operations/nextcloud-mcp.md`
- `.env`（0400）に入れる値
  - `NEXTCLOUD_MCP_PORT`（既定5811。5810=tag-api、5820=khinsiderと衝突しない）
  - `NEXTCLOUD_MCP_BASE_URL=http://127.0.0.1:8080`
  - `NEXTCLOUD_MCP_TAG_API_URL=http://127.0.0.1:5810`
  - `NEXTCLOUD_MCP_TAG_API_TOKEN`（既存 `platform/sops/music-tags.sops.yaml` を再利用）
  - `NEXTCLOUD_MCP_TMP=/var/tmp/nextcloud-mcp`
  - 解凍ガード（最大件数・最大展開バイト）と `NEXTCLOUD_MCP_READ_ONLY`（既定0）

### opencodeへの登録（利用者ごと）

```jsonc
{
  "mcp": {
    "nextcloud": {
      "type": "remote",
      "url": "https://nextcloud-mcp.apextox.dpdns.org/mcp",
      "oauth": false,
      "enabled": true,
      "headers": { "Authorization": "Basic <base64(user:アプリパスワード)>" }
    }
  }
}
```

- `opencode.jsonc` に秘密を直書きしない。`{file:...}`／`{env:...}` を使う。
- opencodeの `tools` で読み取り系だけ残す等、個別に無効化できる（MCP全体は `"nextcloud*": false`）。

## 未確認・実機で必ず確かめること

1. **user_oidc ユーザーのアプリパスワード**: この環境はOIDCログイン（`user_oidc`）。Settings → Security でアプリパスワードを作れるか、WebDAV/OCSでBasic認証が通るかを実機確認する。**通らない場合**はOIDCアクセストークンをBearerで渡す方式（`user_oidc` の `oidc_provider_bearer_validation`）へ切り替える。設計は「Authorizationを転送するだけ」なので変更は小さい。**（未確認。人間のNextcloudアカウントが必要）**
2. ~~Caddyの `nextcloud-mcp` レコード追加後に `tls_proxy` ロールをmedia-01へ再適用し、証明書と中継を確認する。~~ **完了（2026-09-26）。** `https://nextcloud-mcp.apextox.dpdns.org/healthz`が200、Let's Encrypt証明書取得済み。
3. tag-apiがサービスから `127.0.0.1:5810` で届くこと。**確認済み**（media-01上で`curl 127.0.0.1:5810/`が401=起動・到達を確認。トークン付きの実呼び出しは未確認）。
4. 大きいzipの解凍がopencodeのツールタイムアウトに収まるか。**未確認**（実データが必要）。収まらなければ上限を下げ、大物はNextcloud UI（files_zip等）へ誘導する。
5. 削除→ゴミ箱、MOVEでのfileid維持、タグ編集→同期タイマー→Navidrome反映を実データで確認する。**未確認**（実在のNextcloudアカウントが必要）。

## 残り（次の担当がやること）

1〜6・7（実機配備・DNS/TLS反映・monitor-01の監視反映）はすべて完了（上の「このセッションでの進捗」「実機配備」参照）。残るのは下の1点だけ。

7-b. **人間のNextcloudアカウントでの実データ確認**（上の「未確認」1・4・5）と `docs/operations/handover.md` への記録。**検証が済むまで動作確認済みと書かない。** 具体的には:
   - アプリパスワードが作れる・Basic認証で`initialize`が成功することを確認する（通らなければBearer方式へ切替）
   - 代表的なツール呼び出し（一覧・読み書き・タグ・zip作成/展開）を実データで確認する
   - 削除→ゴミ箱、MOVEでのfileid維持、タグ編集→同期タイマー→Navidrome反映を確認する
   - 大きいzipの解凍がopencodeのツールタイムアウトに収まるかを確認する

## 作成済みファイル（2026-09-25〜26）

| ファイル | 状態 | 内容 |
| --- | --- | --- |
| `handoff/nextcloud-mcp.md` | この文書 | 設計と残作業 |
| `stacks/nextcloud-mcp/nextcloud_mcp.py` | **配備済み・稼働中** | MCPサーバー本体（標準ライブラリのみ）。WebDAV CRUD・統合検索・tag-apiブリッジ・zip/tar作成/展開・Streamable HTTP JSON-RPC・読み取り専用モード。call_tool/do_POSTの例外処理バグ2件を修正済み |
| `stacks/nextcloud-mcp/nextcloud-mcp.service.j2` | **配備済み・稼働中** | systemdユニット。`ProtectSystem=strict`＋`ReadWritePaths={{ nextcloud_mcp_tmp }}`。`PrivateTmp=true`との衝突バグを実機で発見・修正済み |
| `stacks/nextcloud-mcp/README.md` | 作成済み | 構成・受け口・ツール一覧・仕組み・設定・配備・テスト |
| `platform/ansible/media-nextcloud-mcp.yml` | **media-01へ適用済み** | 本体コピー、`/var/tmp/nextcloud-mcp` 作成、SOPSからtag-apiトークンを`.env`(0400)へ、unit設置、healthz待ち |
| `platform/terraform/dns.yaml` | **Cloudflareへapply済み** | `nextcloud-mcp`レコード追加（`auth`なし） |
| `platform/ansible/media-tls.yml`（`tls_proxy`ロール） | **media-01へ再適用済み** | CaddyがLet's Encrypt証明書を取得し`nextcloud-mcp.apextox.dpdns.org`を中継中。既存サービスは無停止で継続 |
| `stacks/monitoring/prometheus/blackbox-targets.yml` | **monitor-01へ配備済み** | `/healthz`をhttps probeに追加。Prometheusで`probe_success==1`を確認済み |
| `tests/test_nextcloud_mcp.py` | 作成済み（85件合格） | 純関数・アーカイブ展開ガード・ツールハンドラ・JSON-RPCディスパッチ・実HTTP往復・Ansible配線 |
| `tests/test_tls_proxy.py` | 更新済み | `nextcloud-mcp`追加に合わせて件数・スポットチェックを更新 |
| `docs/development/A06-nextcloud-mcp.md` | 作成済み | 開発計画（`index.md`・`mkdocs.yml`にも追加） |
| `docs/services/nextcloud-agent.md` | 作成済み | 利用者向け（アプリパスワード作成・opencode登録・使い方） |
| `docs/operations/nextcloud-mcp.md` | 作成済み | 管理者向け（配備・資格情報・監視・トラブルシュート） |

## 現状（2026-09-26時点）

- **media-01で`nextcloud-mcp.service`が稼働中。** `https://nextcloud-mcp.apextox.dpdns.org/healthz`が200、`/mcp`への無認証POSTは401、Let's Encrypt証明書取得済み。既存のmedia-01サービス（nextcloud・kavita・navidrome・navidrome-api・metube・khinsider・freshrss）はすべて応答継続を確認済み（回帰なし）。
- `python3 -m unittest discover -s tests` は1179件合格（ansible-core込み）。`python3 -m mkdocs build --strict` は本セッションの追加分に起因する警告なし。
- monitor-01の監視反映も完了。残るのは人間のNextcloudアカウントでの実データ確認（上の「残り」7-b）だけ。
- 調査で確定した規約:
  - MCPの既存例は `cloud/mcp`（Go、読み取り専用、stdio）。**ただし未マージで作業ツリーからは削除されている**（`main` にも無い）。参考にするなら `git show HEAD:cloud/mcp/...`。
  - 常設の小APIは「Python標準ライブラリ＋systemd＋SOPS＋Ansible」が正本（`stacks/localsend-send`、`stacks/music-tools/tag_api.py`）。
  - テストは `python3 -m unittest discover -s tests`。1対象1ファイル、`tests/support.py` のヘルパを使う。Ansibleは `support.syntax_check` で構文検査。
  - 秘密値はSOPS。`.env` は配備先で0400。Gitに置かない。
  - DNS/Caddyは `platform/terraform/dns.yaml` が正本。Forward Authを付けるかは `auth: true` で決まる。
  - media-01のSGは22/80/443/53317のみ。**新しいポートをLANへ開けない。**

## 注意（次の担当へ）

- **作業ツリーが汚れている。** `HEAD`（feat/ops-monitoring-storage）に対し177件の差分があり、MCP関連・docs・`tools/docs-map.py` 等の削除と、`handoff/`・`stacks/eufy-leo-rtc/`・`stacks/mail-view/` 等の未追跡が混在する。`main` 基準の内容に寄せた未コミット作業に見える。**`git checkout -- .` や不用意なコミットをしない。** 既存の変更には触れず、新規ファイル中心で作業する。
- この文書は未追跡の `handoff/` 配下。コミットは指示があるまでしない。
- アプリパスワード・OIDCトークンを会話・コミット・ノートに残さない。
- `Vaultwarden` の保管庫、Nextcloudの `Converted`、`storage/` はMCPの対象外にする（パス許可リストで拒否）。

## 参照

- 入口: `docs/development/index.md`（作業ID一覧）、`docs/operations/services.md`
- 規約: `tests/README.md`、`stacks/localsend-send/`、`platform/ansible/media-localsend.yml`
- タグAPI: `stacks/music-tools/tag_api.py`、`stacks/music-tools/README.md`、`docs/development/W06-music-tools.md`
- Nextcloud: `stacks/media/nextcloud/README.md`、`platform/ansible/group_vars/media.yml`、`docs/operations/nextcloud-permissions.md`
- 入口/DNS: `stacks/tls-proxy/`、`platform/terraform/dns.yaml`、`docs/operations/network-auth.md`
- MCPの既存実装（履歴）: `git show HEAD:cloud/mcp/main.go`、`git show HEAD:cloud/mcp/tools.go`、`git show HEAD:docs/operations/mcp.md`
