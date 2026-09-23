---
title: 通信速度テスト（LibreSpeed）
updated: 2026-09-21
section: 利用ガイド
audience: 利用者
tags:
  - guide
  - network
---

# 通信速度テスト（LibreSpeed）

> **更新日** 2026-09-21 ・ **区分** 利用ガイド ・ **読む人** 利用者

端末（パソコン・スマートフォン）と services-01 の間の**実効速度**を測るページです。
入口は <https://speed.apextox.dpdns.org>（家庭内LANから）。Homarrの
**LibreSpeed** タイルからも開けます。

## 何を測っているか

- 測っているのは **ページを開いた端末 ↔ services-01** の速度です。Wi-Fiの電波状況、
  LANケーブル、VMの仮想NICまで含めた「その端末・その場所」の実測値になります。
- インターネット回線の速度ではありません。回線速度はサーバー側から測る別の仕組みが
  必要です（このページの対象外）。
- Nextcloudなど他のサービスとの速度は、同じLAN・同じ経路を通るので、このページの
  数値が目安になります。

## 使い方

1. [Homarr](https://homarr.apextox.dpdns.org) を開き、**LibreSpeed** タイルを押します。
2. ページが開いたら **Start**（開始）を押します。計測は20秒ほどで終わります。
3. ダウンロード・アップロード・Ping・Jitterが表示されます。

**自動では測りません。** ページを開いただけでは計測は始まりません。計測は回線を
占有するので、必要なときに手で開始します。

## 結果の見方

| 項目 | 意味 | 目安 |
| --- | --- | --- |
| Download | services-01 から端末へ受け取る速さ | 有線で 900Mbps 前後、Wi-Fiは電波次第で 100〜800Mbps |
| Upload | 端末から services-01 へ送る速さ | 有線で 900Mbps 前後 |
| Ping / Jitter | 1往復の遅れとばらつき | 有線で 1ms 未満。Wi-Fiは大きくなる |

家庭内LANは 1Gbps なので、有線でも TCP・TLS のオーバーヘッドを含めて 940Mbps 前後が
上限です。速い・遅いを比べるときは、**同じ端末・同じ場所・同じ時間帯**で測ります。

## 前の結果を見る

計測履歴は services-01 のデータベースに残っています。履歴の統計ページ
`https://speed.apextox.dpdns.org/results/stats.php` は管理者からパスワードを
聞いて開きます（`secrets/stats_password`。通常の利用では不要です）。

## 正確に測るコツ

- **Wi-Fiの比較は測る場所を変えて**。同じ部屋・同じ向きで測ると差が出ます。
- 計測中は他の通信（動画・バックアップ・OS更新）を止めます。
- VPNやプロキシを使っているときは、その経路の速度になります。
- ブラウザーの拡張機能・省電力設定も数値に影響します。
- 端末を有線でつなぐと、LANとWi-Fiの切り分けができます。

## 管理者向け

- スタック: `stacks/librespeed/`（services-01 の独立Compose）。正本は
  `platform/terraform/dns.yaml` の `speed` レコードと `stacks/librespeed/` です。
- 配備: `platform/ansible/librespeed.yml`（roles: `docker` → `tls_proxy` →
  `librespeed`）。詳細は `stacks/librespeed/README.md`。
- 操作: `sudo python3 manage.py init / lock / up / status / backup`。
- 統計パスワードは `secrets/stats_password`。`manage.py init` が一度だけ生成し、
  以後は作り直しません。
- 配備先とバックアップの方針: [サービスの置き場所とクラウドVM](../operations/services.md)。

## うまくいかないとき

| 症状 | 確認すること |
| --- | --- |
| タイルが赤い | services-01 で `sudo python3 manage.py status`。コンテナが動いているか |
| ページは開くが数値が低い | 端末がWi-Fiか有線か、電波状況、同時通信の有無 |
| 有線なのに300Mbps前後で頭打ち | USB接続のGbEアダプタ・USB-Cドック経由（USB 2.0では約300Mbpsが天井）。PC本体のLANポートへ直挿しして再測 |
| LAN内なのに300Mbps前後（Tailscale導入端末） | Tailscaleのsubnet routeがLANより優先され、net-01経由で回り込むことがある。TailscaleのIFメトリックを上げる（`Set-NetIPInterface -InterfaceAlias Tailscale -InterfaceMetric 9999`）、または計測時だけOFF |
| 数値が毎回ばらつく | Wi-Fiは仕様です。有線で同じ値になるか試す |
| 統計ページに入れない | 管理者に `secrets/stats_password` を確認してもらう |
