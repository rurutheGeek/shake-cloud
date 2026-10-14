---
title: Flint 3（家庭内ルーター）
updated: 2026-10-14
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
---

# Flint 3（家庭内ルーター）

> **更新日** 2026-10-14 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **2026-10-14 に router-01 から切替済み。** ONU 直結で MAP-E・DHCP・DNS（AdGuard Home）・IPv6 中継・Tailscale を担当。router-01 は停止（削除していない）。

## 構成

| 項目 | 値 |
| --- | --- |
| 機種・ファーム | GL.iNet GL-BE9300、純正 4.10.1（OpenWrt 23.05派生、カーネル 5.4、fw4） |
| アドレス | `192.168.10.1`（サーバー）、`192.168.40.1`（個人端末）、`192.168.50.1`（ネット専用） |
| 回線 | MAP-E（v6プラス）。外部 IPv4・PSID・ポート範囲は router-01 と同じ |
| 設定の正本 | `platform/flint3/`、区画は `platform/terraform/network.yaml` の `segments` |
| ログイン | `ssh root@192.168.10.1`（鍵 `id_ed25519_pve`）。管理画面は `https://192.168.10.1/` |
| 追加パッケージ | `map`・`ndppd`・`conntrack`（ファーム更新で消える） |
| 出荷時のバックアップ | K11 の `/srv/bulk/backups/flint3/2026-10-13-factory`（eMMC の小領域12個と初期設定） |

## 配線

| Flint 3 のポート | 区画 | 接続先 |
| --- | --- | --- |
| WAN | — | ONU |
| LAN1 | サーバー | TL-SG605（1G） |
| LAN2 | サーバー | K11 の LAN（`nic1`、2.5G） |
| LAN3 | 個人端末 | デスクトップ（2.5G） |
| LAN4 | サーバー | 空き |

K11 の WAN（`nic0`）は空き。内蔵スイッチの番号は LAN1=7、LAN2=6、LAN3=5、LAN4=4、CPU 側=3。

## 区画と SSID

| SSID | 区画 | 帯域 | 暗号化 |
| --- | --- | --- | --- |
| `ditto-2hc355ek` | 個人端末（`192.168.40.0/24`） | 2.4／5／6GHz | 2.4／5GHz は WPA2/WPA3、6GHz は WPA3 |
| `jumpluff-p7y45x7r` | ネット専用（`192.168.50.0/24`） | 2.4GHz | WPA2、端末間は分離 |
| `porygon-…` | サーバー（`192.168.10.0/24`） | 5GHz | WPA2/WPA3 |

- `ditto` と `jumpluff` のパスワードは Git に無い。`ssh -t root@192.168.10.1 /etc/shakecloud/set-wifi-key ditto`（または `jumpluff`）で入れる。
- `porygon` のパスワードは Flint 3 が生成した。`ssh root@192.168.10.1 cat /etc/shakecloud/porygon.key`。
- 管理用の VLAN は作っていない。`porygon` はサーバーの区画へつながる。
- 区画間の通信の方針は [VLAN 分離への切替](vlan.md)。

## 設定の入れ方

```bash
platform/flint3/deploy.sh 192.168.10.1                      # rootfs/ を置く（反映はしない）
ssh root@192.168.10.1 /etc/shakecloud/apply-segments        # 区画・SSID・区画間のファイアウォール・mDNS の中継
```

- `deploy.sh` は `/etc/AdGuardHome/config.yaml` も上書きする。稼働中の AdGuard Home は自分の形式へ書き換えているので、置いたら `/etc/init.d/adguardhome restart`。
- `apply-segments` は何度流してもよい。ネットワークと Wi-Fi を読み込み直すので、有線・無線とも数十秒切れる。
- `apply-router` は router-01 からの切替用。**稼働中の Flint 3 へ流し直さない**（切替前のバックアップを上書きする）。

## ファームウェアを更新したら

1. `opkg update && opkg install map ndppd conntrack`
2. `/etc/init.d/gl_ipv6 disable`（有効へ戻っていると、起動のたびに IPv6 の設定を書き換える）
3. `platform/flint3/deploy.sh 192.168.10.1` と `apply-segments`
4. IPv4・IPv6・DNS を確認する

`iperf3` は opkg で入れない。ファーム内蔵の版とライブラリが食い違って動かなくなる。

