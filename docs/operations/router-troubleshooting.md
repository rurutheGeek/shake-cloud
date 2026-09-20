# ルータがつながらないときの調べ方（備忘録）

更新日: 2026-09-20。2026-09-20 の切替で実際に起きた 2 つの障害と、その切り分けを
そのまま残したものです。ルータ本体の手順は
[router-01（OpenWrt・自作ルータ）](router.md)、設計は
[N06 ルータ自作（OpenWrt）](../development/N06-router.md) が正本です。

## 今回起きたこと（要約）

Aterm から router-01 へ切り替えた直後、**IPv4 が一切通らず、IPv6 だけが動いて
いるように見えた**。原因は 2 つあり、どちらも「設定が 1 箇所足りない」だけでした。

| # | 症状 | 原因 | 直し方 |
| --- | --- | --- | --- |
| 1 | IPv4 が全滅。IPv6 は動く | `wan` に `legacymap '1'` が無く、CE アドレスが JPNE の期待と 1 バイトずれていた | `network` に 1 行 |
| 2 | LAN 端末が IPv6 を取れない | `dhcp.wan6` が `master '1'` だけで、relay のモードが無かった | `dhcp` に 3 行 |
| 3 | インターネットへ ping が通らない | fw4 が icmp の SNAT を落とし、割当外の ICMP id で出ていた | `90-mape-ports` を有効化 |
| 4 | 再起動後、固定アドレスの端末だけ IPv6 を失う | odhcpd の `ndp relay` が端末のアドレス作成時しか学習しない | `ndppd` へ差し替え |

いずれも**ルータ自身は正常に見える**のが厄介な点です。インターフェースは UP、
アドレスも付き、ログにもエラーが出ません。

## 入り口：どこから入るか

切替後は LAN 端末から SSH で入れます。イメージに焼いてある管理者鍵は `root` 用です。

```bash
ssh root@192.168.10.1
```

LAN が落ちていて入れないときは、Proxmox のシリアルコンソールが唯一の入口です
（抜けるのは Ctrl-O）。

```bash
ssh root@192.168.10.126 'qm terminal 101'
```

## 手順：上から順に見る

### 1. まずスクリプトを回す

LAN 端末（dev-b など）から。個別に見る前に、これで当たりが付きます。

```bash
python3 tools/verify-router.py
```

### 2. 「出ているか」と「返ってきているか」を分ける

**MAP-E の障害はここでほぼ決まります。**

```bash
ssh root@192.168.10.1 'ip -s link show map-wan'
```

- **TX が増えて RX が 0** → こちらの送信は成立し、**返りが来ていない**。→ 3 へ
- TX も 0 → そもそも送れていない。トンネル自体（`ifstatus wan`）を見る

補強として、NAT の状態も見ます。全部 `[UNREPLIED]` なら同じ結論です。

```bash
ssh root@192.168.10.1 'grep -c UNREPLIED /proc/net/nf_conntrack; grep UNREPLIED /proc/net/nf_conntrack | head -3'
```

### 3. 「返りの宛先」を上流に聞く

返りが来ないとき、**上流が誰を探しているか**を見ると答えが出ます。上流は戻り
パケットを届ける前に、その宛先を Neighbor Solicitation で呼びます。

```bash
ssh root@192.168.10.1 'tcpdump -nti eth0 -Q in "icmp6 and ip6[40]==135"'
```

```
IP6 <上流のリンクローカル> > ff02::1:ff<…>:
    ICMP6, neighbor solicitation, who has <上流が期待する CE アドレス>
```

この `who has` の住所を、**自分が実際に名乗っている住所**と突き合わせます。

```bash
ssh root@192.168.10.1 'ip -6 addr show dev eth0'
```

**一致しなければ、それが原因です。** 上流は誰もいない宛先へ返事を送り続け、
それが上流側で捨てられます。こちらからの送信は成立するので、ルータ側のログ・
カウンタには何の異常も出ません。

### 4. 形式の違いを確かめる

今回は 1 バイトずれていました。OpenWrt の既定は RFC 7597、JPNE が使うのは
draft-03 系です。`map.sh` は `LEGACY` を `mapcalc` に渡すだけなので、実機で
両方の計算を出して比べられます。

```bash
ssh root@192.168.10.1 \
  'LEGACY=1 mapcalc wan6 type=map-e,ipv6prefix=240b:10::,prefix6len=31,\
ipv4prefix=106.72.0.0,prefix4len=15,psidlen=8,offset=4,ealen=25,\
br=2404:9200:225:100::64 | grep IPV6ADDR'
```

```
インターフェース ID（下位 64 ビット）の並びだけが違う。

上流が聞く（draft-03） : 00 <IPv4 4byte> <PSID> 00   ← LEGACY=1 の出力と一致
OpenWrt 既定（RFC 7597）: 00 00 <IPv4 4byte> <PSID>
                             ^^ 1 バイト右へずれている
```

