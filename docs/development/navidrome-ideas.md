---
title: Navidrome改造予定
updated: 2026-09-18
section: 開発計画
audience: 開発者
tags:
  - plan
  - navidrome
---

# Navidrome改造予定

> **更新日** 2026-09-18 ・ **区分** 開発計画 ・ **読む人** 開発者

Navidromeを今後いじりたい・改善したいと思っている点のメモです。

## タグ編集

Navidromeは読み取り専用で編集機能がありません。当面はNextcloudの **…** → **MP3タグを編集**（コメント欄=備考つき）と`organize.py --corrections`で補っています。本体に編集UIを足すのはAPIがないため上流待ちで、必要になれば自作アプリ側を広げます。

## 検索

検索できるのは曲名・アーティスト・アルバムだけです。**サブタイトル（VSラプソーン等）・コメント・作曲者は検索に出ません**。正式名称を崩さずに検索できるよう、本体の検索インデックス拡張（FTS）を追うか、[全曲アルバム確認](/review/)側で代替します。

## 歌詞の表示

`.lrc` はサーバー側に読み込まれ、対応クライアント（OpenSubsonicの歌詞API）では表示できます。Web UIの歌詞表示はバージョンによって差があり、0.64.0で改善を取り込みました。歌詞がある曲は [歌詞あり一覧](/review/lyrics-found.html) で確認できます。

## 文字のコピー

一覧のリンクやボタンに`user-select: none`が当たり、選択コピーがしにくいです。`stacks/media/navidrome/navidrome-copy.user.js`（Tampermonkey用）で対応済み。本体にカスタムCSSの口ができれば不要になります（[Issue #1311](https://github.com/navidrome/navidrome/issues/1311)）。

## 関連

- 使い方: [音楽・取り込み・タグ](../services/music.md)、[タグ管理（MP3）](../services/tags.md)
- 配備・経緯: [W05](W05-navidrome.md)

## 歌詞をWeb UIで表示する（2026-09-17 解決）

Navidrome 0.64のWebプレイヤーは、曲レコードの歌詞のうち **同期歌詞（`synced: true`）だけ**をLRCに変換して表示します（UIバンドル内の変換コードが `i.synced` の項目しか使わない）。外部`.lrc`はAPI（`getLyricsBySongId`）では同期で返るものの、DBの`lyrics`列には非同期として保存されるため、UIでは「歌詞がありません」になっていました。

対策として、`.lrc`の内容を**SYLT（同期歌詞のID3タグ）としてMP3に埋め込み**ました。再スキャン後は認証情報やユーザースクリプト無しでWeb UIに歌詞が表示されます（2026-09-17 メンタルチェンソーで表示確認）。`.lrc`はそのまま残しています。

- 埋め込み: `embed_sylt.py`（バックアップは `storage/convert/organize/sylt-backups/`）
- プレーンな`.lrc`の同期版再取得: `lyrics.py` に `LYRICS_REFRESH_PLAIN=1`（同期版が取得できたときだけ置換）
- 現状: 歌詞あり555曲中、UI表示可358曲。残り197曲はLRCLIBに同期歌詞が無く表示不可（非同期歌詞自体はSubsonicアプリでは表示可能）
- ライブラリ全体では1293曲が元々歌詞なし（BGM・クラシック等）なので、UIで歌詞が出ないのが正常な曲が多数
