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

**状態**: **2026-10-14 に router-01 から切替済み。** ONU 直結で MAP-E・DHCP・DNS（AdGuard Home）・IPv6 中継・Tailscale を担当。router-01 は停止（削除していない）。DMZ（VLAN 30）は 2026-10-15 に作成（LAN4 は DMZ 専用。shakeserver のつなぎ替えは未）。ログは tarakoserver の Loki へ送る（UDP 1514）。

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
| LAN1 | サーバー | TL-SG605（1G）。tarakoserver・shakeserver（DMZ へ移す前） |
| LAN2 | サーバー（タグ無し）・DMZ（タグ付き VLAN 30） | K11 の LAN（`nic1`、2.5G）。K11 の `vmbr0` はまだ VLAN 非対応 |
| LAN3 | 個人端末 | デスクトップ（2.5G） |
| LAN4 | DMZ（タグ無し） | shakeserver（Raspberry Pi 5）を挿す予定 |

K11 の WAN（`nic0`）は空き。内蔵スイッチの番号は LAN1=7、LAN2=6、LAN3=5、LAN4=4、CPU 側=3。

## 区画と SSID

| SSID | 区画 | 帯域 | 暗号化 |
| --- | --- | --- | --- |
| `ditto-2hc355ek` | 個人端末（`192.168.40.0/24`） | 2.4／5／6GHz と MLO | 通常の電波は 2.4／5GHz が WPA2/WPA3、6GHz は WPA3。MLO の電波は WPA3 |
| `jumpluff-p7y45x7r` | ネット専用（`192.168.50.0/24`） | 2.4GHz | WPA2、端末間は分離 |
| `porygon-…` | サーバー（`192.168.10.0/24`） | 5GHz | WPA2/WPA3 |

- `ditto` と `jumpluff` のパスワードは Git に無い。`ssh -t root@192.168.10.1 /etc/shakecloud/set-wifi-key ditto`（または `jumpluff`）で入れる。
- `porygon` のパスワードは Flint 3 が生成した。`ssh root@192.168.10.1 cat /etc/shakecloud/porygon.key`。
- 管理用の VLAN は作っていない。`porygon` はサーバーの区画へつながり、Proxmox の画面（`https://192.168.10.10:8006`）へも入れる。
- MLO は GL.iNet の MLO 用の電波（`wlanmld2g`／`5g`／`6g`）を `ditto` と同じ名前で出している。MLO の親デバイス `mld0` は `hotplug.d/net/90-mld-personal` が個人端末のブリッジへ入れる。
- WPS は無効。
- 区画間の通信の方針は [VLAN 分離への切替](vlan.md)。

## 設定の入れ方

```bash
platform/flint3/deploy.sh 192.168.10.1                      # rootfs/ を置く（反映はしない）
ssh root@192.168.10.1 /etc/shakecloud/apply-segments        # 区画・SSID・区画間のファイアウォール・mDNS の中継
```

- `deploy.sh` は `/etc/AdGuardHome/config.yaml` も上書きする。稼働中の AdGuard Home は自分の形式へ書き換えているので、置いたら `/etc/init.d/adguardhome restart`。
- `apply-segments` は何度流してもよい。ネットワークと Wi-Fi を読み込み直すので、有線・無線とも数十秒切れる。
- `apply-router` は router-01 からの切替用。**稼働中の Flint 3 へ流し直さない**（切替前のバックアップを上書きする）。

## 設定のバックアップ

| 項目 | 内容 |
| --- | --- |
| 入れ方 | `tools/flint3-backup-install.sh`（何度流してもよい） |
| 取得 | K11 の `flint3-backup.timer`（毎日 4:30）。K11 の専用鍵は Flint 3 で `sysupgrade -b -` しか実行できない |
| 置き場所 | K11 の `/root/flint3-backups`（tar、60 日分）と `/root/flint3-config`（展開して git。差分は `git log -p`） |
| 復元 | tar を Flint 3 へ送って `sysupgrade -r <tar>` のあと再起動 |

## ファームウェアを更新したら

1. `opkg update && opkg install map ndppd conntrack`
2. `/etc/init.d/gl_ipv6 disable`（有効へ戻っていると、起動のたびに IPv6 の設定を書き換える）
3. `platform/flint3/deploy.sh 192.168.10.1` と `apply-segments`
4. `/etc/shakecloud/install-node-exporter`（監視の node_exporter。追加パッケージは更新で消える）
5. IPv4・IPv6・DNS を確認する

`iperf3` は opkg で入れない。ファーム内蔵の版とライブラリが食い違って動かなくなる。

## 純正ファームで足したもの

