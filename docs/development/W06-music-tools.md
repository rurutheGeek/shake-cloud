# W06 MeTube・音楽変換・Picardのmedia-01移行

更新日: 2026-09-12。これは開発計画であり、配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **PicardのWeb GUIをmedia-01へ先行配備済み（2026-09-12）。MeTube・変換・同期の移行は未了**。Picardは `https://picard.apextox.dpdns.org`（Let's Encrypt・Authentik Forward Auth）で公開済み。

`stacks/music-tools/compose.yaml` にMeTube・変換・タグ編集があり、`platform/ansible/music-tools.yml` と同期タイマーが存在する。[音楽手順](../services/music.md)では共有Cookieの実物未登録・対象URL取得未確認を区別している。Picardはメディアの音楽導線（MeTubeの取込 → Nextcloudの共有music → タグ付け → Navidromeの表示）のGUIとして、同じComposeへWeb GUIコンテナ（`jlesage/musicbrainz-picard`）で追加する。導線の資料は[D05](D05-picard.md)。

**先行配備（2026-09-12）:** media-01の `/opt/media-stack/music-tools` に一式を置き、`manage.py init` と `docker compose up -d --wait picard` だけを実行した。`127.0.0.1:5800` でHTTP 200、コンテナはhealthy。MeTube・変換・同期・共有Cookieはまだmedia-01へ移していないため、ライブラリは空のままとし、実データの切替は行っていない。

配備先: **media-01**。開発先は既存 `stacks/music-tools/`。`stacks/media/` は配置の案内と原本の共通規約を担当する。

## 実装手順

1. 既存lockと変換コードを再利用し、music原本・Converted・動画・一時領域・変換状態・Cookieの配置と権限を移す。再開時の重複変換・原本上書きを防ぐ。
2. Picard（`jlesage/musicbrainz-picard`、digest固定）を同じComposeに追加する。共有musicだけを書き込み可能でマウントし、`/config` は `storage/picard` へ分離する。GUIは `127.0.0.1:${PICARD_PORT:-5800}` に閉じ、SSH転送または既存SSOの認証プロキシ経由で使う。BCSTM原本と `music/Converted/` を直接編集しない。
3. 既存の[旧メディアSSO](../services/sso.md)を再利用し、[identity](../operations/identity.md)へ統合する。旧 `media-users` / `homarr-admins` と新 `users` / `admins` の対応、issuer・subject変更時の既存アカウントの紐付けを検証し、メール一致だけで別人のデータを結び付けない。MeTubeは共有キュー・共有Cookieとして運用し、秘密値は対象ホストへ配る。Nextcloud/Navidromeへの同期処理とPicardの入口を新配置に合わせる。
4. 旧キューを止め、未完了ジョブと変換状態を保全して復元する。旧同期タイマーを停止し、新タイマーを一つだけ有効にして少数ファイルから切り替える。Picardのタグ保存と変換・同期が同じファイルを同時に触らない順序にする。

## 依存と並列作業

- 開発開始: なし。手元のサンプル音声・BCSTMと模擬取得結果で変換・同期を検証する。
- 配備・切替: [I02](I02-media-vm.md)、[I01](I01-resources.md)、[N05](N05-https.md)。結合確認は[W03](W03-nextcloud.md)/[W05](W05-navidrome.md)、対象URLの検証は使用可能なURLと必要な共有Cookieの用意後。Picardの入口は[W05](W05-navidrome.md)・[W03](W03-nextcloud.md)と調整する。
- 競合調整: W03/W05とmusicパスと同期の唯一の実行者を決める。[D05](D05-picard.md)のタグ保存と同じファイルを同時更新しない。大規模変換は負荷測定と調整する。

## 検証・完了条件

- 許可された音源の取得、音声/動画の保存先分離、BCSTM変換、タグ編集のプレビューと保存を確認する。
- PicardのWeb GUIでLookup／Scan→確認後Saveが通り、NextcloudとNavidromeに追加が反映される。BCSTM原本と `music/Converted/` を直接編集していない。
- 再起動・途中失敗からの再試行で二重登録や原本破損がない。
- 共有CookieはGit・ログに出ず、未認証者はMeTube・Picardを利用できない。状態・設定の復元を確認し、外部取得未確認は未確認のまま記録する。

## 実装記録

- 2026-09-12: Picard Web GUI（`jlesage/musicbrainz-picard`、digest固定、`127.0.0.1:5800`）を media-01 へ手動SSHで先行配備。HTTP 200・healthy。MeTube・変換・同期・共有Cookieは未移行。
- 2026-09-12: `platform/ansible/music-tools.yml` を拡張し、Ansibleで再現可能にした。`music_tools_services` でサービスの段階配備（例: `-e music_tools_services=picard`。複数はカンマ区切りかJSONリスト）、`music_tools_sync_enabled` で同期タイマーの有効/無効を制御する。既定は全サービス・同期有効で、既存ホストの再実行の挙動を変えない。手動SSHは先行配備の一時手段であり、media-01の状態は playbook を再適用して収束させる。配備・Picardの使い方は `stacks/music-tools/README.md` を参照。
