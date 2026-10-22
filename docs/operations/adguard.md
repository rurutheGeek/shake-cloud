---
title: DNS と広告遮断（AdGuard Home）
updated: 2026-10-22
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
  - dns
---

# DNS と広告遮断（AdGuard Home）

> **更新日** 2026-10-22 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: [Flint 3](flint3.md) で稼働（2026-10-14〜）。設定の正本は `platform/flint3/rootfs/etc/AdGuardHome/config.yaml`。

## ひとことで

家の DNS の窓口です。広告・トラッカーを遮断し、外への問い合わせは
**DoH**（HTTPS で包んだ DNS）で送ります。DHCP とローカル名（`*.lan`）は
dnsmasq が担当し、AdGuard はそこへ転送します。

```
端末 ──DNS（192.168.10.1:53）──▶ GL のファイアウォールが転送
                   ▼
             AdGuard Home（:3053）──DoH──▶ Cloudflare / Google
                   │  *.lan と逆引きだけ
                   ▼
             dnsmasq（127.0.0.1:53）＝ DHCP とローカル名
```

## なぜ入れているか

- **広告・トラッカーの遮断**: AdGuard DNS filter（約18万件）＋
  HaGeZi's Pro Blocklist（2026-09-22 追加）
- **DNS の暗号化（DoH）**: 回線事業者に問い合わせ内容を平文で見せない
- **ISP の DNS 不調から独立**: 切替前、ISP の DNS が `refused` を返して
  名前が引けないことがあった
- **LAN 内の名前は今までどおり**: `*.lan` のローカル名は dnsmasq が
  答える（AdGuard は `*.lan` を dnsmasq へ転送）

## いまの設定

| 項目 | 値 | 理由 |
| --- | --- | --- |
| 待ち受け | `:3053`。LAN・Tailscale からの `:53` を GL のファイアウォールが転送 | GL.iNet の組み込み方式。dnsmasq は `:53` のまま |
| 上流 | `[/lan/]127.0.0.1:53` → DoH（Cloudflare / Google） | ローカル名は dnsmasq、外部は暗号化 |
| ブートストラップ | 1.1.1.1 / 9.9.9.10 | DoH サーバー名の解決用 |
| 逆引き（PTR） | `127.0.0.1:53` | LAN の名前は dnsmasq |
| フィルタ | AdGuard DNS filter ＋ HaGeZi's Pro Blocklist | 広告・トラッカー。1本では網羅できないため補完 |
| 除外（`user_rules`） | Xbox 実績用の Microsoft ドメイン（`v10/v20.events.data.microsoft.com` の地域版・`v10c`・`vortex(-win)`・`pipe.aria`・`watson` と CNAME 先） | HaGeZi's Pro が実績トラッキングを遮断するため（2026-10-02） |
| クエリログ | メモリのみ（ファイルに書かない） | eMMC を減らさない |
| 統計 | 90日 | |
| 管理画面 | `192.168.10.1:3000`。GL.iNet の管理画面のログインが要る | SSO（`adguard.apextox.dpdns.org`）からは入れない |

## 正本と反映

| 対象 | 正本 | 反映 |
| --- | --- | --- |
| 本体の設定 | `platform/flint3/rootfs/etc/AdGuardHome/config.yaml` | `platform/flint3/deploy.sh 192.168.10.1` → `/etc/init.d/adguardhome restart` |
| 予約・名前 | NetBox（`platform/netbox/devices.yaml`） | `tools/netbox-dhcp-sync.py pull`（timer が自動実行） |

**ルータ上で YAML を直接編集しない。** 正本は Git です。

## よくある操作

### フィルタをすぐ更新する

フィルタは既定で24時間ごとに更新されます。すぐ更新したいとき:

```bash
ssh root@192.168.10.1 \
  'curl -s -X POST -H "Content-Type: application/json" -d "{}" \
     http://127.0.0.1:3000/control/filtering/refresh'
```

### 特定の名前を遮断したい・通したい

正本の `config.yaml` の `user_rules` に書いてコミットします。

```yaml
user_rules:
  - '||ads.example.com^'      # 遮断
  - '@@||good.example.com^'   # 除外（遮断しない）
```

反映は `deploy.sh` → `/etc/init.d/adguardhome restart`。

### フィルタ（ブロックリスト）を足す

