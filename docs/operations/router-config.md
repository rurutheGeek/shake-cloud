---
title: router-01 の設定まとめ（素の OpenWrt からの変更）
updated: 2026-09-20
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
  - router
---

# router-01 の設定まとめ（素の OpenWrt からの変更）

> **更新日** 2026-09-20 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **実機で稼働中の設定を「素の状態からの変更」だけ抜き出した一覧。**
対象読者: ネットワーク機器に慣れていない人。細かい手順は
[router-01（OpenWrt・自作ルータ）](router.md)、調査の根拠は
[N06 ルータ自作](../development/N06-router.md) が正本です。
ネットワーク全体の図と IP 帯は[ネットワーク・公開範囲・SSO](../architecture/network-auth.md)。

## まず用語（3分）

| 用語 | かんたんに言うと |
| --- | --- |
| UCI | OpenWrt の設定ファイル（`/etc/config/...`）。テキストなので Git で差分が読める |
| dnsmasq | LAN に IP を配る（DHCP）・名前を引く（DNS）担当 |
| AdGuard Home | DNS の窓口。広告を遮断し、上流を暗号化する |
| DoH | DNS over HTTPS。DNS の問い合わせを HTTPS で包んで送る |
| odhcpd | IPv6 の RA と DHCPv6 の担当 |
| ndppd | IPv6 の「近隣代理」。上流が端末を呼ぶとき、代わりに返事する |
| MAP-E | v6プラスの方式。IPv4 を IPv6 のトンネルに載せる |
| hotplug | 「LAN/WAN が上がった瞬間」に走る小さなスクリプト |
| Image Builder | 設定入り OpenWrt イメージを作る公式の道具 |

## 全体像

```
素の OpenWrt イメージ
  ├─ ビルド時に焼いた設定（rootfs/）        ← 再ビルドで再現できる
  └─ 起動後に足した修正（切替の日に判明）    ← あとから Git の正本へ戻した
ホスト（Proxmox / K11）側の変更（vmbr1・IP・watchdog など）
```

## 1. ビルド時に焼いたもの（イメージの中身）

正本は `platform/openwrt/rootfs/`。`platform/openwrt/build.sh` で再現ビルドします。

| ファイル | 素の状態 | いま | なぜ |
| --- | --- | --- | --- |
| `/etc/shakecloud/config/network` | `eth0` が LAN、WAN は ISP の DHCP | `eth0`=WAN（MAP-E）、`eth1`=LAN（`192.168.10.1`） | ONU 側を WAN、既存 LAN を LAN にする |
| 〃 | — | `legacymap '1'`、`wan6` に `extendprefix '1'` | JPNE 固有の CE 形式と、PD が無いときの /64 取得 |
| `/etc/shakecloud/config/dhcp` | dnsmasq が LAN に広い範囲を配る | プール `.20〜.99`、`.2〜.19` は機器帯 | 固定機器と動的を混ぜない |
| 〃 | dnsmasq が DNS の窓口 | DNS の窓口は **AdGuard（:53）**、dnsmasq は DHCP とローカル名（`:5353`） | 広告遮断と DoH |
| 〃 | IPv6 は LAN でサーバ | RA・DHCPv6 は **relay**、ndp は ndppd に任せる | 上流の /64 を LAN へ中継する |
| `/etc/adguardhome/adguardhome.yaml` | なし | `:53` で受け、`*.lan` は dnsmasq へ、他は DoH。UI は `192.168.10.1:3000`（services-01 の HTTPS 入口だけに許可） | 広告・トラッカー遮断と DNS の暗号化 |
| `uci-defaults/97-shakecloud-adguard` | なし | AdGuard を有効化し、設定パスを UCI に合わせる | 24.10 の既定パス `/etc/adguardhome.yaml` と違うため |
| `/etc/shakecloud/config/firewall` | 既定のゾーン | WAN は masq + mtu_fix | NAT と MSS clamp（MTU 1460 に合わせる） |
| `/etc/shakecloud/config/system` | ホスト名 `OpenWrt` | `router-01`、JST、NICT NTP | 識別と時刻合わせ |
| `/etc/shakecloud/apply` + `uci-defaults/99-…` | なし | 初回起動で設定を反映 | 設定の正本を `/etc/shakecloud/config/` に保つ |
| `/etc/ndppd.conf` + `uci-defaults/98-…` | なし（odhcpd の ndp relay） | ndppd を有効化 | 再起動で固定端末の IPv6 が消える問題の対策 |
| `/etc/hotplug.d/iface/90-mape-ports` | なし | MAP-E の全 240 ポートへ SNAT を分散 | ポート枯渇と、ICMP が割当外へ出る問題の対策 |
| `/etc/hotplug.d/iface/91-lan-prefix-route` | なし | 委譲された /64 を `br-lan` へ向ける経路 | ndppd の戻りパケットを LAN へ流す |
| `/etc/dnsmasq.d/` | なし | NetBox 生成の予約を読む場所 | 予約の正本を NetBox に一本化 |
| `openwrt.yaml` | 素の x86_64 | 版とチェックサム固定 + `map`・`luci`・`ndppd` など | 再現ビルドと必要機能 |

