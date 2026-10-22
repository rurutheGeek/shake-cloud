---
title: VLAN 分離への切替
updated: 2026-10-22
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
---

# VLAN 分離への切替

> **更新日** 2026-10-22 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 個人端末（Wi-Fi `ditto` と Flint 3 の LAN3）とネット専用（Wi-Fi `jumpluff`）を実機で分離済み（2026-10-14）。DMZ は Flint 3 側を作成済み（2026-10-15、LAN4 は DMZ 専用）。shakeserver の LAN4 へのつなぎ替えと、K11 の VLAN 対応（DMZ の VM 用）は未。管理は予約のみ。実機の設定は [Flint 3](flint3.md)。

## 区画

正本は `platform/terraform/network.yaml` の `segments`。

| VLAN | 区画 | 範囲 | 所属 | K11 のトランク |
| --- | --- | --- | --- | --- |
| 10 | サーバー | `192.168.10.0/24`（現行のまま） | apextox、基盤VM、利用者VM、Raspberry Pi 2台 | タグなし |
| 20 | 管理（予約） | `192.168.20.0/24` | 当面は作らない | — |
| 30 | DMZ | `192.168.30.0/24` | shakeserver（Raspberry Pi 5、LAN4。Minecraft など）、DMZ の VM（K11 の VLAN 対応のあと） | タグ付き |
| 40 | 個人端末 | `192.168.40.0/24` | デスクトップ（Flint 3 の LAN3）、ノートPC、スマホ（SSID `ditto-…`） | 通さない |
| 50 | ネット専用 | `192.168.50.0/24` | 家電、プリンター（SSID `jumpluff-…`）。TL-SG605 の先はまだサーバーの区画 | 通さない |

## 区画間の通信

区画間は既定で拒否し、Flint 3 のファイアウォールで次だけを通す。

| 送信元 → 宛先 | 方針 |
| --- | --- |
| 全区画 → インターネット | 許可 |
| 全区画 → Flint 3 | DHCP・DNS のみ。管理画面と SSH はデスクトップ・dev-02・Tailscale のみ |
| 個人端末 → サーバー | 許可。apextox の `:8006`・SSH はデスクトップのみ（Proxmox のファイアウォールで送信元を絞る） |
| 個人端末 → ネット専用 | 印刷と家電のローカル制御に要るポートのみ |
| サーバー → ネット専用 | apps-01 からプリンター・Eufy・SwitchBot、monitor-01 からの監視のみ |
| サーバー → 個人端末 | 拒否 |
| DMZ → サーバー | pkdb（apps-01:5432）のみ。送信元は `dmz-db-clients` に書いた VM だけ |
| 開発用の VM（dev-01・dev-02）→ 個人端末 | 許可（実機のスマホへの adb・Flutter の実機実行） |
| ネット専用 → 他区画 | 拒否 |
| Tailscale → サーバー・個人端末 | 許可。ネット専用へは入れない |

IPv6 は `/64` が1つしか来ないため、サーバー区画だけへ中継する。

## 同じ区画の中（基盤VMの受信）

Flint 3 は区画の間しか絞れないので、同じサーバー区画の中の横の広がりは、Proxmox の VM ファイアウォールで止める（2026-10-22〜）。

| VM | 受ける通信 | 担当 |
| --- | --- | --- |
| core-01 | 入口（80・443）、NetBox API（8000、サーバー区画から）、SSH（サーバー・個人端末）、node_exporter（tarakoserver）、mDNS、ping | 05-seed |
| cloud-01 | ポータルとAPI（80・443）、Garage の S3 API（3900、サーバー・個人端末）、SSH、node_exporter、ping | 10-platform |
| 利用者VM | クラウドAPIのセキュリティグループ | クラウドAPI |