正本の `config.yaml` の `filters` に足してコミットします。URL は
[HostlistsRegistry](https://adguardteam.github.io/HostlistsRegistry/) の
`filter_N.txt` を使い、`id` も登録所の番号に合わせます。

```yaml
filters:
  - enabled: true
    url: https://adguardteam.github.io/HostlistsRegistry/assets/filter_48.txt
    name: HaGeZi's Pro Blocklist
    id: 48
```

**id は一意**にします（重複すると片方が読まれません）。反映は `deploy.sh` →
`/etc/init.d/adguardhome restart` → フィルタ更新（上記）。追加直後は
`/control/filtering/status` の `rules_count` が増えていることを確認します。
リストを増やすほど誤ブロックも増えるので、**1本ずつ足して数日見る**のが安全です。

### 遮断の様子を見る

管理画面の「クエリログ」。メモリにだけ持つので、再起動で消えます。**家の外には出ません。**

### 誤ブロックを見つけたら（止めてはいけない物の確認）

1. クエリログを「遮断」で絞って、ドメインと回数を見る（管理画面）。
2. そのドメインが**機能に必要**なら、正本の `user_rules` に除外を足す。

```yaml
user_rules:
  - '@@||example.com^'   # 遮断しない（サブドメインも含む）
```

3. `deploy.sh` → `/etc/init.d/adguardhome restart` で反映し、コミットする。

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

**2026-10-02、Xbox Live の実績（Minecraft・Minecraft Dungeons など）が
解除されない症状を実測しました。** HaGeZi's Pro Blocklist が実績の記録・同期に
使われる `vortex-win.data.microsoft.com`（`v10/v20.` 配下を含む）・
`vortex.data.microsoft.com`・`pipe.aria.microsoft.com` を `0.0.0.0` へ遮断して
いました。正本の `user_rules` に除外を追加し、`v10/v20.events.data.microsoft.com`
と CNAME 先（`win-global-asimov-leafs-events-data.trafficmanager.net`）も
フィルタ更新で再遮断されないよう明示的に許可しています。同日、HaGeZi の
Microsoft 一覧に載る残り（地域版 `v10/v20`・`v10c`・`watson`）も許可して、
**DNS 側の要因を消した**（それでも解除されないときは、PC 側の
「Connected User Experiences and Telemetry」など Xbox 系サービスの停止を
疑う）。**実績がまた解除されなくなったら、まずクエリログで Microsoft 系の
遮断を確認**し、
[HaGeZi の Microsoft 一覧](https://github.com/hagezi/dns-blocklists/blob/main/share/microsoft.txt)
を参考に `user_rules` へ足してください。

**ただし、Minecraft Dungeons II の Steam 版は「ゲーム内では解除されるのに
Xbox プロフィールに実績が記録されない（プレイ時間だけが残る）」既知の
ゲーム側不具合があります**（[Minecraft Feedback 2026-09-30](https://feedback.minecraft.net/hc/en-us/community/posts/49272314358413-BROKEN-Steam-version-doesn-t-earn-Xbox-achievements)、
Switch 2 でも同報告）。この症状は DNS では直らないので、AdGuard を疑う前に
ゲーム側の不具合情報を確認してください。

### 一時的に遮断を止める

AdGuard 自体を止めると `:53` が空になり DNS が止まります。止めずに、
管理画面でフィルタを無効にする（または正本の `filters[].enabled` を `false`）
のが安全です。

## しくみ（知っておくと困らないこと）

- **フィルタ取得に失敗しても止まらない**: 回線が無い状態で起動すると
  フィルタが空のままになる。上の refresh を叩くか `/etc/init.d/adguardhome restart`
- **dnsmasq は DHCP とローカル名だけ**: `*.lan` は AdGuard からここへ転送される。
  **1語の名前は通らない**。`<名前>.lan` と引く
- **IPv6 端末の DNS は DHCPv4 で配る**: JPNE の上流 RA に RDNSS が無いため、
  IPv6 の DNS（RDNSS）は配れない。端末は DHCPv4 の `192.168.10.1` を使う
- **稼働中の AdGuard Home は設定ファイルを自分の形式へ書き換える**: `deploy.sh`
  で置いたら必ず再起動する

## 確認コマンド

```bash
# 遮断
nslookup doubleclick.net 192.168.10.1   # 0.0.0.0
# フィルタの件数と更新時刻
ssh root@192.168.10.1 'curl -s http://127.0.0.1:3000/control/filtering/status | head -c 300'
# ログ
ssh root@192.168.10.1 'logread | grep -i adguard | tail -5'
```

## 関連

- [Flint 3（家庭内ルーター）](flint3.md)
- [ルータがつながらないときの調べ方](router-troubleshooting.md)
- [NetBox の使い方](netbox.md)
