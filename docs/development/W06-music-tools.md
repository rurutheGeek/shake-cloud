---
title: W06 MeTube・音楽変換・タグ編集のmedia-01移行
updated: 2026-10-02
section: 開発計画
audience: 開発者
tags:
  - plan
  - music
---

# W06 MeTube・音楽変換・タグ編集のmedia-01移行

> **更新日** 2026-10-02 ・ **区分** 開発計画 ・ **読む人** 開発者

これは開発計画であり、配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

**状態**: media-01 で MeTube・変換・タグAPI・KHInsiderが稼働し、Nextcloudの「タグを編集」から読み書きできる（2026-09-14）。同期タイマーは停止中で、切替が残る。タグ編集をNextcloudへ統合したためPicardは撤去した

`stacks/music-tools/compose.yaml` にMeTube・変換・タグAPIがあり、`platform/ansible/music-tools.yml` と同期タイマーが存在する。[音楽手順](../services/music.md)では共有Cookieの実物未登録・対象URL取得未確認を区別している。タグ編集はNextcloudの自作アプリ `shake_tags` が同スタックのタグAPI（`:5810`・MusicBrainz検索つき）を使う。導線の経緯は[D05](D05-picard.md)。

**配備（2026-09-12〜14）:** media-01の `/opt/media-stack/music-tools` に一式を置き、Ansible（`music-tools.yml`）で MeTube・変換・タグAPI・KHInsiderを配備した（KHInsiderは2026-09-14）。同期タイマーは切替まで停止している。共有Cookieは未登録のためYouTubeの実URL取得は未確認（Cookie不要のURLでMeTube→`music/YouTube`着地は確認済み）。

配備先: **media-01**。開発先は既存 `stacks/music-tools/`。`stacks/media/` は配置の案内と原本の共通規約を担当する。

## 実装手順

1. 既存lockと変換コードを再利用し、music原本・Converted・動画・一時領域・変換状態・Cookieの配置と権限を移す。再開時の重複変換・原本上書きを防ぐ。
2. タグ編集はNextcloudの `shake_tags` と、共有musicを読み書きするタグAPI（`tag_api.py`、`:5810`、トークン認証。MusicBrainz検索・バックアップ付き）で行う。ブラウザー内デスクトップ型のGUIは使わない。BCSTM原本と `music/Converted/` を直接編集しない。
3. 認証は[identity](../operations/identity.md)のOIDCへ統合する。既存アカウントを引き継ぐ場合は `users` / `admins` への紐付けを検証し、メール一致だけで別人のデータを結び付けない。MeTubeは共有キュー・共有Cookieとして運用し、秘密値は対象ホストへ配る。Nextcloud/Navidromeへの同期処理とタグAPIの入口を新配置に合わせる。
4. 既存環境のキューを止め、未完了ジョブと変換状態を保全して復元する。既存環境の同期タイマーを停止し、新タイマーを一つだけ有効にして少数ファイルから切り替える。タグ保存と変換・同期が同じファイルを同時に触らない順序にする。

## 依存と並列作業

- 開発開始: なし。手元のサンプル音声・BCSTMと模擬取得結果で変換・同期を検証する。
- 配備・切替: [I02](I02-media-vm.md)、[I01](I01-resources.md)、[N05](N05-https.md)。結合確認は[W03](W03-nextcloud.md)/[W05](W05-navidrome.md)、対象URLの検証は使用可能なURLと必要な共有Cookieの用意後。タグ編集の入口は[W05](W05-navidrome.md)・[W03](W03-nextcloud.md)と調整する。
- 競合調整: W03/W05とmusicパスと同期の唯一の実行者を決める。タグ保存と同じファイルを同時更新しない。大規模変換は負荷測定と調整する。

## 検証・完了条件

- 許可された音源の取得、音声/動画の保存先分離、BCSTM変換、タグ編集のプレビューと保存を確認する。
- Nextcloudの「タグを編集」でMusicBrainz検索→保存が通り、NextcloudとNavidromeに反映される。BCSTM原本と `music/Converted/` を直接編集していない。
- 再起動・途中失敗からの再試行で二重登録や原本破損がない。
- 共有CookieはGit・ログに出ず、未認証者はMeTubeを利用できない（タグAPIはトークンと送信元で制限する）。状態・設定の復元を確認し、外部取得未確認は未確認のまま記録する。

## 実装記録