**グローバル IPv4・PSID・ポートセットはどちらの形式でも同じ値になります。**
そのため `/tmp/map-wan.rules` を読んでも、`verify-router.py` のポート検査
（`map_ports`）が PASS でも、この違いには気づけません。**アドレスそのものを
比べるまで分かりません。**

### 5. IPv6 が LAN へ来ていないとき

**症状で分岐します。**

**(a) 端末が IPv6 アドレス自体を持っていない** → RA が届いていません。

```bash
ssh root@192.168.10.1 'tcpdump -nti br-lan "icmp6 and (ip6[40]==133 or ip6[40]==134)"'
```

`router advertisement` が出ていなければ relay が動いていません。odhcpd は
**モードをインターフェースごとに持つ**ので、下流（`lan`）だけ `relay` にしても
中継は始まりません。上流（`wan6`）にも要ります。

```bash
ssh root@192.168.10.1 'uci show dhcp.wan6'
```

`master '1'` に加えて `ra`・`dhcpv6` が `relay` であること（`ndp` は
`disabled` が正しい。下記）。

**(b) アドレスと既定ルートはあるのに外へ出られない** → 戻りが LAN へ
転送されていません。手順 2・3 と同じ「出ているが返らない」の形です。

```bash
ssh root@192.168.10.1 'ip -6 route | grep br-lan'
```

**委譲された `/64` が `dev br-lan` で入っていること。** これは
`/etc/hotplug.d/iface/91-lan-prefix-route` が入れます。無ければ手で流せます。

```bash
ssh root@192.168.10.1 'ACTION=ifup INTERFACE=wan6 /etc/hotplug.d/iface/91-lan-prefix-route'
```

代理応答は `ndppd` の担当です。動いていることを確認します。

```bash
ssh root@192.168.10.1 'ps w | grep [n]dppd; cat /etc/ndppd.conf | grep -A2 rule'
```

**ここで odhcpd の `ndp relay` へ戻さないでください。** あれは端末がアドレスを
作る瞬間しか学習できず、**ルータを再起動すると固定アドレスの端末（サーバ類）が
IPv6 を失います**。2026-09-20 に実機で踏んでいます（N06）。

## 紛らわしいので先に知っておくこと

- **BR への IPv6 ping が通っても、MAP-E が通るとは限りません。** BR は誰からでも
  応答します。「BR に ping が通る＝疎通 OK」ではありません。
- **IPv6 だけ動いているように見えても、LAN 端末の IPv6 は別問題です。** 今回は
  ルータの WAN 側だけが IPv6 を持ち、LAN 端末は IPv4・IPv6 の両方が死んでいました。
- **インターネットへの `ping` が通らないときは、まず `90-mape-ports` を疑う。**
  ICMP が MAP-E の割当ポートへ SNAT されるのは、fw4 ではなく
  `/etc/hotplug.d/iface/90-mape-ports` の働きです（fw4 は icmp の SNAT を
  落とす）。これが動いていないと**回線は正常なのに ping だけ通らず**、
  `verify-router.py` の `pmtu` も FAIL します。

  ```bash
  ssh root@192.168.10.1 'nft list table ip mape_nat | head'
  ssh root@192.168.10.1 'logread -e mape-ports'   # "installed 15 port sets"
  ```

  出ていなければ手で流せます（`ifup wan` は不要）。

  ```bash
  ssh root@192.168.10.1 'ACTION=ifup INTERFACE=wan /etc/hotplug.d/iface/90-mape-ports'
  ```

## 最後の手段：Aterm に戻す

原因が分からず家のネットを早く戻したいときは、配線を戻すのが確実です。手順は
[router.md のロールバック](router.md)。要点だけ:

1. ONU のケーブルを Aterm の WAN ポートへ戻す
2. `ssh root@192.168.10.126 'qm stop 101'`（`192.168.10.1` の競合を避ける）
3. Aterm の RT/BR/CNV スイッチを RT へ戻し、保存した `.bin` を復元する

## 実機に直接入れた設定について

調査中に `uci set` で実機へ入れた値は、**再起動では消えませんが、VM を作り直すと
イメージの内容に戻ります。** 直した内容は必ず
`platform/openwrt/rootfs/etc/shakecloud/config/` の正本へ反映し、
`tests/test_router.py` に検証を足してください（今回の 2 件は反映済み）。

```bash
# 正本を稼働中のルータへ配る（ルータ上では手編集しない）
scp -r platform/openwrt/rootfs/etc/shakecloud/. root@192.168.10.1:/etc/shakecloud/
ssh root@192.168.10.1 '/etc/shakecloud/apply && reboot'
```
