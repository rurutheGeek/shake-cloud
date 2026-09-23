---
title: ドキュメントの書き方
updated: 2026-09-23
section: 入口
audience: 全員
tags:
  - hub
  - rules
---

# ドキュメントの書き方

> **更新日** 2026-09-23 ・ **区分** 入口 ・ **読む人** 全員

このハンドブックを書き足す・直すときの決まりです。**ルールの半分は `tests/test_docs_structure.py` が機械で検査します**ので、迷ったらテストを流してください。

```bash
python3 -m unittest tests.test_docs_structure
```

## 1. どこに書くか

区分は7つです。**「誰が、何のときに読むか」で決めます。** 扱うサービスや技術では決めません。

| 区分 | ディレクトリ | 置くもの |
| --- | --- | --- |
| 入口 | `docs/`（直下） | 案内板。このページ、[トップ](index.md)、[地図](map.md)、[開発参加ガイド](onboarding.md) |
| 利用ガイド | `docs/services/` | サービスを使う人向け。SSH・設定ファイルが出てこないもの |
| 開発計画 | `docs/development/` | 作業IDごとの計画と進捗 |
| 運用手順 | `docs/operations/` | 立ち上げ・配備・運用・復旧。実行する手順 |
| 設計 | `docs/architecture/` | なぜそう作ったか。決定と根拠 |
| リファレンス | `docs/reference/` | 引くための表。URL・用語 |
| 記録 | `docs/audits/` | ある時点の調査・監査。あとから更新しない |

迷いやすい境目:

- **手順か設計か** — 「実行する」なら運用手順、「なぜその形か」なら設計。`operations/bring-up.md` は初回構築の手順なので運用手順側にあります。
- **設計か決定ログか** — 検討の経緯と比較は設計の各ページ、**結論だけ**は[決定ログ](architecture/decisions.md)。決定ログは「理由なく蒸し返さない」ための場所です。
- **計画か台帳か** — これからやることは開発計画、実機でこうなったは[配備台帳](operations/handover.md)。**計画を書いたことを配備済みと扱いません。**

## 2. 正本をひとつにする

**同じ事実を2か所に書きません。** 片方が必ず腐ります。書こうとしている事実に正本があるなら、リンクするだけにしてください。正本の一覧は[ドキュメント地図](map.md)にあります。

食い違いを見つけたら、正本に合わせて他方を直します。正本の側が古いと分かったときだけ、正本を直します。

## 3. 前提が確定したら、待っている文書まで直す

**調べて答えが出たら、その答えを待っていた文書の「状態」行まで直してください。** 調べたページだけを更新すると、待っていた側は「未確認」のまま残り、次に読んだ人が**すでに答えの出ている調査をやり直します。**

実例があります。[N06 ルータ自作](development/N06-router.md)の調査で、回線が MAP-E で 80/443 が使えないこと、既存スイッチがアンマネージドで VLAN を設定できないことが確定しました。ところが答えは N06 の中だけにあり、それを前提にしていた N03・N04・N01 は「現有スイッチの対応を確認する」「回線の外部到達性を記録する」と書かれたままでした（2026-09-23 に修正）。

**リンクは張られているので、機械では見つかりません。** 到達性のテストは通ってしまいます。書く人が気をつけるしかない種類の腐り方です。

調べ物を終えたら、次を確認してください。

- その調査が**誰の前提だったか**。計画書の「依存と並列作業」「競合」に自分のIDが出てくる文書がそれです
- 相手の**「状態」行**（`**状態**:` / `**区分**:`）が、確定した前提と矛盾していないか
- [開発計画の一覧](development/index.md)の**状態（要約）列**。ここが実態と合っていないと、一覧を見ただけの人が誤解します
- 今後の判断を縛る事実なら、[決定ログ](architecture/decisions.md)にも1行足す

「計画（未着手）」と「機材待ち（調達が前提）」は、読む人にとって別物です。前者は着手できる、後者はできません。

## 4. ファイル名

| 区分 | 形 | 例 |
| --- | --- | --- |
| 開発計画 | `<ID>-<name>.md` | `W06-music-tools.md` |
| 記録 | `<対象>-<YYYY-MM-DD>.md` | `webgui-2026-09-12.md` |
| セクションの入口 | `index.md` | `services/index.md` |
| その他 | 内容が分かる英小文字とハイフン | `nextcloud-permissions.md` |

作業IDの記号は W（Web・メディア）・A（AI）・G（ゲーム）・H（家電）・N（ネットワーク）・I（基盤）・M（監視）・O（復旧・運用）・D（資料のみ）です。**番号は識別用で、実施順や優先度ではありません。**

## 5. ページの先頭

全ページが同じ形で始まります。両方とも必須です。

```markdown
---
title: 接続先一覧
updated: 2026-09-18
section: リファレンス
audience: 全員
tags:
  - reference
  - network
---

# 接続先一覧（URL・アドレス）

> **更新日** 2026-09-18 ・ **区分** リファレンス ・ **読む人** 全員
```

