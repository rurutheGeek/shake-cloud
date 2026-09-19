---
title: プリンター（Canon TS8430シリーズ）
updated: 2026-09-13
section: 利用ガイド
audience: 利用者
tags:
  - guide
  - print
---

# プリンター（Canon TS8430シリーズ）

> **更新日** 2026-09-13 ・ **区分** 利用ガイド ・ **読む人** 利用者

## 構成

プリンターは家庭内LAN（IPP 631・raw 9100・AirPrint対応）にあります。現在のアドレスは `192.168.10.9` です（2026-09-13時点。以前は `192.168.10.2`）。アドレスはDHCPで変わるため、**services-01（`192.168.10.200`）のCUPSがmDNS（`_ipp._tcp`）で現在地を自動検出**して中継します。キュー名は `ts8430` です。端末がプリンターを直接見つけられない場合（VPN越しなど）も、CUPSのIPを指定すれば印刷できます。

> プリンターは自動電源OFFの間はWiFiごと落ちてLANに出てきません（mDNSも応答しません）。その間にCUPSを配備すると「Canon TS8430 がLANで見つからない」で止まります。プリンターの電源を入れ直して再実行すれば完了します。

| もの | 値 |
| --- | --- |
| キューの名前 | `ts8430` |
| CUPSの場所 | `192.168.10.200`（LAN/VPNから。631/tcp） |
| Web確認（HTTPS） | <https://cups.apextox.dpdns.org>（Authentik SSO。`/admin` は入口のCaddyが403で閉じる） |
| Web確認（直） | <http://192.168.10.200:631>（印刷クライアント用の素のHTTP） |
| 印刷の許可 | LAN `192.168.10.0/24` と VPN `100.64.0.0/10`（Tailscale） |
| 管理画面 | `127.0.0.1` のCUPSだけ（LANからは開けない） |

プリンター自体はAirPrint/Mopria/Canon PRINTアプリに対応しているため、**LAN内の端末は直接印刷しても構いません。** CUPSを使うのはLAN外（VPN）の端末や、プリンターを見つけられない端末です。

## 印刷のしかた

### コマンドから（Linux・macOS）

```bash
lp -h 192.168.10.200 -d ts8430 印刷したいファイル.pdf
lpstat -h 192.168.10.200 -p ts8430   # 状態
lpq -h 192.168.10.200                 # キュー
```

### Windows

「プリンターとスキャナー」→「プリンターまたはスキャナーを追加」→
「手動で追加」→「URLでプリンターを検索」で:

```text
ipp://192.168.10.200:631/printers/ts8430
```

### macOS

「プリンターとスキャナー」→「プリンターを追加」→「IP」タブ:

- アドレス: `192.168.10.200`
- プロトコル: IPP
- キュー: `printers/ts8430`

### iPhone / Android

VPN接続中はCUPSを直接見つけられないことがあります。端末の印刷アプリ（Canon PRINTなど）でIPアドレス `192.168.10.200`・IPPを指定するか、LAN内でAirPrint/Mopriaを使ってください。

## Nextcloudから印刷

Nextcloudのファイル一覧で対象ファイルの「…」→「印刷」を選ぶと、services-01 の印刷API経由でそのまま印刷できます。PDF・PNG・JPEG・テキストに対応し、今は1部・カラーで出します。利用者向けの操作は[Nextcloudの使い方（利用者向け）](nextcloud-guide.md)にまとめています。

| もの | 値 |
| --- | --- |
| アプリ | `shake_print`（自作。`stacks/media/nextcloud/apps/shake_print/`） |
| 印刷API | services-01 の `:6320`。トークン認証で、Nextcloud（media-01）からのみ受け付け |
| トークン | `platform/sops/print-api.sops.yaml`（CUPSロールとNextcloudの配備が読む） |
| 配備 | `platform/ansible/media-nextcloud.yml`（アプリのコピーと `occ` 設定まで行う） |

ストアの印刷アプリ（Printer・SkyPrint）はNC33非対応で、NextcloudコンテナへのCUPSクライアント追加が前提のため使いません。自作アプリはファイル一覧のJSとPHPコントローラーだけで、イメージは固定のままです。

## インク残量・状態

インク残量とプリンター状態はHome AssistantのIPP統合で見られます（[H01](../development/H01-home-assistant.md)）。アイドル中は残量が`unknown`になることがあります。プリンターのWeb UIは現在のアドレス（HAのデバイス画面の「開く」リンク、または `avahi-browse -rt _ipp._tcp` で確認）を開いてください。アドレスが変わったときは、CUPSの再配備と合わせてHAの統合も現在地へ張り替えます。

## スキャン

TS8430からNextcloudへ直接スキャンする機能はありません。Canon PRINTアプリで端末へ取り込み、NextcloudアプリかLocalSendで共有してください（[LocalSend](../development/D06-localsend.md)）。

## 保守

CUPSは `platform/ansible/cups.yml` で配備します。キューや許可ネットワークを変えるときは `platform/ansible/roles/cups/defaults/main.yml` を直して再実行してください。ホスト上の `cupsd.conf` を直接編集しないでください。

ロールは応答がないときだけ `avahi-browse` でプリンターを探し、見つかったアドレスでキューを作り直します（`cups_printer_uri` は既定のヒントにすぎません）。プリンターのアドレスを固定したい場合は、ルーターのDHCP固定割当（例: `.20` かプール外の `.190`）を設定してください。

同じロールがNextcloud用の印刷API（`stacks/print-api/` の `print-api.service`・`:6320`）も配備します。トークンはSOPS、送信元は `cups_print_api_allowed`（既定: media-01）だけです。

印刷アプリを直したときは、`stacks/media/nextcloud/apps/shake_print/` で `npm install && npm run build`（Nodeが必要）して `js/shake_print.js` を更新し、`media-nextcloud.yml` を再実行します。ビルドは `src/print.js` のesbuildバンドルで、`node_modules` は配備しません。
