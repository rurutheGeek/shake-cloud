---
title: DNS と広告遮断（AdGuard Home）
updated: 2026-09-22
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
  - dns
---

# DNS と広告遮断（AdGuard Home）

> **更新日** 2026-09-22 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **router-01 で稼働中（家の DNS の窓口）。**
対象読者: 家のネットワークを運用する人。設定の一覧は
[router-01 の設定まとめ](router-config.md)、ルータ本体は
[router-01（OpenWrt・自作ルータ）](router.md) が正本です。

## ひとことで

家の DNS の窓口です。広告・トラッカーを遮断し、外への問い合わせは
**DoH**（HTTPS で包んだ DNS）で送ります。DHCP とローカル名（`*.lan`）は
dnsmasq が担当し、AdGuard はそこへ転送します。

```
端末 ──DNS──▶ AdGuard Home（192.168.10.1:53）──DoH──▶ Cloudflare / Google
                   │  *.lan だけ
                   ▼
             dnsmasq（127.0.0.1:5353）＝ DHCP とローカル名
```

## なぜ入れているか

- **広告・トラッカーの遮断**: AdGuard DNS filter（約18万件）＋
  HaGeZi's Pro Blocklist（2026-09-22 追加）
- **DNS の暗号化（DoH）**: 回線事業者に問い合わせ内容を平文で見せない
- **ISP の DNS 不調から独立**: 切替前、ISP の DNS が `refused` を返して
  名前が引けないことがあった
- **LAN 内の名前は今までどおり**: `aterm.lan` などのローカル名は dnsmasq が
  答える（AdGuard は `*.lan` を dnsmasq へ転送）

## いまの設定

| 項目 | 値 | 理由 |
| --- | --- | --- |
| バージョン | 0.107.57（OpenWrt 24.10 のフィード） | イメージに固定（`openwrt.yaml`） |
| 待ち受け | `192.168.10.1:53`（TCP/UDP・v4/v6） | LAN の窓口 |
| 上流 | `[/lan/]127.0.0.1:5353` → DoH（Cloudflare / Google） | ローカル名は dnsmasq、外部は暗号化 |
| ブートストラップ | 1.1.1.1 / 9.9.9.10 | DoH サーバー名の解決用 |
| 逆引き（PTR） | `127.0.0.1:5353` | LAN の名前は dnsmasq |
| フィルタ | AdGuard DNS filter（約18万件）＋ HaGeZi's Pro Blocklist | 広告・トラッカー。1本では網羅できないため補完 |
| クエリログ・統計 | 90日 | ルータ内のディスクに保存 |
| 管理画面 | `https://adguard.apextox.dpdns.org`（SSO） | Forward Auth の下に置く。ルータの `:3000` は services-01 だけに許可 |
| 作業ディレクトリ | `/etc/adguardhome/data`（UCI `workdir`） | 既定の `/var/lib` は tmpfs。再起動でフィルタが消えるのを防ぐ |
| DHCP の DNS 配布 | `192.168.10.1`（dnsmasq の option 6） | 端末は DHCP で AdGuard を知る |

## 正本と反映

| 対象 | 正本 | 反映 |
| --- | --- | --- |
| 本体の設定 | `platform/openwrt/rootfs/etc/adguardhome/adguardhome.yaml` | scp 後に `/etc/init.d/adguardhome restart`、またはイメージ再ビルド |
| パッケージ・UCI | `openwrt.yaml`・`rootfs/etc/uci-defaults/97-shakecloud-adguard` | イメージ再ビルド |
| dnsmasq 側（DHCP・option 6・`:5353`） | `rootfs/etc/shakecloud/config/dhcp` | scp 後に `/etc/shakecloud/apply`（または reboot） |
| 予約・名前 | NetBox（`platform/netbox/devices.yaml`） | `tools/netbox-dhcp-sync.py pull`（timer が自動実行） |

**ルータ上で UCI や YAML を直接編集しない。** 正本は Git です。

## 管理画面の開き方

**通常は <https://adguard.apextox.dpdns.org>** を開きます（共通ログイン＝SSO）。
しくみは、ルータの `192.168.10.1:3000` を services-01 の Caddy が中継し、
Forward Auth（Authentik）で認証する形です。**ルータのファイアウォールは
`:3000` を services-01 だけに開けている**ので、LAN の端末から
`http://192.168.10.1:3000` を直接開くことはできません（SSO の迂回防止）。

SSO が使えないときは SSH トンネルで開きます。

```bash
ssh -L 3000:192.168.10.1:3000 root@192.168.10.1
# ブラウザで http://localhost:3000/
```

AdGuard 自身にはパスワードを設定していません（`users: []`）。初回に UI で
管理者を作ると設定ファイルが書き換わり、Git の正本と差分が出ます。
**作らないでください**（必要になったら正本へ反映してコミットします）。

## よくある操作

### フィルタをすぐ更新する

フィルタは既定で24時間ごとに更新されます。すぐ更新したいとき:

```bash
ssh root@192.168.10.1 \
  'curl -s -X POST -H "Content-Type: application/json" -d "{}" \
     http://192.168.10.1:3000/control/filtering/refresh'
```

### 特定の名前を遮断したい・通したい

正本の `adguardhome.yaml` の `user_rules` に書いてコミットします。

```yaml
user_rules:
  - '||ads.example.com^'      # 遮断
  - '@@||good.example.com^'   # 除外（遮断しない）
```

反映は scp → `/etc/init.d/adguardhome restart`。

### フィルタ（ブロックリスト）を足す