| ファイル | 理由 |
| --- | --- |
| `apply-router` の IPv6 有効化 | 初期状態は全インターフェースで IPv6 を止めている。MAP-E は IPv6 の上で動く |
| `89-mape-ce-address` | 純正の `map.sh` は CE アドレスをトンネルにしか付けない。上流の近隣要請に誰も応えず、IPv4 の戻りが全滅する |
| `92-lan-prefix-route-on-lan` | 内蔵スイッチの設定を変えると `br-lan` が作り直され、IPv6 を LAN へ流す経路が消える |
| `90-mld-personal` | Wi-Fi を読み込み直した直後、MLO の親デバイスがブリッジへ入らないことがあり、MLO でつながった端末にアドレスが配られない |
| `apply-segments` の Tailscale の転送（`shakecloud_ts_lan`） | GL の `/etc/firewall.tailscale.sh` は Tailscale が動き直すたびに、画面の「LAN へのアクセス」が切れていると `tailscale_lan` という名前の転送を消す。同じ名前を使っていたので消され、宅外からサーバーの区画へ届かなかった（2026-10-14・15）。名前を変え、「LAN へのアクセス」（`tailscale.settings.lan_enabled`）も入れる |
| Tailscale の経路を流し直す（`hotplug.d/iface/95-shakecloud-tailscale-routes`） | GL の `gl_tailscale` はインターフェースが変わるたびに `tailscale up --reset` し、GL の画面で選んだ経路しか流さない。2026-10-15、ネットワークの読み込み直しで `192.168.10.0/24`・`192.168.40.0/24` が消え、外のスマホが Tailscale 越しの DNS を引けずネットに出られなかった |
| ECM（ハードウェアオフロード）の IPv4 を止める（`init.d/shakecloud-ecm`・`hotplug.d/iface/99-shakecloud-ecm`） | 2026-10-14、ECM がネット専用の区画の通信を載せると TCP の 3 回目以降が外へ出ず、jumpluff の家電・スマホがインターネットに出られなかった。`gl_front_end_ipv4_stop` を 1 にすると直った |
| `apply-segments` の IPsec の削除 | 初期ルールが外から LAN へ ESP・UDP 500 を通す。IPv6 では LAN の機器が外から見える |
| `apply-segments` の `Block-LAN-mgmt-iot` の修正 | 初期値は `192.168.10.1` 宛てを塞ぐルールで、サーバーの区画から管理画面へ入れなくなる |
| AdGuard Home の起動後のフィルタ取得 | 回線が無い状態で起動するとフィルタが空のままになる。`/etc/init.d/adguardhome restart` |

## Tailscale

| 項目 | 値 |
| --- | --- |
| 端末 | `gl-be9300`（`100.91.7.69`）。router-01 の端末情報を引き継いだ |
| 宅外から入れる範囲 | `192.168.10.0/24`。個人端末の区画は流さない（2026-10-17。家の中の通信が Flint 3 の Tailscale を回って遅くなったため）。デスクトップ・ノート PC へは tailnet の名前で直接。ネット専用は入れない |
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
- DMZ（`192.168.30.0/24`）からサーバーの区画へは `dmz-db-clients` に書いたアドレスから pkdb（5432）だけ。今は誰も書いていない。
- GL.iNet の付属スクリプトとファームウェア更新が書き換える設定は、tarakoserver の `netmap-router-check.timer` が 5 分ごとに `apply-segments` と見比べる。崩れると `RouterConfigDrift`、点検が止まると `RouterCheckStale`。
- GL.iNet の `gl_tailscale` はネットワークが変わるたびに Tailscale を起動し直して経路を消すので、`95-shakecloud-tailscale-routes` が流し直す（約20秒、そのあいだ宅外から家の中へ届かない）。
- 開発用の VM（dev-01・dev-02）からは個人端末へ接続を始められる（実機のスマホへの adb など）。ほかのサーバーからは始められない。

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
- 2026-10-14: 宅外から Tailscale でサービスへ届かない不具合を修正。MLO、WPS 無効化、IPsec の初期ルール削除、開発用 VM → 個人端末の許可。
- 2026-10-14: ECM（ハードウェアオフロード）の IPv4 を止めた（jumpluff の家電がインターネットへ出られなかった）。設定を毎日 K11 へ取る `flint3-backup.timer`。
- 2026-10-15: DMZ（VLAN 30、LAN4 専用・LAN2 にタグ付き）を作成。そのときの読み込み直しで Tailscale の経路が消え、`95-shakecloud-tailscale-routes` を足した。syslog を tarakoserver の Loki へ送る。
- 2026-10-15: Tailscale → サーバーの区画の転送が GL の付属スクリプトに消されていたのを、名前を変えて直した。「LAN へのアクセス」を入れ、設定崩れの点検と警告を足した。
