---
title: Tailscale（router-01 上の subnet router）
updated: 2026-10-09
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
---

# Tailscale（router-01 上の subnet router）

> **更新日** 2026-10-09 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **router-01（OpenWrt）で稼働中（2026-10-03 にクラウドVM `net-01` から移設し、net-01 は削除）。** ルート承認と tailnet DNS（AdGuard Home）は 2026-10-01 に適用済み。**2026-10-09 にポリシーと端末タグを Git 管理へ移し、同日適用した。** 宅外端末での実機検証が未了。

宅外から管理LAN（`192.168.10.0/24`）へ戻るための Tailscale の subnet router です。[N02](../development/N02-tailscale.md) の復旧経路で、最初は cloud VM `net-01` に置いていましたが、2026-10-03 に **依存の最も少ない router-01（OpenWrt）の上へ移しました**。ルータは Proxmox ホスト（K11）上の VM なので、**K11 そのものが落ちれば使えない**点は変わりません。カバーするのは VM 単位の故障までです。真のアウトオブバンドが必要になったら、専用ルータ機や別ハードを検討します（[VPN比較](../architecture/vpn.md)）。

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
| ポリシーとタグ | `platform/tailscale/policy.yaml` が正本。`tools/tailscale-net.py apply` が管理画面のポリシーと端末のタグを揃える（2026-10-09 に適用） |

tailnet からの着信は `tailscale0` に入り、`tailscale` ゾーンから `lan` へ転送されます。**送信元の書き換え（SNAT）は tailscaled 自身が nftables で行う**ため、ファイアウォール側で `masq` はしません。Tailscale の通信は端末側からの発信と中継で成立するので、WAN 側のポート開放も不要です。

## 設定と配備

OpenWrt の設定はリポジトリの `platform/openwrt/rootfs/` が正本で、[router-01](router.md) の手順でイメージに焼き込みます。**tailscaled の状態ファイル（端末の秘密鍵を含む）だけはリポジトリにもイメージにも入れません。** そのため、**ルータのイメージを作り直すと tailnet からは別端末になります**。次のどちらかで戻します。

1. **端末の身元を引き継ぐ（推奨）**: 作り直す前に `ssh root@192.168.10.1 'cat /etc/tailscale/tailscaled.state'` で状態ファイルを安全な場所へ退避し、新しいイメージで同じパスへ戻して `tailscale up` する。管理画面での再承認は不要。
2. **認証キーで参加し直す**: 管理画面で認証キーを発行し（Pre-approved: on、Tags: `tag:vpn` を推奨）、ルータで `tailscale up --advertise-routes=192.168.10.0/24 --auth-key=<キー>` を実行する。**ルートの再承認**が必要で、管理画面に古い端末が残っていれば Remove します。認証キーの値は `platform/sops/tailscale.sops.yaml`（`.example` 参照）にあり、シェル履歴へ残さない渡し方をします。

管理画面側の設定（ルート承認・tailnet DNS・ポリシー・端末タグ）は `tools/tailscale-net.py` で宣言どおりに揃えます。ポリシーとタグの正本は `platform/tailscale/policy.yaml` で、管理画面で直接編集せず、差分があればこのツールで戻します。**`HOSTNAME` は subnet router の端末名（既定 `router-01`）です。** 管理画面で名前を変えた場合は合わせてください。

```bash
sops exec-env platform/sops/tailscale.sops.yaml \
  '.venv/bin/python tools/tailscale-net.py status'
```

API トークンは管理画面 → Settings → Keys → API access tokens で発行し、`platform/sops/tailscale.sops.yaml` へ入れます（期限は最大90日。切れたら再発行）。`status` は読むだけで、ルート承認・DNS・ポリシー・タグの差分を出します。`apply` はポリシーを丸ごと置き換え（Tailscale 側の `tests` を通してから）、端末にタグを付け、ルート承認と DNS の差分を適用します（ルート承認と DNS は 2026-10-01、ポリシーとタグは 2026-10-09 に適用済み）。

## ポリシー（誰が誰へ届くか）

**ポリシーとタグの正本は `platform/tailscale/policy.yaml`。** 考え方は、人の端末（タグなし）はどこへでも届き、サーバーにはタグを付けて、サーバーから出る通信を必要な宛先だけに絞ることです。タグを付けた端末は利用者の権限を引き継がないので、1台が破られても tailnet と LAN へ広がりません。

| タグ | 端末 | 行ける先 |
| --- | --- | --- |
| （なし） | 利用者のPC・スマホ | tailnet の全端末と subnet router の先の LAN |
| `tag:relay` | negitoroserver | web-01 の 80/443 だけ（LAN のルートも SSH も無い） |
| `tag:outpost` | tarakoserver | negitoroserver の 80・9100 と shakeserver の 9100・9101・8090 だけ |
| `tag:web` | web-01 | 外へ出る許可なし（受けるだけ） |
| `tag:home` | shakeserver | 外へ出る許可なし |
| `tag:router` | router-01 | 外へ出る許可なし（subnet router） |

- ポリシーの `tests` が壊れたルールを適用前に弾きます（`tag:relay` から管理レンジや他のサーバーの SSH へ届かないこと、など）。`apply` は先に Tailscale 側の検査（`acl/validate`）へ通します。
- **タグ付けは端末側で再ログインするまで戻せません。** 付け外しは `policy.yaml` の `devices` を直して `apply` します。
- `status` は `policy.yaml` に無いのにタグが付いた端末も報告します。誰が付けたか分からないタグはここで見つけます。

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

**未了:** ルータへ移したあとの宅外（モバイル回線）のスマホ実機で、通常・core-01 停止・K11 停止の各条件を確認する。**ACL は 2026-10-09 に適用済み**（管理レンジへ届くのは人の端末だけで、`tag:relay` は web-01 の 80/443 だけ。`tools/tailscale-net.py status` が差分なしを返すことを確認）。

## 経緯（net-01）

2026-09-14 に cloud VM `net-01`（`i-88933be43f442c6f4`、`192.168.10.103`）を作り、`platform/ansible/net.yml` と `roles/tailscale` で配備しました。2026-10-01 にルート承認と tailnet DNS を適用。2026-10-03 に端末の身元ごとルータへ移して net-01 は削除し、リポジトリからも `platform/terraform/services/net`・`net.yml`・`roles/tailscale` を削除しました。

## 確認コマンド

```bash
ssh root@192.168.10.1 'tailscale status'
ssh root@192.168.10.1 'tailscale ip -4'
ssh root@192.168.10.1 'tailscale debug prefs'
ssh root@192.168.10.1 'uci show tailscale'
sops exec-env platform/sops/tailscale.sops.yaml \
  '.venv/bin/python tools/tailscale-net.py status'
host example.com 100.100.100.100
host pve.apextox.dpdns.org 100.100.100.100
```
