# タグ管理（MP3）

`music` のMP3タグを「手で直す」「まとめて自動で整える」ための入口をまとめます。項目の意味は[Nextcloudの使い方](nextcloud-guide.md)の「MP3タグ（ID3）の主な項目」を参照してください。

## 手で直す（Nextcloud）

- `music` のMP3の **…** → **MP3タグを編集**（Nextcloud標準の「タグ」とは別機能）
- 曲名・アーティスト・アルバム・アルバムアーティスト・トラック/ディスク番号・年・ジャンル・**コメント（備考）** を編集可能。**MusicBrainzで検索** で候補入力
- 変更前のタグはmedia-01の `/opt/media-stack/music-tools/storage/tags/tag-backups/` に保存
- Navidromeへの反映は通常1時間以内

## まとめて整える（organize.py）

`アーティスト/アルバム/NN - 曲名.mp3` への整理・リネームとタグ付け、カバー取得をまとめて行います。詳細は[music-toolsのREADME](https://github.com/rurutheGeek/shake-cloud/blob/main/stacks/music-tools/README.md)。

```bash
# 1) 計画（/musicは変更しない）
sudo docker compose ... run --rm --entrypoint python3 tagger /tools/organize.py plan \
  --aliases /tools/organize-aliases.json
# 2) report.md と manifest.json を確認
# 3) 適用（ID3バックアップ・移動ジャーナル付き）
sudo docker compose ... run --rm --entrypoint python3 tagger /tools/organize.py apply \
  --manifest /state/organize/manifest.json --cleanup
# 4) 取り消し
... /tools/organize.py undo --journal /state/organize/journal-<日時>.json
```

- `--no-lookup`: MusicBrainzで上書きせず、既存タグだけから再整理（手修正後の再実行向け）
- `--corrections FILE`: ファイル単位のタグ上書き（`{"files": {"<相対パス>": {"album": "..."}}}`）。手修正やレビュー結果の反映に使う
- `--no-covers`: カバー取得をしない（タグだけ変えるとき用。短時間で終わる）

## 自動ツール（stacks/music-tools/）

| ツール | 用途 | 備考 |
| --- | --- | --- |
| `organize.py` | 整理・タグ・カバー・undo | plan/apply/undo。`--corrections`で個別上書き |
| `make-review-html.py` | 全曲アルバム確認HTML | コメント入力→CSV出力。`https://navidrome.apextox.dpdns.org/review/`（SSO）で閲覧 |
| `lyrics.py` | 歌詞（`.lrc`）取得 | LRCLIB。既存`.lrc`は保持。曲名のみ検索も試す |
| `genres.py` / `genres-album.py` | ジャンル推定・アルバム単位で統一 | 既存タグ優先＋キーワード |
| `composers.py` | 作曲者（TCOM）補完 | Soundtrack/Game/Classicalはアルバムアーティスト＝作曲者 |
| `strip-embedded-art.py` | 埋め込みAPIC削除 | 画像は `storage/convert/organize/apic-backups/` に保存 |
| `strip-itunes-comments.py` | iTunesの`iTunSMPB`コメント削除 | コメント欄に出る謎の16進数を除去。バックアップは `storage/convert/organize/itunes-backups/` |
| `edit-tags.py` | JSONマニフェスト式のタグ編集 | 旧来の一括編集 |

自動ツールは `plan --no-lookup --corrections <出力JSON>` → `apply` の順で反映するのが基本です（ジャンル/作曲者/歌詞も同様）。歌詞は `.lrc` を直接置くため、実行後にNavidrome/Nextcloudのスキャンが必要です。

レビューCSVのコメント欄は自由記入です。1セルに複数の指示（曲名＋作曲者＋「アルバム未収録」など）を混ぜると誤適用の原因になります（2026-09-18、コメントの指示文がそのままアルバム名等になる644件を修正）。

## ジャンルの方針

- ゲーム本編で使われた音源・ゲーム内アレンジ: `Soundtrack`
- ゲーム外のアレンジ（コンサート・ピアノ・ジャズ・リミックス・同人アレンジ）: `Arrange`
- ボカロ/ネット曲: `Vocaloid`、アニメ: `Anime`、クラシック: `Classical`、海外ポップス系: `Pop`/`Rock`/`Punk`/`Hiphop`/`Jazz` など
- 詳細ジャンル（J-Rock、City Pop等）はMusicBrainzのジャンルから追加できます

## ネット限定・アルバムが無い曲

- 配信リリースしか無い曲は、分かる範囲で**配信リリース名をアルバム**にします（例: `エイリアンエイリアン`、`GETCHA! (feat. 初音ミク & GUMI)`）
- アルバムが特定できない単曲は `アーティスト/Singles/` に置きます
- アレンジものはジャンル `Arrange` を付けます。見つけた良いアレンジはこの方針で追加してください

## バックアップと復元

- タグ: `storage/tags/tag-backups/`（Nextcloud編集）、`storage/convert/organize/tag-backups/`（organize.py）
- 移動: `storage/convert/organize/journal-*.json` → `organize.py undo` で戻せる
- 埋め込み画像: `storage/convert/organize/apic-backups/`
- 音声本体のバックアップは別途必要です（[O03](../development/O03-restore.md)）

## タグ付け方針（迷ったときの基準）

- **曲名 (title)**: 原題を優先（日本語があれば日本語）。`feat.` や `〜` はそのまま。ゲーム曲で曲名から分からない場合は**コメント**に「vs ○○」などを書く
- **アーティスト (artist)**: 演奏・歌唱した人。ボカロ曲は**ボカロ名**（初音ミク等）、プロデューサーはアルバムアーティスト/作曲者へ。BGM等で歌唱・演奏者がいない曲は作曲者（またはアルバムアーティスト）を入れる（`Unknown Artist`回避。2026-09-18に626曲補完）
- **アルバム (album)**: **原典**（その曲が最初に収録されたリリース）。ゲーム曲は「元ファイルが入っていた作品のサントラ」。企画盤・ベスト盤より原典を優先
- **アルバムアーティスト (albumartist)**: リリースのクレジット。ゲームは作曲者（例: すぎやまこういち）または Various Artists、ボカロはプロデューサー名
- **表記揺れ**: アーティスト名は公式表記に統一（例: `ゲスの極み乙女。`、`Finishing Move Inc.`）。ローマ字表記・訳名・略称を混在させない
- **作曲者 (composer)**: 分かる場合のみ（Soundtrack/Game/Classicalは自動補完済み）
- **ジャンル**: ゲーム本編→`Soundtrack`、ゲーム外アレンジ→`Arrange`、ボカロ/ネット→`Vocaloid`、アニメ→`Anime`、クラシック→`Classical`、洋楽系は `Pop`/`Rock`/`Punk`/`Hiphop`/`Jazz` 等
- **コメント (comment)**: 備考欄。別名や「誰と戦う曲か」など
- **歌詞**: `.lrc` サイドカー（自動取得）または埋め込みUSLT

## 新しく曲を追加するときの置き場所

| 入手元 | 置き場所 | 手順 |
| --- | --- | --- |
| YouTube等のURL | `music/YouTube/`（MeTubeが自動保存） | MeTubeで追加 → 必要なら organize.py で整理 |
| KHInsiderのアルバム | `music/Khinsider/<アルバム名>/`（KHInsiderツールが自動保存） | 取り込み後に organize.py で整理 |
| 手元のファイル・CD rip | `music/inbox/`（無ければ作成） | アップロード → `organize.py plan` → 確認 → `apply` |
| ネット限定・配信のみ | 同上 | 配信リリース名をアルバムに。分からなければ `Singles` |

追加後の基本の流れ:

```bash
# 1) 追加（MeTube/KHInsider or music/inbox へアップロード）
# 2) 計画（MusicBrainz照合。見つからない曲は既存タグ/ファイル名で整理）
sudo docker compose ... run --rm --entrypoint python3 tagger /tools/organize.py plan \
  --aliases /tools/organize-aliases.json
# 3) report.md を確認して適用
sudo docker compose ... run --rm --entrypoint python3 tagger /tools/organize.py apply \
  --manifest /state/organize/manifest.json
# 4) 反映（タイマーが動いていれば自動。止めている場合は手動で）
sudo docker exec media-navidrome-navidrome-1 /app/navidrome scan -f
sudo docker exec -u www-data media-nextcloud-nextcloud-1 php occ files:scan --path=admin/files/music
```

## ネット限定曲・メタデータの調べ方

- 配信だけの曲は配信リリース名をアルバムにします（例: `GETCHA! (feat. 初音ミク & GUMI)`）
- ボカロ曲は [VOCALOID楽曲wiki（hmiku）](https://w.atwiki.jp/hmiku/pages/43320.html) のような一覧Wikiで、曲名・作曲者・初出を確認できます（マオの例）。見つけた情報はNextcloudのMP3タグ編集か、レビューCSV→`--corrections`で反映してください
- ウィキからの自動取得は行いません（規約・表記ゆれのため）。必要になったら個別に対応を検討します
