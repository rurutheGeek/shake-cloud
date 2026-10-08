---
title: W10 Nextcloudの画像OCR検索（ocr_search）
updated: 2026-10-08
section: 開発計画
audience: 開発者
tags:
  - plan
  - nextcloud
  - ocr
---

# W10 Nextcloudの画像OCR検索（ocr_search）

> **更新日** 2026-10-08 ・ **区分** 開発計画 ・ **読む人** 開発者

種別: **実装＋資料**。状態: **GitHubへ公開（リリース `v0.1.0`）し、media-01へ配備済み（2026-10-08）。実機で既存画像の索引・検索・新規アップロードの自動索引・メモリを確認。ブラウザーでの表示確認とレシート類での精度確認が残る**。

[開発計画一覧](index.md)へ戻る。番号は実施順を表しません。

## 目的

Nextcloudの統合検索から、画像の中の文字（レシート、レシピ、スクリーンショットなど）で画像を探して開けるようにします。ImmichのOCR検索に相当するものを、Nextcloudの中で軽く完結させます。アプリはNextcloudアプリストアへの公開を前提に、独立した公開リポジトリで開発します。

- アプリと認識サービス: 公開リポジトリ `rurutheGeek/nextcloud-ocr-search`（アプリID `ocr_search`、認識サービスは同リポジトリの `server/`）
- 配備先: **media-01**（Nextcloudと同じComposeプロジェクト `media-nextcloud`）
- このリポジトリが持つもの: 配備（`stacks/media/nextcloud/`・`platform/ansible/media-nextcloud.yml`）、テスト、資料

## 要件と受入条件

| 要件 | 実現方法 | 確認 |
| --- | --- | --- |
| 日本語と英語を認識する | PP-OCRv5 mobile（RapidOCR＋ONNX Runtime） | 実写真6枚で確認（下表） |
| 既存画像の一括索引 | `occ ocr_search:index`＋`ocr_search:process`。夜間のsystemd timer | 実機で `/inbox/ocr` の6枚を索引（2026-10-08）。全体は夜間timerが処理 |
| 新規・更新画像の自動索引 | ファイルイベントでキューへ1行追加し、Nextcloudのcronジョブが5分ごとに処理 | 実機でWebDAVアップロードから約190秒後に検索に出た（2026-10-08） |
| アクセスできないファイルを検索結果に出さない | 利用者のマウント（storage）で絞り、最後に利用者自身のファイルビューで1件ずつ確定 | 結合テスト（未共有は出ない・共有した1枚だけ出る・共有解除で消える） |
| メモリが軽い（常駐1GiB未満） | `mem_limit: 1g`・`cpus: 2`・同時実行1・長辺1024pxへ縮小・待機5分でモデル解放 | 実機のピーク424MiB、待機時25MiB（モデル読み込み前）〜約160MiB |
| 認識テキストをコピーできる | Filesのサイドバーに「文字」タブとコピーボタン | 実機は未 |
| OCR停止時もアップロード・閲覧を壊さない | アップロード時はDBへ1行入れるだけ。Nextcloudは認識サービスに依存しない | 結合テスト（停止時は試行回数を消費せず待機） |
| 一括索引を任意の時刻に実行でき、負荷を制限できる | 一括分はcronジョブでは処理せず、`ocr_search:process --max-runtime` だけが処理する | 結合テスト |

## 構成

```
アップロード・更新 ─▶ ocr_search がファイルIDをキューへ（DBへ1行）
                           │
cronコンテナ（5分ごと） ───┤ Nextcloud経由で画像を読む
夜間timer（occ process） ──┘      │ POST /v1/ocr（共有トークン）
                                  ▼
                        ocrコンテナ（状態なし・ポート非公開）
                                  │ 行ごとの文字と座標
                     NextcloudのDB（oc_ocr_search_index）
                                  │
統合検索 ─▶ 正規化した本文への部分一致 ─▶ 1件ずつアクセス確認
```

