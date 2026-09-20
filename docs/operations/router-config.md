# router-01 の設定まとめ（素の OpenWrt からの変更）

更新日: 2026-09-20。状態: **実機で稼働中の設定を「素の状態からの変更」だけ抜き出した一覧。**
対象読者: ネットワーク機器に慣れていない人。細かい手順は
[router-01（OpenWrt・自作ルータ）](router.md)、調査の根拠は
[N06 ルータ自作](../development/N06-router.md) が正本です。

## まず用語（3分）

| 用語 | かんたんに言うと |
| --- | --- |
| UCI | OpenWrt の設定ファイル（`/etc/config/...`）。テキストなので Git で差分が読める |
| dnsmasq | LAN に IP を配る（DHCP）・名前を引く（DNS）担当 |
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
| 〃 | IPv6 は LAN でサーバ | RA・DHCPv6 は **relay**、ndp は ndppd に任せる | 上流の /64 を LAN へ中継する |
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

## 3. ホスト（Proxmox / K11）側の変更

| 変更 | 理由 |
| --- | --- |
| `vmbr1` 追加（`nic0`、IP なし） | WAN を VM へ渡す。ホストに IP を与えない |
| 実体のない `nic2` の定義を削除 | 台帳と実機のズレを消す |
| ホスト IP `.126` → `.10` | クラウド API の採番帯の内側にあったため |
| 起動順 `order=1,up=30`（`qm set`） | ルータを最初に起動。Terraform では `Sys.Modify` が要るため手動 |
| watchdog を softdog → SP5100 TCO | ホストがハングしても約10秒で自動再起動 |
| `kernel.panic=10` / `panic_on_oops=1` | panic でも自動再起動 |
| （未）BIOS の AC 復帰設定・UPS 接続 | 停電対策。物理作業 |

## 4. 変えたいときの正本

| 対象 | 正本 | 反映方法 |
| --- | --- | --- |
| UCI 設定 | `platform/openwrt/rootfs/etc/shakecloud/config/` | `build.sh` で再ビルド、または `/etc/shakecloud/apply` |
| 機器の予約 | `platform/netbox/devices.yaml` | `tools/netbox-dhcp-sync.py ensure && pull`（timer が自動実行） |
| VM の形 | `platform/terraform/router.yaml` + `router/` | `tools/tf router apply` |
| ホストのネットワーク | 手順: [router.md](router.md) | 手作業（物理コンソール推奨） |
| watchdog / panic | 手順: [power.md](power.md) | 手作業 |

**ルータ上で UCI を直接編集しない。** 正本は Git と NetBox です。

## 5. 確認コマンド

```bash
# 設定（UCI）
ssh root@192.168.10.1 'uci show network.wan; uci show dhcp.wan6'
# 予約（NetBox 生成）
ssh root@192.168.10.1 'cat /etc/dnsmasq.d/netbox-reservations.conf'
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
