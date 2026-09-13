# W06 MeTube・音楽変換・タグ編集のmedia-01移行

更新日: 2026-09-12。これは開発計画であり、配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **media-01 で MeTube・変換・タグAPIが稼働し、Nextcloudの「タグを編集」から読み書きできる（2026-09-13）。同期タイマーは停止中で、切替が残る。タグ編集をNextcloudへ統合したためPicardは撤去した**。

`stacks/music-tools/compose.yaml` にMeTube・変換・タグAPIがあり、`platform/ansible/music-tools.yml` と同期タイマーが存在する。[音楽手順](../services/music.md)では共有Cookieの実物未登録・対象URL取得未確認を区別している。タグ編集はNextcloudの自作アプリ `shake_tags` が同スタックのタグAPI（`:5810`・MusicBrainz検索つき）を使う。導線の経緯は[D05](D05-picard.md)。

**配備（2026-09-12〜13）:** media-01の `/opt/media-stack/music-tools` に一式を置き、Ansible（`music-tools.yml`）で MeTube・変換・タグAPIを配備した。同期タイマーは切替まで停止している。共有Cookieは未登録のためYouTubeの実URL取得は未確認（Cookie不要のURLでMeTube→`music/YouTube`着地は確認済み）。

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
