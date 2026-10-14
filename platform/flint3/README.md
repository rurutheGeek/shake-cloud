# platform/flint3

Flint 3（GL-BE9300、純正ファーム 4.10.1）の設定。区画の設計は
[docs/operations/vlan.md](../../docs/operations/vlan.md)、実機の状態は
[docs/operations/handover.md](../../docs/operations/handover.md)。

router-01（`platform/openwrt/`）は設定ファイルを丸ごと置き換えるが、Flint 3 は
GL.iNet の初期設定に独自の項目が多いので、**必要な項目だけを `uci` で上書きする**。

| ファイル | 内容 |
| --- | --- |
| `deploy.sh` | `rootfs/` を Flint 3 へ置く（反映はしない） |
| `rootfs/etc/shakecloud/apply-router` | 区画なしのルーターにする。MAP-E・DHCP・IPv6 中継。10分以内に `confirm` しなければ巻き戻る |
| `rootfs/etc/shakecloud/apply-segments` | 区画（個人端末・ネット専用）、SSID、LAN3 の割当、区画間のファイアウォール、mDNS の中継。何度流してもよい |
| `rootfs/etc/shakecloud/set-wifi-key` | SSID のパスワードを対話で入れる（値を Git に置かないため） |
| `rootfs/etc/hotplug.d/net/90-mld-personal` | MLO の親デバイスを個人端末のブリッジへ入れる |
| `rootfs/etc/hotplug.d/iface/92-lan-prefix-route-on-lan` | LAN が作り直されたときに IPv6 の経路を張り直す |
| `rootfs/etc/shakecloud/rollback-router` | `apply-router` の前の状態へ戻して再起動する |
| `trial.sh` | 配線を変えない切替試験。K11 経由の VLAN 100 で ONU を Flint 3 へ届け、時間を区切って必ず router-01 へ戻す |
| `rootfs/etc/hotplug.d/iface/89-mape-ce-address` | MAP-E の CE アドレスを上流側のデバイスへ付ける。純正ファームの `map.sh` が付けないため（無いと IPv4 の戻りが全滅する） |
| `rootfs/etc/hotplug.d/iface/90-mape-ports` | MAP-E の 240 ポートを使い切る SNAT。router-01 と同じ |
| `rootfs/etc/hotplug.d/iface/91-lan-prefix-route` | 上流の /64 を `br-lan` へ向ける。router-01 と同じ |
| `rootfs/etc/ndppd.conf` | WAN 側の近隣要請への代理応答。router-01 と同じ |

追加パッケージは `map`・`ndppd`・`conntrack`。**ファームウェアを更新すると消える**ので、
更新後に `opkg install map ndppd conntrack` で入れ直す。`iperf3` は入れない
（ファーム内蔵の版とライブラリが食い違って動かなくなる）。

## 状態

2026-10-14 に router-01 から切り替えて稼働中。運用の手順・配線・既知の制約は
[docs/operations/flint3.md](../../docs/operations/flint3.md)。

`apply-router` と `trial.sh` は切替のためのもので、稼働中の Flint 3 へは流さない。
日常の変更は `apply-segments`（区画・SSID・区画間のファイアウォール・mDNS の中継）で入れる。