- 2026-09-12: Picard Web GUI（`jlesage/musicbrainz-picard`、digest固定、`127.0.0.1:5800`）を media-01 へ手動SSHで先行配備。HTTP 200・healthy。MeTube・変換・同期・共有Cookieは未移行。
- 2026-09-12: `platform/ansible/music-tools.yml` を拡張し、Ansibleで再現可能にした。`music_tools_services` でサービスの段階配備（例: `-e music_tools_services=tag-api`。複数はカンマ区切りかJSONリスト）、`music_tools_sync_enabled` で同期タイマーの有効/無効を制御する。既定は全サービス・同期有効で、既存ホストの再実行の挙動を変えない。手動SSHは先行配備の一時手段であり、media-01の状態は playbook を再適用して収束させる。配備・タグ編集の使い方は `stacks/music-tools/README.md` を参照。
- 2026-09-13: **タグAPI（`stacks/music-tools/tag_api.py`、`:5810`、トークン認証）とNextcloudアプリ `shake_tags`（ファイルの「…」→「タグを編集」、MusicBrainz検索つき）を配備。** 実MP3でタグの読み書き・冪等性・バックアップ（`storage/tags/tag-backups/`）を実機確認。トークンは `platform/sops/music-tags.sops.yaml`。コード変更はconvertと同じハッシュラベルでコンテナ再作成される。2026-09-13: **Picardは撤去した**（compose・lock・検証・DNSから削除。設定データ `storage/picard` は残置し、戻す場合はgitで戻す）。
- 2026-09-13: **ブラウザー実測で `shake_tags` のメニュー出現〜エディタ起動（一般ユーザー、タグAPI 200）を確認。** それまでの不具合はアプリ側3件: ①`@nextcloud/files` がv3系でNC33の v4 グローバルレジストリ（`window._nc_files_scope`）に載らない ②`Node.extension` はドット込み（`.mp3`）なのに `'mp3'` と比較 ③コントローラに `#[NoAdminRequired]` が無く実行時403。あわせてJSを `Util::addInitScript` へ変更。詳細は[D08](D08-nextcloud-print.md)の実装メモ。
- 2026-09-13: **ライブラリ一括整理 `organize.py` を追加。** MusicBrainzのリリース→録音照合と既存タグ/ファイル名から `アーティスト/アルバム/NN - 曲名.mp3` へ移動・リネームし、タグを書き、アルバムへ `cover.jpg` を置く。plan（調査のみ）→ apply（ID3バックアップ・移動ジャーナル付き）→ undo の3段階。日本語ゲームBGMは `organize-aliases.json`（albums/folders単位の上書き）で補う。カバーは Cover Art Archive → iTunes(JP) → Deezer → 既存Folder.jpg の順で、しきい値未満は付けない。tagger は `/tools` を 0711 で参照する（0750ではコンテナ33:33がPermission denied、実機確認）。
- 2026-09-13: **既存ライブラリ1,470曲へ一括整理を適用。** plan（dev-b、`organize.py`）で MusicBrainz録音一致877・リリース一致53・既存タグ整理526・未解決14、カバー355件を用意し、media-01で apply（タグ1,470・移動1,456・cover.jpg 394・WMP残骸20削除）。Navidromeは active 1,619曲（MP3 1,470＋既存WAV 149）・529アルバム・missing 0へ収束し、Nextcloudは `occ files:scan` でエラー0。未解決14曲は `20230520/` と直下に残置。**media-01から musicbrainz.org / coverartarchive.org に到達できない**（iTunes/Deezerは到達可）ため、MetaBrainz照合は到達可能な端末で plan し、`manifest.json`・`covers/`・`report.md` を `storage/convert/organize/` へ運んで apply する運用にした。
- 2026-09-13: **ユーザーレビューによる補正を適用。** 要チェック一覧（430曲）を提示し、Pokémonは元ディレクトリのゲームのサントラへ、クラシックは作曲者ごとの `クラシック` アルバムへ、指定曲（Second Heaven、戦闘のテーマ、月光など約50件）を個別修正。`organize.py plan --no-lookup --corrections organize-corrections.json` でMB上書きなしに再整理し、966移動・970タグ更新。埋め込みAPICが誤カバーとして表示される件（DAOKOの例）を受け、`strip-embedded-art.py` で51ファイルのAPICを削除（画像は `storage/convert/organize/apic-backups/` に保存し、cover.jpg優先の運用へ統一）。残り195曲（高131/中64）をv2一覧として再提示。
- 2026-09-14: **KHInsiderのアルバム一括ダウンロード画面（`khinsider.py`、`:5820`）を追加。** MeTubeが1本のURLしか扱えないため、アルバムページ→曲ページ→配信MP3の順に取得し `music/Khinsider/<アルバム名>/` へ保存する。既存ファイルはスキップし、途中失敗後も再投入で続きから取得する。Docker・Ansible・DNS（`khinsider.apextox.dpdns.org`）・Authentik Forward Authまで配線し、テストは `tests/test_music_khinsider.py`。**2026-09-14: media-01へ実配備した。** `20-dns` でAレコード、`identity.yml` でForward Authプロバイダと `khinsider` アプリ（usersへ許可）、`music-tools.yml` でコンテナ（healthy）、`media-tls.yml` でCaddy（Let's Encrypt証明書付き）。未認証の `/` は `auth.apextox.dpdns.org` の khinsider プロバイダへ302し、コンテナ内からアルバムページの取得と `music/Khinsider` への書き込みを実機確認した（実際の楽曲ダウンロードは未実施）。
- 2026-09-14: **KHInsiderの「日本語の曲名に戻す」を追加。** KHInsiderは日本語ゲームでもアルバム名・曲名を英語で載せるため、取得時のオプションで扱う。**アルバム名はKHInsiderの日本語別名＝原典ゲームの日本語タイトルにする**（例: `kirby-super-star` → `星のカービィスーパーデラックス`。フォルダとID3 `album` に反映）。自動照合した別アルバム（コンサート等）の名前では置き換えない。曲名は **MusicBrainz**（無ければiTunes JP）から公式の日本語名を照合し、ファイル名とID3 `title` に書く。誤マッチ防止のため曲数一致・尺一致（±2秒または3%）・日本語名が半数以上を条件にし、満たさない曲は英語のまま残す。手動辞書 `khinsider-ja.json`（slug→`itunes_term`/`album`/`tracks`）が自動照合より優先。`music-tools.yml` を再適用してmedia-01へ配備し、コンテナ内で「星のカービィ25周年記念オーケストラコンサート」26曲の照合（15秒）とID3への日本語書き込み・読み戻しを実機確認した。**アルバム名は照合結果では変えず、KHInsiderの日本語別名か手動辞書だけで決める**（照合した別アルバム名で置き換えない）。手動辞書 `kirby-super-star` に `星のカービィ スーパーデラックス`（任天堂の公式表記）を登録し、既存ライブラリの `Jun Ishikawa, Dan Miyakawa/Kirby Super Star` も同フォルダ名へリネームして70曲の `album` タグを日本語に更新した（Navidromeは1時間ごとのスキャンで反映）。`kirby-super-star` は公式の日本語トラックリストが無いため曲名は英語のまま。辞書は単一ファイルのbind mountで稼働中コンテナに反映されないため、`manage.py` の `KHINSIDER_CODE_SHA` に辞書の内容も含めて再作成させる。テストは `tests/test_music_khinsider.py`。
- 2026-09-15: **`kirby-super-star` の70曲の日本語名を手動辞書へ登録。** 自動照合では見つからないゲームリップについて、『星のカービィ 非公式wiki』のサウンドテスト一覧（<https://wiki3.jp/kirby/page/3588>）に基づき `khinsider-ja.json` の `tracks`（KHInsiderの英語曲名→日本語）へ70件を記入した。既存ライブラリ `Jun Ishikawa, Dan Miyakawa/星のカービィ スーパーデラックス` の70曲も、ID3 `title` を日本語へ更新しファイル名を `NN - 日本語.mp3` へ改名した（曲順はKHInsiderと一致することを確認）。Navidromeは1時間ごとのスキャンで反映する。Nextcloudは同期タイマー停止中のため即時反映されない（当時の既知の未了点。2026-09-24に修正済み）。
- 2026-09-26: **KHInsiderをアルバム単位で最大3並列にした。** `KHINSIDER_WORKERS`（既定3・上限3）でワーカー数を決め、各ワーカーは thread-local な `curl_cffi` セッションを持つ。同一アルバムはURLごとのロックで直列化し、二重ダウンロードを防ぐ。全ワーカー合計のリクエスト間隔（`KHINSIDER_REQUEST_INTERVAL`、既定0.4秒）で叩きすぎを防ぐ。ジョブ履歴の保存は複数ワーカーから呼ばれるためロックで直列化した。
- 2026-09-26: **KHInsiderの進捗を見えるようにした。** ジョブ履歴を `storage/khinsider/jobs.json`（コンテナ内 `/state`）へ永続化し、コンテナ再作成をまたいで残す（中断した実行中ジョブは「再起動で中断」として失敗表示し、「再試行」で続きから再開）。一覧は実行中がある間5秒ごとに自動更新し、状態を日本語（待機中/実行中/完了/失敗）・`done/total`・失敗理由つきで表示する。さらに**投入時に既存フォルダを調べ、保存済みの曲数と未取得数を出す確認画面**を追加（同じアルバムの再投入で、どこまで取得済みか分かる）。「続きから」で再開し、保存済みはスキップする。
- 2026-09-23: **KHInsiderのCloudflare 403対策を強化。** 配信元が `cf-mitigated: challenge`（403）を返すため、MeTubeイメージ同梱の `curl_cffi` でブラウザ指紋を模し、challenge時は**セッションを作り直して指紋（chrome/chrome131/firefox133）を切り替え**、待ち時間を5→15→30→60秒へ延長。曲間の既定待ちも0.4→0.8秒にした。失敗したジョブの画面に **「再試行」** ボタンを追加（同じURL・同じ日本語オプションで再投入。保存済みはスキップ）。`pokepark-pikachu-s-adventure-wii`（111曲）の取得をコンテナ内で確認。
- 2026-09-15: **ダウンロードのファイル名を曲名だけにした。** これまではサイトの `1-01. 曲名.mp3` を踏襲していたが、番号はID3の `tracknumber`/`discnumber`（サイトの `d-nn.` 接頭辞から取得）へ入れ、ファイル名には付けない。同名曲は `曲名 (2).mp3`。既存ライブラリの70曲も `NN - 曲名.mp3` から `曲名.mp3` へ改名した（`tracknumber` は既存タグを維持）。
- 2026-09-15: **タグ編集アプリを「MP3タグ編集」に改名（v1.0.7）。** Nextcloud標準の「タグ」機能と紛らわしいため、ファイルの「…」メニューとアプリ名を明確化した。あわせて **コメント（COMM）** をタグAPI（`tag_api.py`）と編集フォームに追加し、ゲームBGMの「vs ○○」などの備考を書けるようにした（画像付きの項目説明は[Nextcloudの使い方](../services/nextcloud-guide.md)）。EasyID3はCOMMを扱えないため、API側はID3フレームを直接読み書きする。
- 2026-09-24: **音楽同期タイマーの既知不具合を修正。** `media-stack-music-sync.service` が (1) `/opt/media-stack/runtime` 不在、(2) 分割レイアウト（`media/<unit>`）に対応していない、(3) `runtime/access.json` のNavidromeパスワード依存、の3つで毎回失敗していた。`sync-music.py` を両レイアウト対応にし、runtimeを作成し、Navidromeは同梱CLIの `navidrome scan` で再スキャンする（認証情報不要）。実機で1回目=Nextcloudスキャン+Navidrome rescan、2回目=`OK: music unchanged` を確認。
- 2026-09-24: **既存のポケモン4アルバム（458曲）を日本語盤のメタデータへ修正。** ダウンロード時に英語だった `album`・`title` と外部ツール由来の英語クレジットを、MusicBrainzの日本語盤（赤・緑 2016 / ブラック2・ホワイト2 2012 / X・Y 2013 / Let's Go 2018）に `(disc, track)` と尺の一致で対応付けて書き換えた。アルバム名・曲名は日本語、`artist`/`composer` は日本語の作曲者クレジット、`albumartist` は盤のクレジット、`date` は発売日。ファイル名も日本語曲名へ改名。移行スクリプトは `stacks/music-tools/retag-japanese.py`（plan/apply、旧名・旧タグのジャーナル）。ポケモン不思議のダンジョン救助隊DXは日本語サウンドトラックが無いため対象外。**ブラック2・ホワイト2 は403で中断して79/173曲だったため、未取得の94曲を同じ対応表（KHInsiderのslug `pokemon-black-and-white-2-super-music-collection`）で日本語の曲名・タグ付きで追加取得し、173/173曲にした。** 旧中断の0バイト`.part`も削除。ジャーナル・マニフェスト・使用スクリプトは media-01 の `/srv/media-stack/storage/retag-japanese/`。
- 2026-09-24: **公式サウンドトラックがある日本語盤を追加で6枚（約1,000曲）修正。** サン・ムーン（161/169）・ハートゴールド&ソウルシルバー（262/270）・オメガルビー&アルファサファイア（268/269）・LEGENDS アルセウス（110/110）・ルビー&サファイア（108/109）・ファイアレッド&リーフグリーン（89/90）を、MusicBrainzの日本語盤へ `(disc, track)`＋尺で対応付けて、アルバム名・曲名・作曲/アーティスト・発売日を日本語化し、ファイル名も日本語曲名へ改名した（`stacks/music-tools/retag-japanese.py` の `ALBUMS` に追記）。尺が一致しない計19曲（『The End』などの短い曲・重複テイク）は英語のまま。日本語盤が見つからないもの（BDSP・ソード/シールド+エキスパンションパス・不思議のダンジョン各作・レンジャー・ランブル・シャッフル・マスターズEX・スマブラ・タイピング）は対象外。
- 2026-09-24: **KHInsiderの403（Cloudflareのbot challenge）を解消。** 旧実装のurllib＋独自UAにはCloudflareが `cf-mitigated: challenge` の403を返す（UAをブラウザに変えてもTLS/HTTP2指紋が違うと解けない）。MeTubeイメージがyt-dlp経由で同梱する **curl_cffi** を使い、Chromeの指紋で接続する。1セッションを使い回してクリアランスCookieを曲ページ・配信URLへ引き継ぎ、`403`/`429`/`503` は5→15→30秒で再試行。それでも通らないときは理由を画面に出す。テストは `tests/test_music_khinsider.py` の `BrowserFetchTests`（セッション利用・再試行・失敗時の非書込）。実機ではコンテナ内から `pokemon-x-y` のアルバムページ取得（200）と1曲のダウンロードを確認した。