正本の `adguardhome.yaml` の `filters` に足してコミットします。URL は
[HostlistsRegistry](https://adguardteam.github.io/HostlistsRegistry/) の
`filter_N.txt` を使い、`id` も登録所の番号に合わせます。

```yaml
filters:
  - enabled: true
    url: https://adguardteam.github.io/HostlistsRegistry/assets/filter_48.txt
    name: HaGeZi's Pro Blocklist
    id: 48
```

**id は一意**にします（重複すると片方が読まれません）。反映は scp →
`/etc/init.d/adguardhome restart` → フィルタ更新（上記）。追加直後は
`/control/filtering/status` の `rules_count` が増えていることを確認します。
リストを増やすほど誤ブロックも増えるので、**1本ずつ足して数日見る**のが安全です。

### 遮断の様子を見る

管理画面の「クエリログ」。ファイルは
`/etc/adguardhome/data/data/querylog.json`（90日）。**家の外には出ません。**

### 誤ブロックを見つけたら（止めてはいけない物の確認）

1. クエリログを「遮断」で絞って、ドメインと回数を見る（管理画面、または
   ログファイルを `grep`）。
2. そのドメインが**機能に必要**なら、正本の `user_rules` に除外を足す。

```yaml
user_rules:
  - '@@||example.com^'   # 遮断しない（サブドメインも含む）
```

3. scp → `/etc/init.d/adguardhome restart` で反映し、コミットする。

**2026-09-20 の調査（18時間・遮断1,303件/94ドメイン）**では、広告SDK・
計測（Firebase/Google Analytics など）・Amazon デバイスのテレメトリ
（`footprintdns.com`・`minerva.devices.a2z.com` など）だけで、機能に必要な
名前の遮断は見つかりませんでした。唯一の候補は Alexa のテレメトリで、
**Alexa の挙動がおかしくなったら上のように除外**してください。
`stats.grafana.org` はトラッカーなので**遮断のままでよい**（Grafana 側の
匿名統計も止めている。`stacks/monitoring/compose.yaml`）。

**2026-09-22 に HaGeZi's Pro Blocklist を追加**したため、遮断はさらに増えます。
アプリやサイトの機能が壊れたと思ったら、まずクエリログを「遮断」で絞り、
上の手順で除外してください。

### 一時的に遮断を止める

AdGuard 自体を止めると `:53` が空になり DNS が止まります。止めずに、
管理画面でフィルタを無効にする（または正本の `filters[].enabled` を `false`）
のが安全です。

## しくみ（知っておくと困らないこと）

- **起動**: `interface.*.up` の5秒後に起動（WAN が上がってから）。再起動では
  `workdir` のフィルタキャッシュを読むため、すぐ遮断が効く
- **フィルタ取得に失敗しても止まらない**: 起動直後は WAN が未確立のことが
  あり、その場合はキャッシュを使う。キャッシュが無い初回だけは次回更新まで
  遮断が空になるので、上の refresh を手で叩く
- **dnsmasq は DHCP とローカル名だけ**: DNS は `:5353`。`*.lan` は AdGuard から
  ここへ転送される。**1語の名前（`aterm`）は通らない**。`aterm.lan` と引く
- **IPv6 端末の DNS は DHCPv4 で配る**: JPNE の上流 RA に RDNSS が無いため、
  IPv6 の DNS（RDNSS）は配れない（odhcpd の relay は上流 RA の RDNSS を
  書き換える方式で、元が無い）。端末は DHCPv4 の `192.168.10.1` を使う
- **24.10 のパッケージは設定パスが違う**: 既定は `/etc/adguardhome.yaml`。
  UCI `adguardhome.config.config` で `/etc/adguardhome/adguardhome.yaml` に
  合わせている（`uci-defaults/97`）
- **作業ディレクトリは永続領域**: 既定の `/var/lib/adguardhome` は tmpfs。
  再起動でフィルタと統計が消える（2026-09-20 に実際に踏んだ）

## つまずきやすい点

| 症状 | 原因 | 直し方 |
| --- | --- | --- |
| スマホに「インターネットなし」 | DHCP が DNS（option 6）を配っていない | `dhcp.lan` に `list dhcp_option '6,192.168.10.1'`（設定済み）。端末は Wi-Fi 再接続で新しいリースを取る |
| 広告が消えない | フィルタが空（起動時に取得失敗） | refresh API を叩き、`rules_count` を確認 |
| `aterm` が引けない | 1語の名前は転送されない | `aterm.lan` と引く |
| 管理画面が開けない | SSO か Caddy の入口の問題 | `https://adguard.apextox.dpdns.org` を開く。だめなら SSH トンネル（上記） |
| 名前が全体的に引けない | AdGuard か dnsmasq が落ちている | 下の確認コマンド |

## 確認コマンド

```bash
# 窓口（:53 = AdGuard、:5353 = dnsmasq）
ssh root@192.168.10.1 'netstat -lntup | grep -E ":(53|5353) "'
# 遮断とローカル名
ssh root@192.168.10.1 'nslookup doubleclick.net 192.168.10.1'   # 0.0.0.0
ssh root@192.168.10.1 'nslookup aterm.lan 192.168.10.1'         # 192.168.10.2
# フィルタの件数と更新時刻
ssh root@192.168.10.1 'curl -s http://192.168.10.1:3000/control/filtering/status | head -c 300'
# HTTPS 入口（SSO のログインへ 302 すれば正常）
curl -sI https://adguard.apextox.dpdns.org/ | head -3
# ログ
ssh root@192.168.10.1 'logread | grep -i adguard | tail -5'
```

## 関連

- [router-01 の設定まとめ](router-config.md)
- [router-01（OpenWrt・自作ルータ）](router.md)
- [ルータがつながらないときの調べ方](router-troubleshooting.md)
- [NetBox の使い方](netbox.md)