## 純正ファームで足したもの

| ファイル | 理由 |
| --- | --- |
| `apply-router` の IPv6 有効化 | 初期状態は全インターフェースで IPv6 を止めている。MAP-E は IPv6 の上で動く |
| `89-mape-ce-address` | 純正の `map.sh` は CE アドレスをトンネルにしか付けない。上流の近隣要請に誰も応えず、IPv4 の戻りが全滅する |
| `92-lan-prefix-route-on-lan` | 内蔵スイッチの設定を変えると `br-lan` が作り直され、IPv6 を LAN へ流す経路が消える |
| `apply-segments` の `Block-LAN-mgmt-iot` の修正 | 初期値は `192.168.10.1` 宛てを塞ぐルールで、サーバーの区画から管理画面へ入れなくなる |
| AdGuard Home の起動後のフィルタ取得 | 回線が無い状態で起動するとフィルタが空のままになる。`/etc/init.d/adguardhome restart` |

## Tailscale

| 項目 | 値 |
| --- | --- |
| 端末 | `gl-be9300`（`100.91.7.69`）。router-01 の端末情報を引き継いだ |
| 宅外から入れる範囲 | `192.168.10.0/24`、`192.168.40.0/24`。ネット専用は入れない |
| 範囲を変える | `tailscale set --advertise-routes=…` と、管理画面（API）での経路の承認 |
| 宅外端末の DNS | AdGuard Home（`192.168.10.1`）。`tailscale0` からの `:53` を `:3053` へ転送 |
| 端末情報 | `/etc/tailscale/tailscaled.state`（秘密値。Git に置かない） |

### 家の中で遠回りになる場合

Tailscale を入れた Windows・スマホは、家の中にいても、家のアドレス（`192.168.10.x`・`192.168.40.x`）宛ての通信を Flint 3 の Tailscale 経由で送る。Flint 3 が暗号化を肩代わりするので遅くなる。

| 避け方 | 向いている場面 |
| --- | --- |
| 接続先を Tailscale の名前（`game-01`、`ouchithegeek`）で登録する | Moonlight、RDP。家でも外でも端末同士が直接つながる |
| 家では Tailscale を切る | 相手に Tailscale が入っていない場合 |
| その端末だけ「サブネットを使用」をオフにする | 家から持ち出さない端末（デスクトップ） |

## 既知の制約

- 同じ宛先へ短時間に何度もつなぐと、一部の接続が途中で止まる（ニチバンのサイトへ30回で12回）。MAP-E の 240 ポートを使い回すため。router-01 では起きなかった。
- AdGuard Home の管理画面（`:3000`）は GL.iNet の管理画面のログインを要求する。`adguard.apextox.dpdns.org`（SSO 経由）からは入れない。
- ルーターを入れ替えた直後は、上流が CE アドレスの持ち主を覚え直すまで約5分 IPv4 が止まる。
- 6GHz と 5GHz・2.4GHz を束ねる MLO は未設定。WPS の無効化は設定済みで、次の Wi-Fi 再読込から効く。
- DMZ（`192.168.30.0/24`）は未作成。

## router-01 へ戻す

1. ONU のケーブルを Flint 3 の WAN から K11 の WAN（`nic0`）へ挿し直す。
2. Flint 3 を止めるか、LAN の `192.168.10.1` を外す（同時に名乗らせない）。
3. `ssh root@192.168.10.10 'qm set 101 -onboot 1 && qm start 101'`。

router-01 の Tailscale の端末情報は Flint 3 が使っている。router-01 の Tailscale は起動させない。

## 実施記録

- 2026-10-13: 到着。ファームを 4.8.1 から 4.10.1 へ更新。出荷時のバックアップを取得。Aterm との性能比較（`experiments/20261014_wifi_ap_comparison/`）。
- 2026-10-13〜14: K11 経由の VLAN 100 で ONU を届ける切替試験を3回。1回目で CE アドレスの不具合、2回目で復帰時の5分待ちを確認。
- 2026-10-14 00:10: router-01 から切替。00:56 に ONU を WAN へ直結。
- 2026-10-14: AdGuard Home、Tailscale（端末情報の引き継ぎ）、区画と SSID、LAN3 の個人端末化、mDNS の中継。Aterm は撤去。router-01 は停止、自動起動なし。