## 2. 起動後・切替の日に足した修正（実機 → Git）

| 症状 | 原因 | 変更 |
| --- | --- | --- |
| IPv4 が全滅（IPv6 だけ動く） | JPNE は draft-03 系の CE アドレス形式 | `network.wan` に `legacymap '1'` |
| LAN 端末が IPv6 を取れない | odhcpd は上流側にもモードが要る | `dhcp.wan6` に `ra`・`dhcpv6` の relay |
| 家のサービス名が引けない | rebind protection が公開 DNS の私有 IP を捨てる | `dnsmasq` に `rebind_domain` |
| ping が通らない・ポート枯渇 | fw4 が ICMP の SNAT を張らない | `90-mape-ports` を有効化 |
| 再起動で固定端末の IPv6 が消える | odhcpd の ndp relay は一度しか学習しない | ndppd + `91-lan-prefix-route` |
| 予約が UCI と NetBox で二重管理 | — | `confdir=/etc/dnsmasq.d` にして NetBox 生成へ |
| 再起動後に Wi-Fi 端末が「インターネットなし」 | dnsmasq が DHCP で DNS（option 6）を配らない | `dhcp.lan` に `list dhcp_option '6,192.168.10.1'`（実測で Offer/ACK を確認） |

<a id="3-dns-の構成adguard-home"></a>
## 3. DNS の構成（AdGuard Home）

```
端末 ──DNS──▶ AdGuard Home（192.168.10.1:53）──DoH──▶ Cloudflare / Google
                   │  *.lan だけ
                   ▼
             dnsmasq（127.0.0.1:5353）＝ DHCP とローカル名
```

- **窓口は AdGuard**: 広告・トラッカーを遮断し、上流は DoH（暗号化）。
  ISP の DNS 不調（`refused` を返す問題）から独立する
- **dnsmasq は DHCP とローカル名だけ**: DNS は 5353 へ移した。AdGuard が
  `*.lan` をここへ転送する（DHCP のリース名・NetBox の予約名が引ける）
- **ローカル名は `.lan` を付けて引く**: `aterm.lan` のように。AdGuard は
  末尾一致でしか転送できないため、1語の名前（`aterm`）は通らない
- **IPv6 端末の DNS は DHCPv4 で配る分だけ**: `dhcp.lan.dns` は odhcpd 用に
  入れてあるが、**JPNE の上流 RA に RDNSS が無いため、いまは効かない**。
  odhcpd の relay は「上流 RA の RDNSS を書き換える」方式で、元が無ければ
  何も配れない（実測で確認。2026-09-20）。LAN 端末は DHCPv4 の
  `192.168.10.1` を使う。ISP が将来 RDNSS を載せれば、この設定で AdGuard へ
  書き換わる。恒久的に配る方法（radvd を RDNSS 専用で併用する等）は未実施
- **管理画面は HTTPS 入口から**（`https://adguard.apextox.dpdns.org`、SSO）。
  ルータの `192.168.10.1:3000` は**ファイアウォールで services-01（Caddy の
  ホスト）だけに許可**している（LAN 全体に開けると SSO を迂回できる）。
  SSH トンネルでも開ける:
  `ssh -L 3000:192.168.10.1:3000 root@192.168.10.1` → `http://localhost:3000/`