- **認識サービス**はファイルもDBも見ません。専用のinternalネットワーク `ocr` に置き、`nextcloud` と `cron` だけが届きます。モデルはイメージに同梱し、実行時はネットワーク不要・読み取り専用・非rootです。
- **イメージ**はリリースのソース（`server/`）からmedia-01でローカルビルドし、`ocr-search-service:<バージョン>` のタグを付けます。バージョンの正本は `group_vars/media.yml` の `nextcloud_custom_apps` の1行で、アプリと認識サービスを同時に上げます。
- **共有トークン**は `manage.py init` がmedia-01上で `secrets/ocr_token` に生成し、認識サービスにはファイルで、アプリには `manage.py config-ocr` が `occ` で渡します。SOPSには置きません（media-01の外へ出ない値のため）。
- **索引**は `file_id` を主キーに、本文・正規化本文・行ごとの座標・etag・状態・試行回数・最終エラーを持ちます。
- **検索**は正規化した本文への部分一致（LIKE）です。語を空白で区切るとAND検索になります。
- **再試行**: 認識サービスに届かないときは試行回数を消費せず、その回の処理を止めます。画像固有の失敗は5分・20分・80分・5時間20分の間隔で5回まで試し、その後 `failed` にします（`occ ocr_search:retry-failed` で戻せる）。
- **除外**: フォルダに `.noocr` を置くと、その下を索引しません。管理設定で画像の種類・最小／最大サイズを変えられます。

### 正規化（索引する本文と検索語の両方にかける）

| 変換 | 例 |
| --- | --- |
| 全角・半角と大文字・小文字 | `ＡＢＣ`→`abc`、`ﾎﾟｹﾓﾝ`→`ポケモン` |
| 濁点・半濁点を落とす | `ゲーム`と`ケーム`を同じに扱う |
| 旧字体・簡体字・繁体字を新字体へ | `內`→`内`、`產`→`産`、`东`→`東` |
| 形が同じ文字 | `力`（漢字）と`カ`（カタカナ）、`一`と`ー` |
| 小書きのかな | `っ`→`つ` |
| 空白・改行・句読点をすべて除く | 「文字」タブからコピーした文が、行の切れ目に関係なく当たる（0.1.1） |

## エンジンの選定（2026-10-07実測）

media-01上の `--memory=1g --cpus=2` のコンテナで、Nextcloudの `inbox/ocr` の実写真6枚（画面の接写、縦書きの賞状、手書きメモ2枚、イラストの題字、ゲーム画面の字幕）を測りました。

| エンジン・設定 | 秒/枚 | ピークメモリ |
| --- | --- | --- |
| RapidOCR（PP-OCRv5 mobile）長辺1600px | 0.41 | 706MiB |
| RapidOCR（PP-OCRv5 mobile）長辺1024px | 0.26 | 392MiB |
| Tesseract 5.5 `jpn+eng` | 0.82 | 約220MiB（子プロセス込み） |

- Tesseractは活字のスクリーンショット以外をほぼ読めず、記号の屑の行を大量に出したため不採用。
- 長辺1024pxと1600pxで精度はほぼ同じだったため、既定は1024px（`OCR_MAX_SIDE`）。
- 縁取りのある装飾文字と大きな手書きは弱い（v1の限界）。
- **レシート・レシピの写真では未測定**。細かい活字が1024pxで読めない場合は `OCR_MAX_SIDE` を上げる（1600pxでも1GiBに収まる）。

## 変更範囲

- `stacks/media/nextcloud/compose.yaml`: `ocr` サービスとinternalネットワーク `ocr`、秘密値 `ocr_token`。
- `stacks/media/nextcloud/manage.py`: `ocr-service`（リリースのソース取得）、`config-ocr`（アプリへURLとトークンを設定）、`ocr-index`（夜間の一括索引）。`init` が `ocr_token` を生成する（既存の秘密値は上書きしない）。
- `stacks/media/nextcloud/media-stack-ocr-index.{service,timer}.j2`: 毎晩2:30に最大2時間。時刻と上限は `group_vars/media.yml` の `nextcloud_ocr_index_calendar`・`nextcloud_ocr_index_max_runtime`。
- `platform/ansible/media-nextcloud.yml`: アプリ導入、ソース取得、設定、timerの配備。
- `tests/test_media_nextcloud.py`: `OcrServiceTests`。

## 依存関係・並列作業

