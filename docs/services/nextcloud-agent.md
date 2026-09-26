---
title: Nextcloudファイルエージェント（AI用MCP）
updated: 2026-09-26
section: 利用ガイド
audience: 利用者
tags:
  - guide
  - nextcloud
---

# Nextcloudファイルエージェント（AI用MCP）

> **更新日** 2026-09-26 ・ **区分** 利用ガイド ・ **読む人** 利用者

状態: **media-01へ配備済み・稼働中**（`https://nextcloud-mcp.apextox.dpdns.org/healthz`が200）。**アプリパスワードでの実際のログイン確認はまだです**。うまく使えない場合は下の「困ったとき」を見るか管理者へ連絡してください。

opencode等のAIエージェントから、自分のNextcloudの中身を直接読み書きできる
ようにする機能です。Googleドライブ連携のように、エージェントに「このファイル
を読んで」「ここに書いて」「このzipを展開して」と頼めます。**Nextcloudの
アカウントを持っていれば誰でも使えます**（専用の申請は不要です）。

## できること

- ファイルの一覧・読み取り・書き込み・フォルダ作成・改名/移動・コピー・削除
- MP3のタグ編集（[タグ管理](tags.md)と同じ結果。バックアップ・MusicBrainz候補付き）
- zip/tarの作成と展開

すべての操作は**あなた自身のNextcloud権限**で行われます。共有されていない
フォルダには触れませんし、削除してもゴミ箱に入ります（Nextcloud標準の
30日ルールなどがそのまま適用されます）。

## 使えないこと・制限

- `music/Converted`（変換の原本）は書き換え・削除ができません（読み取りは可能）
- MP3タグの読み書きは`music`配下の`.mp3`だけです
- 圧縮ファイルはサーバー側で展開するため、非常に大きいzip/tarは時間切れになることがあります。大きい物はNextcloudのWeb画面から扱ってください

## 準備（アプリパスワード）

1. Nextcloudにログインし、右上のアイコン → **設定** → **セキュリティ** を開く
2. 「新しいアプリパスワードを作成」で名前（例: `opencode`）を付けて作成する
3. 表示されたパスワードを控える（**一度しか表示されません**。ログイン用の
   パスワードとは別物です）

**この環境は共通ログイン（Authentik）でサインインしているため、アプリ
パスワードが作れない/使えない場合があります。** その場合は管理者へ連絡して
ください（[管理者向け手順](../operations/nextcloud-mcp.md)にOIDCトークン方式への
切替が書かれています）。

## opencodeへの登録

`opencode.jsonc`にMCPサーバーとして追加します（`user:アプリパスワード`を
base64にしたものを`Authorization`へ渡します）。

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

```bash
# base64の作り方（アプリパスワードにコロンやスペースが無いことを確認してから）
printf '%s' 'あなたのユーザー名:アプリパスワード' | base64
```

**`opencode.jsonc`に平文の資格情報を書かないでください。** opencodeが対応
していれば`{env:NEXTCLOUD_MCP_AUTH}`のような環境変数参照を使ってください。

読み取りだけ使いたい場合は、opencode側の`tools`設定で書き込み系ツール
（`nextcloud_write_*`・`nextcloud_delete_*`・`nextcloud_move_*`・
`nextcloud_create_*`・`nextcloud_extract_*`）を個別に無効化できます。

## 使ってみる

登録後、エージェントに次のように頼めます。

- 「`/inbox`に何が入ってるか教えて」
- 「`music/YouTube/新曲.mp3`のアーティストを直して」
- 「`music/00_未整理`の中身を`archive.zip`にまとめて」
- 「`archive.zip`を`music/00_未整理`に展開して」

ファイルパスはNextcloudの「ファイル」画面に出るパス（先頭`/`の絶対パス、
例: `/music/YouTube/song.mp3`）と同じ形式で伝えると確実です。

## 困ったとき

- **401エラーが出る**: アプリパスワードが失効・削除されていないか確認してください（設定 → セキュリティ）
- **タグ編集が失敗する**: 対象が`music`配下の`.mp3`か、あなたにそのファイルの編集権限があるか確認してください
- 上記で解決しない場合は管理者へ連絡してください（[管理者向け手順](../operations/nextcloud-mcp.md)）