- 正本は `platform/terraform/firewall.yaml`。書いていない受信は落ちる（Garage の管理API 3903・RPC 3901、core-01 の CUPS 631 など）。送信は絞らない
- 口を開けたら `firewall.yaml` に足し、`tools/tf 05-seed apply`（core-01）か `tools/tf 10-platform apply`（cloud-01）で配る
- 締め出されたら K11 の root で `pvesh set /nodes/apextox/qemu/<VMID>/firewall/options -enable 0`（VMID は core-01 が 150、cloud-01 が 140）

## 切替の順序

1. Flint 3 を既存LANと同じ構成（区画なし、`192.168.10.1`）でルーターにする（router-01 からの本切替）。
2. 個人端末・ネット専用の区画と SSID を足す。K11 側は変更なし。
3. apextox と Flint 3 の管理面を送信元で絞る。
4. DMZ（下の「DMZ の作り方」）。`vmbr0` が VLAN 未対応の間、API は DMZ への作成を断る。

## DMZ の作り方

家にいて、K11 の物理コンソールか Proxmox の画面が使えるときに行う。2 で失敗すると K11 上の全 VM が LAN から切れる（dev-02 も止まる）。

| 順 | 作業 | 切れるもの |
| --- | --- | --- |
| 1 | `ssh root@192.168.10.1 /etc/shakecloud/apply-dmz`（2026-10-15 に実施済み） | 有線・無線が数十秒。Tailscale の経路も約20秒消える |
| 2 | K11 で `sh pve-vlan-aware.sh apply`（`tools/pve-vlan-aware.sh` を置いて実行）。SSH と VM の通信を確かめて `confirm`。しなければ 10 分で元に戻る | 失敗すると K11 上の全 VM |
| 3 | `python3 tools/site-yaml.py --api` で `bridge_vlan_aware: true` にし、`platform/ansible/cloud.yml` で API を配備し直す | API が数秒 |
| 4 | `tools/tf services/pentest apply`（`subnet_id = subnet-dmz`） | なし |
| 5 | pentest-01 で `sudo sh check-segments.sh` | なし |
| 6 | Flint 3 の `/etc/shakecloud/dmz-db-clients` に pentest-01 のアドレスを書いて `apply-dmz`、`sudo sh check-segments.sh --db`。終わったら消して `apply-dmz` | なし |

- `apply-dmz` は LAN4 を DMZ 専用（タグ無し）にし、LAN2（K11）へ VLAN 30 をタグ付きで足す。サーバーの区画はタグ無しのまま。shakeserver は LAN4 につなげば DMZ（`192.168.30.12`）に入る（K11 の VLAN 対応は要らない）。
- DMZ → サーバーは `dmz-db-clients` に書いたアドレスから pkdb（`192.168.10.105:5432`）だけ。ファイルが無ければ何も通さない。web 公開用の VM を DMZ に置いたら、そのアドレスを書く。
- サーバー → DMZ は許可（配備の SSH・監視）。
- pentest-01 は 1 vCPU・512MiB。外向きの SG は全許可のまま（侵害された VM の立場）。

## 元に戻す

- K11: `sh pve-vlan-aware.sh rollback`（`/root/interfaces.pre-vlan-aware` へ戻す）。
- Flint 3: `uci delete network.dmz; uci delete network.vlan_dmz; uci delete dhcp.dmz; uci delete firewall.dmz` のあと `apply-segments`。

## この段階で分離されないもの（残り）

- 内部サービス（S3・DB・ゲーム）と公開入口は、まだ管理VLAN・管理LAN上です。4区分に分けるのは後段。
- 同一VLAN内はルータを通らないため、Proxmox の VM ファイアウォール（セキュリティグループ）と、将来の Cilium NetworkPolicy を併用します（[ネットワーク・SSO](../architecture/network-auth.md)）。
- Garage の管理API（`:3903`）は、VLAN 切替後も**利用者VLANから届きうる**ので、到達先をクラウドAPIだけに絞るのは別途 VM ファイアウォールで行います。
