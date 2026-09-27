# ポケモン用語対応翻訳

状態: **実装のみ（2026-09-27）**。翻訳サイトの配備先・DNS・TLSは未決定で、配備していない。
拡張機能はサーバなしで使える。

原文中のポケモン・わざ・とくせい・どうぐ・タイプ・せいかく・ステータス・地名・
フォーム名を辞書で見つけて `⟦n⟧` に置き換えてから翻訳エンジンへ渡し、訳文の
`⟦n⟧` を訳先言語の公式名へ戻す。エンジンが「じしん」を「自信」、「Earthquake」
を「地震」と訳すような問題を避ける。

## 構成

```
core/poketr.js        照合・保護と復元・まとめ訳・Google翻訳の呼び出し（本体は1つ）
 ├─ site/index.html   翻訳サイト。ブラウザが core を読み、Google翻訳を直接呼ぶ
 └─ extension/        Chrome系ブラウザの拡張機能。core と辞書を同梱し、サーバ不要
dictionary.py         PokéAPI の CSV と custom-terms.json から辞書を作る
manage.py build       辞書・翻訳サイト一式・拡張機能（zip含む）を生成する
```

翻訳処理は `core/poketr.js` だけにあり、翻訳サイトと拡張機能は同じファイルを使う。
Google翻訳への通信は閲覧している人のブラウザから出るので、翻訳サイトのサーバは
静的ファイルを配るだけで、外部サービスへの通信が1台に集まらない。

| 生成物（Git管理外） | 内容 |
|---|---|
| `storage/pokeapi.json` | PokéAPI から取った公式名（`--refresh` まで保持） |
| `storage/site/` | 翻訳サイト一式と `poke-translate-extension.zip` |
| `extension/poketr.js`・`extension/dictionary.json` | 拡張機能に同梱するコピー |

対応言語は ja・en・ko・zh-TW・zh-CN・fr・de・es・it。日本語はかな表記を正とし、
漢字表記と全角英数を半角にした表記も別名として拾う。

## 翻訳エンジン

Google翻訳の**非公式**Webエンドポイント（`client=dict-chrome-ex` のGET）を使う。
無料・キー不要でブラウザから直接呼べる（`Access-Control-Allow-Origin: *`）が、
保証はなく、遮断や仕様変更で使えなくなりうる。その場合は理由を表示する。
公式APIやローカルLLMへ移るときは `core/poketr.js` に `translate(text, source, target)`
を持つクラスを足して差し替える。

## 辞書

公式名は PokéAPI（`manage.py` の `POKEAPI_REF` で版を固定）から作る。海外サイト
向けに次も生成する。

- `Landorus-Therian` 式のフォーム名 → ランドロス（れいじゅうフォルム）
- `Water-types`・`Tera Steel`・`Psychic immunity`（わざと同名のタイプを後ろの語で判別）
- `Jolly Nature`（Showdown形式）→ 性格: ようき
- ステータス名（こうげき〜すばやさ）

俗称・対戦用語・略記は [`custom-terms.json`](custom-terms.json) に書く。

```json
{"ref": "species:445", "ja": ["ガブ"]}
{"ja": ["S振り"], "en": ["Speed investment"]}
```

`ref` 付きは既存の用語に別名を足し、`ref` なしは新しい用語になる。各言語の最初の
名前がその言語での出力表記。`ambiguous` の語（英語の `Bold`・`Return` のように
普通の単語と重なる名前）は文頭では照合しない。`exclude` の語は照合しない。
ひらがな2文字以下の名前（「くさ」「みず」）は単独では照合せず、「くさタイプ」の
形だけを拾う。同名のときは カスタム > ポケモン > わざ > とくせい > どうぐ > タイプ
の順に採る。変更したら `manage.py build` で作り直す。

## 翻訳サイト

`site/index.html`。文章を貼って訳す。「用語だけ置き換え」にすると Google翻訳へ
送らず、Showdown形式の型などの用語だけを日本語名にする。ページ下部から拡張機能の
zipを配る。

## 拡張機能

Chrome・Edge・Brave・Vivaldi（Android版を含む）向けの Manifest V3 拡張機能。
ツールバーのボタンか `Alt+T` で、見ているページの段落を原文の直下に訳す（対訳
表示）。原文のリンクや書式は触らない。もう一度押すと「訳のみ」「原文のみ」「対訳」
と切り替わる。スクロールで増える投稿なども自動で訳す。`<pre>`（Showdown形式の型
など）は訳さず用語だけ置き換え、コード・入力欄は触らない。

段落は約3,500文字ずつ区切り記号 `⟦0⟧` でまとめて1回で訳し、同時に送るのは2件
までにして遮断されにくくしている。通信先は `translate.googleapis.com` だけで、
閲覧中のページへは押したときだけ一時的に権限を得る（`activeTab`）。

入れ方:

1. `python3 manage.py build` で `extension/` に辞書と本体を同梱する
   （翻訳サイトを配備していれば、そこから zip を取ってもよい）。
2. PC: `chrome://extensions`（Vivaldi は `vivaldi://extensions`）でデベロッパー
   モードを有効にし、「パッケージ化されていない拡張機能を読み込む」で `extension/`
   を選ぶ。
3. スマホ: zip を展開したフォルダを、同じくデベロッパーモードから読み込む。

辞書や本体を変えたら、`build` し直して拡張機能を再読み込みする。

## 操作

```bash
python3 manage.py build             # 辞書・翻訳サイト・拡張機能を生成（PokéAPIは初回だけ取得）
python3 manage.py build --refresh   # POKEAPI_REF の公式名を取り直す
python3 manage.py up                # 生成してから翻訳サイトを 127.0.0.1:5830 で起動
python3 manage.py status
python3 manage.py down
```

テストは `python3 -m unittest tests.test_poke_translate`。本体（`core/poketr.test.js`）
のテストは `node` があるときに実行する（CIは Node.js を入れて実行）。