- 前提: W03のNextcloud（media-01、配備済み）。
- media-01は他のメディアサービスと同居する。認識の負荷は `ocr` コンテナの上限（2CPU・1GiB）で抑え、一括索引は夜間に限る。
- アプリストアへの公開は、証明書の申請（`nextcloud/app-certificate-requests`）とリポジトリ変数 `APPSTORE_ENABLED` の設定後に、リリースのワークフローが行う（`cups_print` と同じ流れ）。

## 検証・完了条件

- [x] 実写真で日本語の検索が当たる（使い捨てのNextcloud 33＋実物の認識サービスで、6枚中4枚の代表語が当たることを確認）
- [x] 未共有の他人のファイルが検索結果に出ない（結合テスト）
- [x] 常駐メモリ1GiB未満（実測ピーク359MiB）
- [x] テスト・lint（アプリ側: PHP 31件・認識サービス19件、こちら側: `tests.test_media_nextcloud`）
- [x] GitHubへ公開し、リリース `v0.1.0` を作る（CI通過）
- [x] media-01へ配備し、新規アップロードが自動で索引されることを実機で確認する（2026-10-08。アップロードの応答は0.19秒、約190秒後に索引）
- [x] 実機で既存サービスへの影響がないこと（メモリ・応答）を確認する（`ocr` のピーク424MiB、他コンテナは配備前と同水準、Nextcloudは200応答）
- [x] 実機（PostgreSQL）の統合検索APIで実写真が当たる（「ゲームを早く」「ポケモンの力」「クリスマス サンタ」「新宿山吹」）
- [ ] 実機のブラウザーで統合検索の表示とサイドバーの「文字」タブを確認する
- [ ] レシート・レシピの写真で精度を確認する

共通の確認は `.venv/bin/python -m unittest discover -s tests` と `.venv/bin/mkdocs build --strict`。

## 実装メモ

- **media-01のメモリ下限に余裕がない（2026-10-08）。** Proxmoxホストのメモリ使用率が80%を超えるとバルーニングで各VMが下限まで絞られ、media-01は `memory_min_mib` の2048MiBになる。常用が約1.5GiBなので、`ocr` のピーク（約420MiB）が重なると不足しうる。同日、ストア用スクリーンショットの撮影（使い捨てのNextcloud・OCR・ヘッドレスブラウザーをmedia-01で同時に動かした）で全体のOOMが起き、Kavitaが1回強制終了した（自動再起動）。対策として `ocr` に `oom_score_adj: 500` を付け、夜間timerはメモリ下限を見直すまで止めている。**media-01で検証用のコンテナを複数同時に動かさない。**
- **統合検索は画面右上（ヘッダー）の虫めがね**。Filesの左メニューの検索欄の「あらゆるところで検索」はFiles自身のファイル名検索（WebDAVのSEARCH）で、アプリの検索プロバイダーは呼ばれない（2026-10-08、利用者の報告とアクセスログで確認）。
- 0.1.0は日本語の文字の間の空白だけを除いていたため、句読点や数字の直後で行が切れた文をコピーして探すと当たらなかった。0.1.1で空白と句読点をすべて除き、更新時の修復ステップ（`Renormalize`）が既存の索引を作り直す（再認識は不要）。
- AppAPI／ExAppは採らず、アプリ設定に認識サービスのURLを持たせた（依存を増やさず、Composeだけで完結させるため）。
- 検索の権限確認は2段階。storageで絞るだけでは、共有された一部のフォルダーだけがマウントされている場合に持ち主の他のファイルまで候補に入るので、最後に利用者のフォルダーから `getFirstNodeById` で引けたものだけを返す。
- アップロード中のイベントでは `insertIgnoreConflict` を使う。PostgreSQLはトランザクション内のINSERT失敗で後続を巻き込むため、重複で例外を出さない。
- 認識中に同じファイルが書き換えられた場合、結果は保存せずキューに残す（claimの値で判定）。
- NC33のサイドバーのタブは `@nextcloud/files` v4 の `registerSidebarTab`（Web Component）で登録する。
- テストは `nextcloud:33-apache` の使い捨てコンテナにSQLiteで導入して実行する（アプリ側リポジトリの `tests/run.sh`）。