| 項目 | 決まり |
| --- | --- |
| `title` | H1と揃える。ナビゲーションの見出しとも揃える |
| `updated` | **内容が最後に変わった日。** 体裁を直しただけ、リンクが追従しただけでは動かしません |
| `section` | 上の7区分のどれか |
| `audience` | 利用者／開発者／管理者／管理者・開発者／全員 |
| `tags` | 先頭が区分タグ（`guide` `plan` `ops` `design` `reference` `record` `hub`）、続けて話題タグ |
| 引用のメタ行 | front matter の `updated`・`section`・`audience` と一致させる。サイト上で日付が読めるようにするため |

状態を書くページは、H1の下に `**状態**: …` の1行を置きます。区分を併記するときは `**区分**: … ・ **状態**: …` です。

## 6. MkDocs の制約

サイトは MkDocs の**既定テーマ（`mkdocs`）** で配備します。Material ではないので、次は使えません。

| 使えないもの | 代わりに |
| --- | --- |
| `!!! note` の admonition | 太字の1行か、引用（`>`） |
| content tabs | 見出しを分ける |
| `{#custom-id}`（attr_list） | 生のHTMLで `<a id="3-11"></a>` を見出しの直前に置く |
| 脚注、絵文字ショートコード | 本文に書く |

有効な拡張は MkDocs 既定の `toc`・`tables`・`fenced_code` だけです。表とコードフェンスが使えるのはこのため。

- **リンクは相対パスの Markdown リンク**（`../operations/handover.md`）にします。`[[wikilink]]` は MkDocs が解決できません。
- **図は ```mermaid のコードフェンス。** 同梱の `docs/assets/js/mermaid.min.js` がオフラインで描画するので、外部CDNへは繋ぎません。
- 新しいページは `mkdocs.yml` の `nav` へ必ず足します。**nav に無いページはサイトから辿れません**（テストが検査します）。
- MkDocs は**アンカーの存在を検証しません。** `#3-11` のようなリンクを書いたら、リンク先に `<a id="3-11"></a>` があるか確かめてください（テストが検査します）。

## 7. Obsidian

`docs/` をそのまま Vault として開けます。front matter のプロパティで絞り込め、相対リンクはグラフビューに出ます。[トップ](index.md)と[地図](map.md)が地図の中心（MOC）なので、**どちらからも辿れないページを作らないでください。**

## 8. 図を更新したとき

`docs/architecture/diagrams/` の図は、Mermaid原稿（`*.mmd`）と表示用SVG（同名）の両方をコミットします。SVGが静的なので、サイト表示時に外部CDNが要りません。再生成は管理環境で次を実行します。Mermaidの版とスクリプトのSHA-256はスクリプト内で固定しています。

```bash
python3 -m pip install playwright==1.62.0
python3 -m playwright install chromium --only-shell
python3 tools/render-architecture-diagrams.py
```

## 9. 出す前に流す検査

**テストを書き足すとき**は、命名規則・共通ヘルパ（`tests/support.py`）・一時ディレクトリの扱いを `tests/README.md` にまとめてあります。このページがドキュメントの規約であるのと同じ位置づけで、**テストの規約はそちらが正本**です。ここでは重複させません。

そこに1つ、このページを縛る決まりがあります。**ドキュメントへテスト件数を書かないでください。** すぐ古くなります。必要なら「`tests/test_<name>.py` が検査する」とファイルを参照します。

```bash
python3 -m unittest discover -s tests
python3 tools/docs-map.py          # 地図の全ページ一覧を作り直す
.venv/bin/mkdocs build --strict    # 未解決リンクがあれば失敗する
python3 tools/check-publication.py
```

`tools/docs-map.py --check` は地図が古いと失敗します。ページを足したら**先に `python3 tools/docs-map.py` を流してください。**

サイトへの配備は別操作です。GitHubへの push はサイトを更新しません。

```bash
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/docs-site.yml
```

`docs-site.yml` は静的インベントリ `seed.ini` で流します。動的インベントリだと対象なしで終わり、しかも終了コードは 0 です（[はまりどころ](operations/verify.md)）。

## 10. 書かないもの

Gitの `docs/` は公開リポジトリです。次は入れません。

- 実際のAPIキー・トークン・パスワード・Cookie・CA秘密鍵
- 個人用のIP台帳、DB接続文字列、アプリのセーブデータ、Kubernetes の Secret
- 生成物（`stacks/docs/site/`）と Terraform の state

**置き場所と取り出し方は書いてよい**（例: 「services-01 の `/opt/netbox-stack/secrets/` にある」）が、値そのものは書きません。暗号化して置くものは SOPS を使います（[秘密値の管理](operations/secrets.md)）。

公開前に、ステージした差分と `tools/check-publication.py` の結果を目視で確かめてください。

## 11. サイトを直接編集しない

**Gitの `docs/` が唯一の正本です。** 生成済みサイト（services-01 の配信ファイル）や、Nextcloud の `docs` フォルダーを編集しても、Gitへは戻りません。双方向同期も設けていません。変更は必ず Git 側から入れてください。
