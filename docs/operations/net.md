---
title: Tailscale（Flint 3 上の subnet router）
updated: 2026-10-14
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
---

# Tailscale（Flint 3 上の subnet router）

> **更新日** 2026-10-14 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **2026-10-14 に [Flint 3](flint3.md#tailscale) へ移した（端末情報を引き継ぎ、宅外から入れる範囲に個人端末の区画を追加）。** 以下は router-01 での記録: router-01（OpenWrt）で稼働中（2026-10-03 にクラウドVM `net-01` から移設し、net-01 は削除）。** ルート承認と tailnet DNS（AdGuard Home）は 2026-10-01 に適用済み。宅外端末での実機検証が未了。

宅外から家の区画へ入るための Tailscale の subnet router です。**2026-10-14 から Flint 3（K11 とは別の機械）で動いています。** K11 が落ちても宅外から家へ入れます。

| 項目 | 値 |
| --- | --- |
| ホスト | Flint 3（GL-BE9300、`192.168.10.1`、tailnet `100.91.7.69`、`tag:router`） |
| 流している経路 | `192.168.10.0/24`（サーバー）だけ。個人端末の区画（`192.168.40.0/24`）は 2026-10-17 から流さない（家の中の通信が遠回りしたため）。`autoApprovers` で自動承認。ネット専用・DMZ は流さない |
| 経路を保つ仕組み | GL の `gl_tailscale` はインターフェースが変わるたびに `tailscale up --reset` で経路を消すため、`hotplug.d/iface/95-shakecloud-tailscale-routes` が約20秒後に流し直す |
| アクセス制限 | `platform/tailscale/acl.json`（正本）。自分と家族の端末は全部、タグの付いた機器（relay・web・dmz・monitoring・game・router）は決めた先だけ |
| tailnet DNS | `192.168.10.1`（AdGuard Home。tailscale ゾーンの 53 を 3053 へ転送） |
| 家の中での遠回り | 家にある端末が「サブネットを使う」と、家の中の通信も Flint 3 の Tailscale を通る。家から出さない端末はオフにする（[Flint 3](flint3.md#tailscale)） |

以下は router-01 で動かしていた頃の記録です（2026-10-03〜10-14）。

## 実体

| 項目 | 値 |
| --- | --- |
| ホスト | `router-01`（OpenWrt、VMID 101、`192.168.10.1`） |
| tailnet アドレス | `100.91.7.69`（net-01 の端末の身元を引き継いだ。管理画面での再承認は不要だった） |
| 宣言（リポジトリ） | `platform/openwrt/openwrt.yaml` の `packages` に `tailscale`、`platform/openwrt/rootfs/etc/shakecloud/config/tailscale` |
| tailscaled の設定 | `/etc/config/tailscale`: `state_file /etc/tailscale/tailscaled.state`、`fw_mode nftables` |
| 状態ファイル | `/etc/tailscale/tailscaled.state`（**秘密値。イメージには含めない**） |
| ファイアウォール | `config/tailscale` の `tailscale` ゾーン（`device tailscale0`、forward REJECT）と、`tailscale` → `lan` の `forwarding`（`config/firewall`） |
| 広告ルート | `192.168.10.0/24`（`site.yaml` の `network.prefix` から取得）。承認済み（2026-10-01） |
| tailnet DNS | `192.168.10.1`（AdGuard Home）を唯一の global nameserver にし、`overrideLocalDNS` を有効化（MagicDNS は維持） |

tailnet からの着信は `tailscale0` に入り、`tailscale` ゾーンから `lan` へ転送されます。**送信元の書き換え（SNAT）は tailscaled 自身が nftables で行う**ため、ファイアウォール側で `masq` はしません。Tailscale の通信は端末側からの発信と中継で成立するので、WAN 側のポート開放も不要です。

## 設定と配備

OpenWrt の設定はリポジトリの `platform/openwrt/rootfs/` が正本で、[router-01](router.md) の手順でイメージに焼き込みます。**tailscaled の状態ファイル（端末の秘密鍵を含む）だけはリポジトリにもイメージにも入れません。** そのため、**ルータのイメージを作り直すと tailnet からは別端末になります**。次のどちらかで戻します。

1. **端末の身元を引き継ぐ（推奨）**: 作り直す前に `ssh root@192.168.10.1 'cat /etc/tailscale/tailscaled.state'` で状態ファイルを安全な場所へ退避し、新しいイメージで同じパスへ戻して `tailscale up` する。管理画面での再承認は不要。
2. **認証キーで参加し直す**: 管理画面で認証キーを発行し（Pre-approved: on、Tags: `tag:vpn` を推奨）、ルータで `tailscale up --advertise-routes=192.168.10.0/24 --auth-key=<キー>` を実行する。**ルートの再承認**が必要で、管理画面に古い端末が残っていれば Remove します。認証キーの値は `platform/sops/tailscale.sops.yaml`（`.example` 参照）にあり、シェル履歴へ残さない渡し方をします。

管理画面側の設定（ルート承認・tailnet DNS）は `tools/tailscale-net.py` で宣言どおりに揃えます。**管理画面の端末名は net-01 から移した時点のものを引き継いでいます。** 名前を変えた場合は、ツール冒頭の `HOSTNAME` も合わせてください。

```bash
TAILSCALE_API_TOKEN=$(sops --decrypt --extract '["TAILSCALE_API_TOKEN"]' platform/sops/tailscale.sops.yaml) \
  .venv/bin/python tools/tailscale-net.py status
```

API トークンは管理画面 → Settings → Keys → API access tokens で発行し、`platform/sops/tailscale.sops.yaml` へ入れます（期限は最大90日。切れたら再発行）。`status` は読むだけで、ルート承認と DNS の差分を出します。`apply` で適用します（2026-10-01 に適用済み）。

## tailnet DNS

- 広告ブロックを宅内・宅外で揃えるため、tailnet の global nameserver は
  **AdGuard Home（`192.168.10.1`）1つだけ**にし、`overrideLocalDNS` を有効にする。
  Tailscale 接続中の端末は、宅内 Wi-Fi でもモバイル回線でもこの resolver を使う
  （MagicDNS は有効のまま。`*.ts.net` は Tailscale が内部で解決する）。
- **split DNS は使わない。** AdGuard は `*.apextox.dpdns.org` も上流 DoH で
  引けるため、サフィックスごとの振り分けが要らない。
- 2026-10-01 より前は global nameserver が未設定のまま MagicDNS だけが有効で、
  `100.100.100.100` が全名前に SERVFAIL を返していた。スマホで Tailscale を
  繋ぐと「インターネットが繋がらない」ように見えた原因はこれ。
- **AdGuard（router-01）が停止すると、Tailscale 接続中の端末は名前解決できなくなる。**
  subnet router も同じ router-01 なので、ルータが落ちれば経路もDNSも同時に失う。
  予備 resolver を併記すると広告ブロックが漏れるため、あえて1つにしている。
  復旧時は IP 直打ちや `/etc/hosts` を使う。

## ローテーション

- 認証キーのローテーション: 管理画面で旧キーを失効 → 新しいキーで再登録する
  （端末の身元を状態ファイルで引き継いでいれば、失効だけでは切断されない）。
- 端末の失効: 管理画面で該当端末を Remove。ルータを作り直して身元を引き継が
  なかった場合は、古い端末が残っていないか確認する。

## 検証（N02の合格条件）

**一部完了（2026-10-01、dev-02 の `accept-dns` 有効で実測）。** 旧 net-01 時代の結果です。

- tailnet resolver が `192.168.10.1` になる（`tailscale dns status`）
- `100.100.100.100` が公開名（`example.com`）と内部名
  （`pve.apextox.dpdns.org` → `192.168.10.10`）を解決する
- `googleads.g.doubleclick.net` が AdGuard により `0.0.0.0` へ遮断される
- MagicDNS 名が引ける
- ルート `192.168.10.0/24` が承認されている

**未了:** ルータへ移したあとの宅外（モバイル回線）のスマホ実機で、通常・core-01 停止・K11 停止の各条件を確認する。許可外利用者が管理レンジへ到達できないこと（ACL）は、ポリシーに制限を入れるときに確認する。

## 経緯（net-01）

2026-09-14 に cloud VM `net-01`（`i-88933be43f442c6f4`、`192.168.10.103`）を作り、`platform/ansible/net.yml` と `roles/tailscale` で配備しました。2026-10-01 にルート承認と tailnet DNS を適用。2026-10-03 に端末の身元ごとルータへ移して net-01 は削除し、リポジトリからも `platform/terraform/services/net`・`net.yml`・`roles/tailscale` を削除しました。

## 確認コマンド

```bash
ssh root@192.168.10.1 'tailscale status'
ssh root@192.168.10.1 'tailscale ip -4'
ssh root@192.168.10.1 'tailscale debug prefs'
ssh root@192.168.10.1 'uci show tailscale'
TAILSCALE_API_TOKEN=$(sops --decrypt --extract '["TAILSCALE_API_TOKEN"]' platform/sops/tailscale.sops.yaml) \
  .venv/bin/python tools/tailscale-net.py status
host example.com 100.100.100.100
host pve.apextox.dpdns.org 100.100.100.100
```