<a id="handover-log"></a>

## handover移動分の作業記録

handover.md の「5. 進捗とTODO」表の該当行から移した記録（原文のまま。表セルを日付ごとの箇条書きに整形しただけ）。いまの状態と未完は handover.md の該当行を参照。

- **2026-09-26: 全曲レビュー（review）をmusic-toolsへ追加。
- ** `https://navidrome.apextox.dpdns.org/review/`（SSO）でアーティスト→アルバム→曲をたどり、ページ遷移なしで試聴、👍いいね／⚠指摘（項目・正しい値・メモ）を付けられる。指摘は `/opt/media-stack/music-tools/storage/review/events.jsonl`（追記のみ）に保存し、AIが読んで直す。ユーザーはForward Authのヘッダーで識別し、確認数とアルバム・アーティストの完了印を出す。旧静的確認HTMLは `/review-static/` へ移動（Caddyのパス入口は `dns.yaml` の `path_routes`、前置きの除去は認証の後ろ）。
- **2026-09-26: レビューで見つかった作曲者タグを調査・一括修正（339曲）。
- ** 非サントラ中心にMB任せでなく手調べで `composer` を補完（たなかひろかず/中田ヤスタカ/川谷絵音/神前暁/田代智一/多和田吏/三原康司/小林武史/きくお 等）。タグ全欠けだった「ポケモンカフェミックス」36曲（作曲・アーティスト=多和田吏）と「はねろ!コイキング」11曲（artist=SOLIDTUNE Inc.、作曲=高本誠一・舛田智）はalbum/artistも補完。ID3バックアップは `/opt/media-stack/music-tools/storage/tags/tag-backups/composer-fill/`（適用は`docker exec media-music-tools-tag-api-1 python3 -`、dry→apply）。
- **2026-09-26: バンドリ（BanG Dream!）全56曲を補完。
- ** Roseliaは先行分、今回は Poppin'Party/Afterglow/ハロー、ハッピーワールド！/Pastel＊Palettes/RAISE A SUILEN/花園たえ/カバー計34曲に Elements Garden 系のクレジット（上松範康・藤永龍太郎・藤田淳平・都丸椋太・岩橋星実・藤間仁・末益涼太・菊田大介・笠井雄太・母里治樹）とカバー原曲（ヒゲドライバー/みきとP/Orangestar/EasyPop）を反映。索引の再読込はNFS上の7,562曲で約3分かかる。残りは 非ゲームの要調査（MEGAREX/PSYQUI等の同人コンピ、Charisma.com、Avril/The Wantedの追加曲、IOSYS東方、平野綾/松本梨香 等）と、作曲者=アーティストで正しいゲームBGM・Vocaloid。タグ全欠けのポケモンBGM 193曲を補完（ポッ拳56=Various Artists/橋本大樹ほか10名、ピンボールRS38=巣山員也・佐野あゆみ、マグナゲート28=いとうけいすけ・川越康弘、スマイル27=裏谷玲央、コマスター22=景山将太、とうぞく18=西村隆文、ポケパーク2・牧場・はねろ ほか）。
- **はねろ!コイキングの11曲は中身がM4A（ftyp）なのに.mp3拡張子で、先頭のID3v2がMP4の絶対オフセットを壊していた**ため、ID3を剥がしてffmpegで実MP3へ変換しタグを付け直した（`/state/m4a_to_mp3.py`、原本は `/opt/media-stack/music-tools/storage/tags/tag-backups/m4a-originals/`）。非ゲームも追加補完（DA PUMP if...=富樫明生、CHEMISTRY Period、BLUE SAPPHIRE、The Wanted Warzone、Sk8er Boi、薔薇園アヴ、ホログラム=光村龍哉、Perfume、松本梨香/ライオン/GARDEN=たなかひろかず、ZUN、しも、Butter-Fly=千綿偉功、創聖=菅野よう子 等）。
- **2026-09-26: レビュー索引をNavidromeのSQLite（`media_file`）から作る方式へ変更。
- ** `storage/navidrome` をreviewコンテナへ読み取り専用でマウントし（`NAVIDROME_DATA_ROOT`）、再構築は約0.6秒。タグの正本はファイルのまま、一覧はNavidromeが見ている内容と揃う。
- **Navidromeのアルバム分割を修正。
- ** 原因は同一フォルダ内のalbumartist不一致（Navidromeはalbumartist+albumでアルバムを分ける）。ポケパーク2の2曲（オープニング/タイトル、Various Artists→橘田拓人/小谷野謙一）とポケモンコロシアムの1曲（コロシアム・スタジアム：ファイナル、多和田吏→多和田吏/Tsukasa Tawada）を揃え、両アルバムとも1つに統合。NavidromeはWatchChangesで数秒で再スキャンする。
- **2026-09-26: ローマ字重複と同名アルバムを整理。
- ** ローマ字併記（例「多和田吏 • Tsukasa Tawada」）は TPE2 ではなく **TXXX:ALBUM ARTIST / TXXX:ENSEMBLE** が残っていたのが原因（Navidromeは両方をalbumartistとして結合する）。340ファイルから該当TXXX（Tsukasa Tawada / Takuto Kitsuta / Kenichi Koyano）を除去し、コロシアム・ポケモンレンジャー3作のアルバムを統合。モンスターハンター（7曲）・Singles（23曲）・クラシック（19曲）は albumartist=Various Artists に統一、ロケット団よ永遠にの別リップ1曲は既存シングルへ統合。カバー/アレンジの3曲（Arthur Ebeling「Bad Guy」・R.O.T.「You Should See Me in a Crown」・Baguettes Ensemble「ブラック★ロックシューター」）は album=曲名にして衝突解消。結果、albumartistが複数あるアルバムは0件。
- **2026-09-26: レビュー板の不具合修正とC418整備。
- ** 保存後に `openArtist` が `VIEW.album` を null にして `album=null` の0曲（null表示）になっていたため、保存前のアルバムを保持して復元するよう修正。投票・指摘の保存で一覧を作り直してスクロールが先頭に戻る問題を、行だけ更新（`applyRowState`／`refreshCounts`）してスクロール維持に変更（保存時は編集欄を閉じる）。再読込完了時の自動更新もアルバム選択を保持するようにした。読み込み時に全指摘の編集欄を自動展開していたのをやめ、⚠を押したときだけ開くようにした。ヘッダーの ◧/◨ ボタンと **Ctrl+B（Cmd+B）** でアーティスト一覧、▤/▥ ボタンと **Ctrl+Alt+B** でアルバム一覧を折りたためる（状態は localStorage に保持、両方たたむと曲一覧が全幅）。
- **東方Project原作のKHInsider一括ダウンロードを投入（2026-09-26）**: ユーザー要望で「本編だけ30枚」に確定。PC-98 5作（靈異伝・封魔録OPNA・夢時空OPNA・幻想郷・怪綺談）＋Windows 25枚（7.5/09/9.5/10/10.5/11/12/12.3/12.5/12.8/13/13.5/14/14.3/14.5/15/15.5/16/16.5/17/17.5/18/18.5/19/20）。紅魔郷・妖々夢・永夜抄は既存が完全なため除外。ZUN's Music Collection 12枚は対象外。重複のOPN版2枚と深秘録初回特典CDは `/opt/media-stack/music-tools/storage/trash/touhou-extras-20260926/` へ退避。日本語化は進行中。公式曲名の取得元は MusicBrainz（PC-98盤のみ存在）と Touhou Wiki（en.touhouwiki.net の各作品 /Music ページ、コンテナの curl_cffi で取得）。英訳↔日本語の対応で自動照合した結果、Windows本編は概ね90%以上一致（09/09.5/10/12.8=100%、11/12/14/15=17/18 等）。格闘ゲーム派生（7.5/10.5/12.3/13.5/14.5/15.5/17.5）とPC-98（01〜05）は英語名が公式訳と一致せず要手当て。方針: ファイル名は「曲名.mp3」（NNなし）、曲番はID3のtracknumber。作業データは /var/tmp/work/music-review/（touhou_ja.json・touhou_wiki.json・touhou_match.py・apply_touhou.py）。
- **適用済み（2026-09-26）**: 30枚を `/srv/media-stack/library/music/ZUN/<公式日本語アルバム名>/` へ移動し、album/artist/albumartist=ZUN・composer=ZUN・discnumber=1・tracknumber を設定、ファイル名は曲名のみ。曲名は294曲を日本語化（本編Windowsはほぼ完了）。残り420曲は英語のまま（格闘ゲーム派生7作・PC-98・神霊廟の霊界版・虹龍洞など、KHの英語名がTouhou Wikiの公式訳と一致せず要手当て）。旧ZUN/の4枚（紅魔郷・妖々夢・永夜抄・花映塚の「サウンドトラック」付き）は既存のまま（ファイル名のNN除去は未実施）。
- **確定（2026-09-26）**: ユーザー定義により「原作」= 弾幕シューティング本編ラインのみ（PC-98 01〜05＋Windows 06〜20の20作）。派生13作（7.5/9.5/10.5/12.3/12.5/12.8/13.5/14.3/14.5/15.5/16.5/17.5/18.5）と旧花映塚1曲はゴミ箱 `/opt/media-stack/music-tools/storage/trash/touhou-spinoffs-20260926/` へ退避。ZUN/ は本編20アルバム。428曲中323曲を公式日本語曲名に（Touhou Wikiの英訳対応＋ja.wikipediaの曲目リスト、PC-98はMusicBrainz）。残り105曲は英語（PC-98の公式英語タイトル A Sacred Lot / Bad Apple!! 等が中心で、これは公式名のため正しい。加えて神霊廟の霊界版の一部・虹龍洞などの未照合）。ファイル名は曲名のみ（NNなし）、tracknumber/discnumber/album/artist/albumartist/composer=ZUN を設定済み。作業データ: /var/tmp/work/music-review/。
- **クラシック19曲を整備（2026-09-26）**: アルバム名をすべて作曲者名に変更（album=albumartist=作曲者）。曲名を正しい曲目名に修正（剣の舞、ユーモレスク第7番、ジムノペディ第1番、月の光、木星、怒りの日、ファランドール、交響曲第5番「革命」第4楽章、熊蜂の飛行、ラ・カンパネラ、愛の夢第3番、小犬のワルツ、夜想曲第2番、G線上のアリア、カノン、タイプライター、ピアノソナタ第14番「月光」、ディエス・イレ 等）。ホルストの「惑星」は長さ約8分から木星と推定（要確認）。
- **C418のMinecraft 2アルバムを整備**: `C418/Minecraft/` の28曲を公式『Minecraft – Volume Alpha』(14曲)・『Minecraft – Volume Beta』(25曲)へ振り分け（曲名・曲番は公式トラックリスト、全長一致を確認。ゲーム内名はcommentに保持）、Volume Betaフォルダの既存10曲の曲番も公式に修正（Alpha=#2, Chirp=#20, Wait=#21, Mellohi=#22, Stal=#23, Strad=#24, Ward=#26, Mall=#27, Blocks=#28, Far=#29）、Cat=#19。Navidromeの再読込はタグの実書き込みで発火し、TXXX除去は40ファイルずつ8秒間隔で実行した。残りは自己名義（Such/group_inou/日食なつこ等）と未確認のみ（SMバナーの2曲、Charisma.com、The Wanted追加曲、IOSYS東方、太鼓/アイマス等 約70曲）。
- **2026-09-27: 東方本編20作のタグを東方元ネタwiki（seesaawiki.jp/toho-motoneta_2nd）基準で再構築。
- ** PC-98 5作は英語wikiベースの誤り（「死なばもろとも」欠落、魔鏡（別バージョン）の入替、曲順がM.TEST/MusicModeと不一致、ファイル名の切り詰め）を全面修正し、公式曲順・公式曲名に統一（A Sacred Lot / Bad Apple!! 等の公式英語名はそのまま）。Windows 15作も、06/07/08に混入していた重複8ファイル（`/opt/media-stack/music-tools/storage/trash/touhou-dup-extras-20260927/` へ退避）による曲番ズレ、神霊廟の霊界版14曲挿入によるタグズレ（古きユアンシェン欠落）、「風神少女 (Short Version)」「秘神マターラ ～ Hidden Star in All Seasons.」「綿月のスペルカード ～ 神海戦」「最後の一人は慣れてるから ～ Stone Goddess」等の切り詰め・ローマ字混入、ファイル名の「～」切れを修正。全20作でファイル名=曲名・tracknumber=公式順・重複0・連番を実機確認。
- **2026-09-27: ゲーム系サントラのアルバム名を整理（公式サントラが無いものは有名な日本語ゲームタイトル）。
- ** DKC2の残り1曲→「スーパードンキーコング2 ディディーコング&ディクシーコング」（別バージョンとして統合、36曲）、Pokémon Bank→ポケモンバンク、Pokémon Sleep（Spotify）→ポケモンスリープ（既存リップと統合し112曲・albumartist統一）。公式サントラ側の英語名も日本語公式名へ（Mega Man 2 Sound Collection→ロックマン2 サウンドコレクション、MONSTER STRIKE OFFICIAL SOUNDTRACK→モンスターストライク オリジナルサウンドトラック、The Very Best of Kirby: 52 Hit Tracks→星のカービィ ベストセレクション）。空だったKhinsider配下7フォルダを削除。
- **2026-09-27: アルバムカバー整備（方針: 公式サントラが無いゲームはゲームのパッケージ/タイトルの日本語版）。
- ** 東方本編20作すべてにカバーを設定（PC-98の5作は各ゲームのタイトル画面、錦上京は公式カバーTh20cover。cover.png/jpg＋ID3 APICを埋め込み）。直近で整理したゲームアルバム（スーパードンキーコング2、ポケモンバンク、ポケモンスリープ、星のカービィ ベストセレクション、ロックマン2 サウンドコレクション、モンスターストライク オリジナルサウンドトラック）にもカバーを設定。
- **他のゲーム系アルバム98枚も対応**（KH由来でフォルダにあったcover画像をID3へ埋め込み72枚、KHから検索・取得して設定13枚。ポケモン各作・モンスターハンター・ドラゴンクエスト・カービィ・どうぶつの森・スマブラ等）。
- **残り8枚**（ドラクエII/IV、FF V、FF VIIアドベントチルドレン、スーパーマリオRPG、交響組曲DQライブベスト、めざせポケモンマスター、I Miss You — EarthBound 2012）はKHに該当リリースが無く、VGMdbはCloudflareで自動取得不可のため未設定（公式CDのジャケットを手動で用意するか、別ソースの許可が必要）。
- **2026-09-30: `00_未整理` の39曲を整理。
- ** アーティスト/アルバムフォルダへ移動（稲葉曇は既存アルバムへ統合、涼宮ハルヒのキャラソンは各キャラフォルダ、ボカロ系はシングル名アルバム）、artist/album/albumartist/tracknumberを正規化（「(CV.…)」除去）、ファイル名=曲名、カバーはAPLMate埋め込みを保持しcover.jpg/pngを配置。未完成の.crdownloadはゴミ箱へ。
- **歌詞はLRCLIB（lrclib.net API）で時報付き.lrcを取得**（32曲同期＋15曲はプレーン、うち3曲は歌ネット等からプレーン.lrcを手書き）。対象22フォルダは全mp3に.lrcが揃った（56曲）。
