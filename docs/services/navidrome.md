# Navidrome改造予定

Navidromeを今後いじりたい・改善したいと思っている点のメモです。

## タグ編集

Navidromeは読み取り専用で編集機能がありません。当面はNextcloudの **…** → **MP3タグを編集**（コメント欄=備考つき）と`organize.py --corrections`で補っています。本体に編集UIを足すのはAPIがないため上流待ちで、必要になれば自作アプリ側を広げます。

## 検索

検索できるのは曲名・アーティスト・アルバムだけです。**サブタイトル（VSラプソーン等）・コメント・作曲者は検索に出ません**。正式名称を崩さずに検索できるよう、本体の検索インデックス拡張（FTS）を追うか、[全曲アルバム確認](/review/)側で代替します。

## 文字のコピー

一覧のリンクやボタンに`user-select: none`が当たり、選択コピーがしにくいです。`stacks/media/navidrome/navidrome-copy.user.js`（Tampermonkey用）で対応済み。本体にカスタムCSSの口ができれば不要になります（[Issue #1311](https://github.com/navidrome/navidrome/issues/1311)）。

## 関連

- 使い方: [音楽・取り込み・タグ](music.md)、[タグ管理（MP3）](tags.md)
- 配備・経緯: [W05](../development/W05-navidrome.md)