- **LuCI は `https://router.apextox.dpdns.org`**（SSO なし・復旧経路。IP 直は
  `http://192.168.10.1`）。認証は LuCI の root パスワードで、未設定なら
  SSH で `passwd` を実行して設定する
- フィルタは AdGuard DNS filter（約18万件）と HaGeZi's Pro Blocklist
  （2026-09-22 追加）。設定の正本は
  `platform/openwrt/rootfs/etc/adguardhome/adguardhome.yaml`
- 運用（管理画面の開き方・フィルタ更新・つまずきやすい点）は
  [DNS と広告遮断（AdGuard Home）](adguard.md)
- **作業ディレクトリは `/etc/adguardhome/data`**（UCI の `workdir`）。既定の
  `/var/lib/adguardhome` は tmpfs なので、再起動でフィルタのキャッシュと統計が
  消える。起動直後は WAN がまだ上がっておらずフィルタを取得できないため、
  永続化していないと次回更新（既定24時間）まで遮断が効かない

## 4. ホスト（Proxmox / K11）側の変更

| 変更 | 理由 |
| --- | --- |
| `vmbr1` 追加（`nic0`、IP なし） | WAN を VM へ渡す。ホストに IP を与えない |
| 実体のない `nic2` の定義を削除 | 台帳と実機のズレを消す |
| ホスト IP `.126` → `.10` | クラウド API の採番帯の内側にあったため |
| 起動順 `order=1,up=30`（`qm set`） | ルータを最初に起動。Terraform では `Sys.Modify` が要るため手動 |
| watchdog を softdog → SP5100 TCO | ホストがハングしても約10秒で自動再起動 |
| `kernel.panic=10` / `panic_on_oops=1` | panic でも自動再起動 |
| （未）BIOS の AC 復帰設定・UPS 接続 | 停電対策。物理作業 |

## 5. 変えたいときの正本

| 対象 | 正本 | 反映方法 |
| --- | --- | --- |
| UCI 設定 | `platform/openwrt/rootfs/etc/shakecloud/config/` | `build.sh` で再ビルド、または `/etc/shakecloud/apply` |
| DNS（AdGuard） | `platform/openwrt/rootfs/etc/adguardhome/adguardhome.yaml` | 再ビルド、または `scp` 後に `/etc/init.d/adguardhome restart` |
| 機器の予約 | `platform/netbox/devices.yaml` | `tools/netbox-dhcp-sync.py ensure && pull`（timer が自動実行） |
| VM の形 | `platform/terraform/router.yaml` + `router/` | `tools/tf router apply` |
| ホストのネットワーク | 手順: [router.md](router.md) | 手作業（物理コンソール推奨） |
| watchdog / panic | 手順: [power.md](power.md) | 手作業 |

**ルータ上で UCI を直接編集しない。** 正本は Git と NetBox です。

## 6. 確認コマンド

```bash
# 設定（UCI）
ssh root@192.168.10.1 'uci show network.wan; uci show dhcp.wan6'
# 予約（NetBox 生成）
ssh root@192.168.10.1 'cat /etc/dnsmasq.d/netbox-reservations.conf'
# DNS（AdGuard 経由）
ssh root@192.168.10.1 'nslookup example.com 192.168.10.1'      # 外部（DoH）
ssh root@192.168.10.1 'nslookup doubleclick.net 192.168.10.1'  # 0.0.0.0 なら遮断
ssh root@192.168.10.1 'nslookup aterm.lan 192.168.10.1'        # ローカル名
# 動作（STUN・PMTU・IPv6・リンクの6項目）
python3 tools/verify-router.py --pve root@192.168.10.10
# ホストの watchdog
ssh root@192.168.10.10 'wdctl | head -4'
```

## 関連

- [router-01（OpenWrt・自作ルータ）](router.md)
- [NetBox の使い方](netbox.md)
- [電源と UPS](power.md)
- [N06 ルータ自作（OpenWrt）](../development/N06-router.md)
