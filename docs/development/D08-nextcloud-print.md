---
title: D08 Nextcloudからの印刷（cups_print）
updated: 2026-09-26
section: 開発計画
audience: 開発者
tags:
  - plan
  - nextcloud
  - print
---

# D08 Nextcloudからの印刷（cups_print）

> **更新日** 2026-09-26 ・ **区分** 開発計画 ・ **読む人** 開発者

種別: **実装＋資料**。状態: **印刷アプリを公開リポジトリ `rurutheGeek/nextcloud-cups-print`（`cups_print`）へ切り出し、media-01はGitHub Releaseから導入。実印刷・ダイアログ（部数/カラー/ページ範囲）・Markdown印刷を実測済み（2026-09-26）**。

[開発計画一覧](index.md)へ戻る。番号は実施順を表しません。

## 目的・現状の根拠

Nextcloudのファイル一覧から直接印刷できるようにします。ストアの印刷アプリ（Printer・SkyPrint）はNC33非対応で、NextcloudコンテナへのCUPSクライアント追加が前提のため採用せず、**自作の小さなアプリ**とservices-01の印刷APIで構成しました。

- アプリ: 公開リポジトリ [`rurutheGeek/nextcloud-cups-print`](https://github.com/rurutheGeek/nextcloud-cups-print)（`cups_print`）。Filesの「…」→「印刷」（PDF・PNG・JPEG・テキスト・Markdown、ダイアログで部数・カラー・ページ範囲）
- API: `stacks/print-api/`（`print_api.py`・systemdユニット）。`:6320`・トークン認証・media-01からのみ
- トークン: `platform/sops/print-api.sops.yaml`（CUPSロールとNextcloud配備が読む）
- 配線: `platform/ansible/roles/cups`（API）と `platform/ansible/media-nextcloud.yml`（`manage.py custom-apps` がGitHub Releaseから導入、`config-print` が `occ` 設定）

## 変更範囲

- Nextcloudのイメージは固定のまま。htmlボリューム内 `custom_apps/cups_print` へ置き、`occ config:app:set` でAPIのURLとトークンを設定する。
- 印刷APIは本文を一時ファイルへ落として `lp -d ts8430` に流すだけ。CUPSキューは `platform/ansible/roles/cups/` が作る。
- 利用者向けの案内は[プリンター](../services/printer.md)へ追加し、**Nextcloud全体の利用者向けマニュアル `docs/services/nextcloud-guide.md`**（機能・他アプリ連携・Androidアプリ）を新設して目次と[全サービスの使い方](../services/usage.md)からリンクした。

## 依存関係・並列作業

- 前提: CUPS中継（services-01）とNextcloud（media-01）。どちらも配備済み。
- 並列: 特になし。呼べるのはNextcloudにログインしたユーザーだけ（Filesの画面から）。

## 検証・完了条件

- services-01: `print-api` がactive、`/healthz` 200、キュー `ts8430` がidle（実測済み）。
- media-01: `occ app:list` に `cups_print: 1.0.1`、`relay_url` とトークン設定済み（実測済み）。
- 経路: media-01 → API → CUPS で `ts8430-2` が完了し、1枚印刷された（実測済み）。
- ブラウザー（一般ユーザー）で `/books` のPDFの「…」に **「印刷」「LocalSendで送る」**、`/music` のMP3に **「タグを編集」「LocalSendで送る」** が出ることを実測（2026-09-13）。「タグを編集」は実クリックでエディタが開き、タグAPIが200を返した（元ファイルにタグが無いため空欄）。
- ダイアログで部数・カラー（カラー/白黒）・ページ範囲（例 `1-3,5`）を指定できる。MarkdownはCUPSのテキストフィルタで印刷する（2026-09-26実装）。

共通の確認は `python3 -m mkdocs build --strict` と `python3 -m unittest discover -s tests`。

## 実装メモ

- Nextcloud 33は `appinfo/info.xml` に `<namespace>` が無いと `ucfirst` した `OCA\Cups_print` を探し、`OCA\CupsPrint` と噛み合わず二重includeで落ちる（2026-09-13実測）。`<namespace>CupsPrint</namespace>` を宣言する。
- JSは `@nextcloud/files` の `registerFileAction` を使う。`@nextcloud/dialogs` はFilePicker経由でVueとCSSを引き込むため使わず、トーストは `OCP.Toast` にする。esbuildで `js/cups_print.js` にバンドルし、`node_modules` は配備しない。
- **NC33のFilesアプリは `@nextcloud/files` v4 のグローバルレジストリ（`window._nc_files_scope`）を共有する。** アプリ側も v4 をバンドルしないと登録が別インスタンスに落ちてメニューに出ない（v3系の `window._nc_fileactions` は読まれない。2026-09-13実測）。v4では `new FileAction(...)` ではなくプレーンオブジェクトを `registerFileAction()` へ渡す。
- アプリJSは `Util::addScript` でなく `Util::addInitScript` で読む。Filesの初期化より前に登録でき、v4の `register:action` イベントと合わせて順序に依存しない。
- v4の `Node.extension` は**ドット込み**（`.pdf`）。`enabled` では `(node.extension || '').toLowerCase().replace(/^\./, '')` のように正規化する。
- コントローラの各メソッドに `#[NoAdminRequired]` を付ける。AppFrameworkは既定で管理者のみで、無いと一般ユーザーの実行時だけ403になる（メニュー表示は成功するため気づきにくい。2026-09-13実測）。

## 公開リポジトリへの切り出し（2026-09-26）

- App Store公開を見据え、アプリ本体は `rurutheGeek/nextcloud-cups-print`、中継APIは同リポジトリの `server/` を正本にした。このリポジトリの `stacks/print-api/` は配備用の写し。
- media-01への導入は `manage.py custom-apps`（`group_vars/media.yml` の `nextcloud_custom_apps` がバージョン正本）。旧 `shake_print` は `remove-apps` で撤去した。
- プリンターのアドレスはDHCPで `192.168.10.9` → `192.168.10.3` へ移動していた。キューはmDNSホスト名 `ipp://cA5E9FB00000.local/ipp/print` を指すようにして追従させた（`cups_printer_uri`）。
- 2026-09-26、Nextcloud 35.0.1の使い捨てコンテナでも有効化・ルート・設定フォーム描画・JS配信を確認した。
