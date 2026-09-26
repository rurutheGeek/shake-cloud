---
title: W06 MeTube・音楽変換・タグ編集のmedia-01移行
updated: 2026-09-16
section: 開発計画
audience: 開発者
tags:
  - plan
  - music
---

# W06 MeTube・音楽変換・タグ編集のmedia-01移行

> **更新日** 2026-09-16 ・ **区分** 開発計画 ・ **読む人** 開発者

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
