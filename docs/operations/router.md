# router-01（OpenWrt・自作ルータ）

更新日: 2026-09-20。状態: **切替済み・N06 の完了条件をすべて満たした。**
`verify-router.py` は 5 PASS / 0 FAIL、ホスト再起動での自動復旧も確認済み
（全断 53 秒）。IPv6 の近隣代理は odhcpd ではなく **ndppd** が担当する。
**実機へ `uci`／`opkg` で入れた変更はイメージにまだ焼かれていない**ので、
VM を作り直す前に `build.sh` でイメージを再生成すること。
（開発計画と調査結果は [N06 ルータ自作（OpenWrt）](../development/N06-router.md) が正本。
**つながらなくなったときは
[ルータがつながらないときの調べ方](router-troubleshooting.md)** から読む）

Aterm WG1200HP4 を AP モードへ移し、K11（`apextox`）上の OpenWrt VM を
家庭内ルータにします。ルータ設定は Git（UCI ファイルとイメージ）に移します。

**素の OpenWrt から何を変えたかだけを一覧にしたページ**は
[router-01 の設定まとめ](router-config.md) です（ネットワーク機器に慣れていない
人向け）。

## 正本と構成

| 対象 | 場所 |
| --- | --- |
| UCI 設定（ルータの設定そのもの） | `platform/openwrt/rootfs/etc/shakecloud/config/` |
| DNS（AdGuard Home）の設定 | `platform/openwrt/rootfs/etc/adguardhome/adguardhome.yaml` |
| イメージのビルド宣言 | `platform/openwrt/openwrt.yaml` |
| ビルド | `platform/openwrt/build.sh`（出力は `dist/openwrt-router.raw`） |
| VM の宣言（2 NIC・起動順・リンク状態） | `platform/terraform/router.yaml` |
| VM の Terraform | `platform/terraform/router/`（state は `shake-cloud/router/`） |

```
ONU ──→ nic0 (WAN)  ┐
                     ├─ K11 / Proxmox ── router-01（OpenWrt）── 192.168.10.1
TL-SG605 ←── nic1 (LAN) ┘                    │
   └─ Aterm（APモード・Wi-Fi専用）───────────┘
```

| OpenWrt | Proxmox | bridge | 接続先 |
| --- | --- | --- | --- |
| `eth0` | net0 | `vmbr1`（本作業で追加） | ONU |
| `eth1` | net1 | `vmbr0`（既存） | スイッチ・Aterm・各VM |

**`vmbr1` にはホストの IP を与えません。** 管理 IP は今までどおり `vmbr0` 側
（`192.168.10.10`）に残ります。

### 切替で変わる配線（ケーブルは2本）

1. **ONU の LAN ケーブル**: Aterm の WAN ポート → **K11 の空きポート（`nic0` = WAN）**。
   - ONU のケーブルが届くか、事前に長さを確認する。
2. **Aterm の上流ケーブル（TL-SG605 行き）**: Aterm の **LAN ポート → WAN ポート**へ
   挿し替える（1ポート分動かすだけ）。
   - BR（ブリッジ）モードの上流は **WAN ポート**へ繋ぐのが公式手順
     （NEC のブリッジ接続、同型機のプロバイダ設定ガイド）。
   - Aterm の LAN ポートに残すのは Raspberry Pi 4・Switch 2 などのローカル機器。

```
ONU ── nic0 [K11] nic1 ── TL-SG605 ──┬── Windows デスクトップ（有線）
                                       ├── Raspberry Pi 5
                                       └── Aterm WAN
                                            └── Aterm LAN ── Pi 4 / Switch 2 / 空き
```

- **K11 に今刺さっているケーブルは動かさない**。それは `nic1`（`vmbr0` = LAN）で、
  TL-SG605 への幹線。ここを抜くと管理LANごと落ちる。
- Wi-Fi は Aterm のまま。SSID・暗号化キーもそのまま（初期化された場合を除く）。



## 切替前に決めておくこと

- **K11 が落ちると家のネットも落ちます。** Proxmox の再起動・カーネル更新が
  全断になります。復旧経路の `net-01` も同じホスト上にあるため、宅外からも
  届かなくなります（[net-01（Tailscale subnet router）](net.md)）。
  **方針（2026-09-19）: 受容＋コールドスペア。** 計画メンテは人がいるときに
  行い、K11 が直らない故障のときは Aterm をルータへ戻します（下記
  「K11 のメンテナンス」）。
- **Aterm のモード切替は設定を初期化します。** 切替前に Aterm の管理画面で
  設定を保存（エクスポート）し、Wi-Fi の SSID・暗号化キーを**運用メモ**から
  再投入できるようにします。**秘密値はこの文書と Git に書きません。**
  具体的な保存・控え方は次節。
- **Aterm の管理 IP は `192.168.10.2`**（dnsmasq の MAC 予約。`.2〜.19` は
  機器帯で、DHCP プールは `.20〜.99`）。Aterm 側は DHCP クライアントのままでよい。
- 切替は家の全利用者に影響します。全断は数分です。時間を調整してから行います。

### Aterm の設定を保存し、Wi-Fi の値を控える

**切替で Aterm が初期化された場合に戻せるように**、次の2つを残します。値は
Git に入れず、`.local/` など Git 管理外の運用メモへ書きます。

1. **設定ファイルの保存**（今のルータモードのまま）
   - ブラウザで `http://aterm.me/`（または `http://192.168.10.1/`）を開き、
     ユーザー名 `admin` ＋ 管理者パスワードでログイン。
   - ［詳細な項目を表示］→「メンテナンス」−「設定値の保存＆復元」→
     「ファイルへ保存」。`2026-09-19_aterm_config.bin` のように日付を付けて保存。
   - **管理者パスワードはこのファイルに含まれない。** 別途控える（未変更なら
     本体ラベルの「Web PW」8桁）。
2. **Wi-Fi の値**
   - 工場出荷のプライマリ（5GHz）は本体ラベルの `aterm-XXXXXX-a` と13桁の
     暗号化キー（2.4GHz はバンドステアリングで同じ設定）。
   - 変更している場合・セカンダリ SSID を使っている場合は「Wi-Fi（無線LAN）設定」
     →「Wi-Fi詳細設定（2.4GHz / 5GHz）」→「対象ネットワークを選択」で
     **両バンド・両 SSID 分**の SSID と暗号化キーを控える。
3. **戻し方**（詳細は「ロールバック」）: 電源を切って RT/BR/CNV スイッチを RT へ
   戻し、電源投入後に「設定値の保存＆復元」で 1 のファイルを復元する。

### 機器帯と Aterm の住所（`.2〜.19`）

`192.168.10.2〜.19` は**ネットワーク機器・常時稼働サーバの帯**で、DHCP プール
（`.20〜.99`）の外です。**予約の正本は NetBox**（宣言は
`platform/netbox/devices.yaml`）で、`tools/netbox-dhcp-sync.py` が
`/etc/dnsmasq.d/netbox-reservations.conf` を生成します。**UCI に `config host` を
手書きしません**（重複すると dnsmasq が起動に失敗します）。

| 住所 | 機器 | MAC |
| --- | --- | --- |
| `.2` | Aterm（AP） | `80:22:a7:8f:27:80` |
| `.3` | プリンタ | `f8:a2:6d:a5:e9:fb`（`wlan0`） |
| `.10` | Proxmox ホスト `apextox` | `c8:ff:bf:0d:fd:6d` |
| `.11` | tarakoserver（Pi 4） | `e4:5f:01:f2:b8:dc` |
| `.12` | shakeserver（Pi 5） | `2c:cf:67:2c:e3:4d` |

予約の反映と確認:

```bash
sops exec-env platform/sops/netbox.sops.yaml \
  'python3 tools/netbox-dhcp-sync.py pull'
ssh root@192.168.10.1 'cat /etc/dnsmasq.d/netbox-reservations.conf'
ping -c2 192.168.10.2     # Aterm（リース更新後に .2 へ移る）
```

詳しい分担とトラブルは [NetBox の使い方](netbox.md#lanのipとルータのdhcpを同期する)。

Aterm の UI を開く必要があるときは、BR モードでは `aterm.me` が使えないので
`http://192.168.10.2/` を直接開きます。住所が分からず開けないときは強制 DHCP
サーバ機能（電源を切り、らくらくスタートを押したまま電源を入れ、CONVERTER が
緑点滅したら離す → `http://192.168.1.210/`）を使い、設定後は**再起動して強制
DHCP を止めます**。

### DNS と広告遮断（AdGuard Home）

DNS の窓口は **AdGuard Home**（`192.168.10.1:53`）です。広告・トラッカーを
遮断し、上流は DoH（Cloudflare / Google）で暗号化します。dnsmasq は DHCP と
ローカル名だけを担当し、DNS は `:5353` に移っています。

```
端末 ──▶ AdGuard（:53）──DoH──▶ Cloudflare / Google
              │  *.lan だけ
              ▼
        dnsmasq（127.0.0.1:5353）＝ DHCP・ローカル名
```

- **ローカル名は `.lan` を付けて引きます**（`aterm.lan`・`tarakoserver.lan`）。
  1語の名前（`aterm`）は AdGuard から dnsmasq へ転送できません（末尾一致のみ）。
  `*.apextox.dpdns.org` は今までどおり DoH 側で解決します。
- **端末が使う DNS は DHCPv4 で配る `192.168.10.1` です。** IPv6 の RDNSS は
  JPNE の上流 RA に RDNSS が無いため配れません（odhcpd の relay は上流 RA の
  RDNSS を書き換える方式）。実測で確認済み（2026-09-20）。ISP 側が変われば
  `dhcp.lan.dns` の1行で AdGuard へ書き換わります。
- **管理画面は HTTPS 入口から**（`https://adguard.apextox.dpdns.org`、SSO）。
  ルータの `:3000` はファイアウォールで services-01 だけに開けています。
  SSH トンネルでも開けます:
  `ssh -L 3000:192.168.10.1:3000 root@192.168.10.1` → `http://localhost:3000/`
- 設定の正本は `platform/openwrt/rootfs/etc/adguardhome/adguardhome.yaml`。
  反映は scp 後に `/etc/init.d/adguardhome restart`（UCI と違い reboot 不要）。
  パッケージは `openwrt.yaml` に入っているので、イメージ再ビルドでも入ります。
- **作業ディレクトリは `/etc/adguardhome/data`**（UCI の `workdir`）。既定の
  `/var/lib/adguardhome` は tmpfs で、再起動するとフィルタのキャッシュが消え、
  WAN が上がる前の起動では再取得に失敗して次回更新まで遮断が効きません
  （実機で踏んで修正済み）。

```bash
ssh root@192.168.10.1 'nslookup doubleclick.net 192.168.10.1'  # 0.0.0.0 なら遮断
ssh root@192.168.10.1 'nslookup aterm.lan 192.168.10.1'        # ローカル名
```

運用の詳細（管理画面の開き方・フィルタ更新・トラブル）は
[DNS と広告遮断（AdGuard Home）](adguard.md)。

- **ルータの管理画面（LuCI）**は `https://router.apextox.dpdns.org` でも
  開けます（**SSO なし**。identity が止まっていても開ける復旧経路にするため）。
  IP 直は `http://192.168.10.1`。**ログインには root パスワードが要ります**
  （未設定。SSH 鍵で入って `passwd` で設定する。パスワードは Git に置かない）。

## 1. ホスト側の準備（既存ネットに影響しない）

`vmbr1` を作り、実体のない `nic2` の定義を消します。**Proxmox の物理コンソール
か IPMI を手元に用意してから**行います（bridge を誤ると SSH も API も届かなく
なります）。

```bash
ssh root@192.168.10.10 'cp /etc/network/interfaces /etc/network/interfaces.bak-$(date +%F) && cat /etc/network/interfaces'
```

`/etc/network/interfaces` に次を足し、`iface nic2` のブロック（実体なし）を
削除します。

```
auto vmbr1
iface vmbr1 inet manual
        bridge-ports nic0
        bridge-stp off
        bridge-fd 0
        # WAN 用。ホストの IP は与えない。nic0 に ONU を挿すまでリンクは無い。
```

```bash
ssh root@192.168.10.10 'ifreload -a'
ssh root@192.168.10.10 'ip -br link show vmbr1; ip -4 addr show vmbr1'
```

- `vmbr1` が UP で、**IPv4 アドレスを持たない**こと。
- `vmbr0` と `192.168.10.10` が今までどおりであること。
- `nic0` / `nic1` のリンク速度が 1000Mbps であること（`nic0` は ONU 接続後）。

```bash
ssh root@192.168.10.10 'for i in nic0 nic1; do echo "== $i"; ethtool $i | grep -E "Speed|Duplex"; done'
```

`nic1` のリンク断が続いていないかも確認します（N06「LAN ケーブル不良」）。
100Mbps でリンクしていたら**切替を止めてケーブルを疑います**。

site.yaml はこの変更後もそのまま再生成できます（管理 IP を持つ bridge だけを
選ぶため。`tools/site-yaml.py` を参照）。

```bash
set -a && . .local/pve-readonly.env && set +a
python3 tools/site-yaml.py --api
tools/tf 10-platform plan -detailed-exitcode   # 差分なし
```

## 2. イメージのビルド

```bash
platform/openwrt/build.sh
ls -l platform/openwrt/dist/openwrt-router.raw
```

Image Builder（`openwrt.yaml` で版とチェックサムを固定）に、`rootfs/` の UCI
設定と管理者の SSH 公開鍵（`platform/terraform/access.yaml`）を焼きます。
MAP-E のパラメータは `rootfs/etc/shakecloud/config/network` が持っています。

## 3. VM の配備（リンクを落としたまま）

`platform/terraform/router.yaml` の `wan_connected` / `lan_connected` で両 NIC を
リンクダウンにした状態で作ります。この段階では既存 LAN に一切影響しません
（192.168.10.1 の重複も DHCP の二重化も起きない）。

**WAN は切替前に有効化しておきます。** 私（opencode）の応答はインターネット
越しなので切替中は会話できず、WAN を後から上げる操作ができないためです。
nic0 にケーブルが無い間はリンクが上がらないだけで無害で、ケーブルを挿した
瞬間に MAP-E が始まります。LAN は最後までダウンにしておき、切替時に
Proxmox UI から上げます（手順 4・5）。

`tools/tf router` は他の管理モジュールと同じく、`platform/sops/s3.sops.yaml` と
`platform/sops/proxmox.sops.yaml` の資格情報を SOPS から環境変数で渡します。

```bash
tools/tf router init
tools/tf router plan
tools/tf router apply
```

起動後の確認はシリアルコンソールで行います（LAN はまだリンクダウン）。

```bash
ssh root@192.168.10.10 'qm config 101'          # net0=vmbr1, net1=vmbr0
ssh root@192.168.10.10 'qm terminal 101'        # 抜けるのは Ctrl-O
```

**起動順だけは Terraform で設定しません。** Proxmox は `startup` の設定に
`Sys.Modify` on `/` を要求し（PVE の API の特別扱い）、`terraform@pve` には
その広い権限を与えていないためです。ホストで一度だけ設定します
（VM を作り直したら再実行。値の正本は `platform/terraform/router.yaml`）。

```bash
ssh root@192.168.10.10 'qm set 101 -startup order=1,up=30'
ssh root@192.168.10.10 'qm config 101 | grep -E "^(onboot|startup):"'
```

`onboot: 1` と `startup: order=1,up=30` が出れば、ホスト再起動時にルータが
他の VM より先に起動します（`up` は「次の VM を起動するまで待つ秒数」）。

コンソールで `eth0` が WAN、`eth1` が LAN になっていること（MAC で対応）と、
`/etc/shakecloud/config/` が反映されていることを確認します。

```
ip -br link
uci show network | head -30
cat /etc/config/network
```

**切替まではコンソールだけが入口です**（両 NIC がリンクダウンなので SSH は
届きません）。`platform/terraform/access.yaml` の管理者鍵は焼いてあるので、
切替後は鍵で SSH できます。LuCI（`https://192.168.10.1/`）には root の
パスワードが必要ですが、**イメージに秘密値は焼かない**ので、初回に一度だけ
コンソールから `passwd` で設定します。

## 4. 切替

**Aterm は OpenWrt の WAN 側（MAP-E）の疎通を確認するまでルータのまま残します。**
LAN を OpenWrt に移すのは最後の一手です。

### 手順（インターネットが無い時間帯でも進められる形）

**私（opencode）の応答はインターネット越しなので、切替中は会話できません。**
そのため、WAN は切替前に有効化しておき（済み）、LAN は Proxmox UI で上げます。
Terraform の apply は復旧後にまとめて行います。

1. **Aterm の設定エクスポートと Wi-Fi 値の控え**（済み。前節）。
2. **WAN の有効化**（済み）: `router.yaml` の `wan_connected: true` を適用済み。
   nic0 にケーブルが無い間は無害で、**挿した瞬間に MAP-E が始まります**。
3. ONU の LAN ケーブルを K11 の `nic0` へ挿し替える（ここから家のネット断）。
   - `ethtool nic0` で 1000Mbps リンクを確認する。
   - 不安なら Proxmox UI の Console（router-01）で
     `ifstatus wan`・`cat /tmp/map-wan.rules` を確認する。
4. Aterm を **AP（BR）モード**へ切り替える。
   - 電源を切った状態で、TL-SG605 へ行くケーブルを Aterm の **LAN ポートから
     WAN ポート**へ挿し替える（BR モードの上流は WAN ポート。前節の配線図）。
   - 背面の RT/BR/CNV スイッチを BR 側へ切り替えて電源を入れる
     （ACTIVE ランプが橙点灯すれば完了）。
   - 初期化された場合は SSID・暗号化キーを再投入する（運用メモから）。
   - **DHCP サーバ機能が止まったことを確認**する（二重 DHCP の回避）。
   - 管理 IP は dnsmasq の予約で `.2`（前節）。Aterm 側の操作は不要。
5. **Proxmox UI**（`https://192.168.10.10:8006`）で LAN リンクを上げる:
   router-01 → Hardware → **net1** → Edit → **「切断（Disconnect）」のチェックを外す**。
   CLI なら `ssh root@192.168.10.10 'qm set 101 -net1 link_down=0'`。
   - これで `192.168.10.1` が OpenWrt になり、DHCP・DNS・インターネットが戻る。
6. 端末で DHCP を取り直す（Windows は `ipconfig /renew`。`192.168.10.1` の
   ARP が古い間は 1 分ほど待つか、Wi-Fi を付け直す）。
7. **インターネットが戻ったら**声をかける。こちらで `lan_connected` を `true` に
   して apply し（実機は UI で上がっているので差分は解消される）、
   `tools/verify-router.py --pve root@192.168.10.10` で検証する。

**192.168.10.1・DHCP・DNS を Aterm と OpenWrt の両方が名乗る瞬間を作らないで
ください。** Aterm の AP 化（手順 4）→ LAN のリンクアップ（手順 5）の順を守ります。

### ロールバック

OpenWrt の疎通が確認できるまで Aterm の設定は残します。戻すときは:

1. router-01 を停止するか、Proxmox UI で net0/net1 を「切断」にする
   （オフラインなら `qm set 101 -net0 link_down=1 -net1 link_down=1`。オンラインに
   戻ったら `router.yaml` を `false` に戻して `tools/tf router apply`）。
2. ONU のケーブルを Aterm へ戻す。
3. Aterm をルータモードへ戻し、エクスポートした設定を復元する
   （モード切替で初期化されるため、復元が要る）。

Aterm の AP 化を最後にすることで、切替当日の作業は「配線と設定の復元」だけで
戻せる範囲に収めます。

### K11 のメンテナンスとコールドスペア

方針: **計画メンテの全断は許容し、直らない故障のときは Aterm をルータへ戻す。**
外出中の遠隔復旧は行いません。

- **計画メンテ**（Proxmox・カーネル更新、ハード再起動）: 利用者へ予告してから
  実施します。ルータ VM は `on_boot` と起動順 `order=1` で自動起動するので、
  再起動が終わればネットは自力で戻るはずです。**切替直後に一度ホストを再起動し、
  `tools/verify-router.py` で自動復旧を確認します**（N06 の完了条件）。
  注意: dev-b など K11 上の作業環境も一緒に落ちます。
- **ハング時は watchdog で自動復帰します**（SP5100 TCO、約10秒でリセット →
  `router-01` 自動起動。全断は約1〜2分）。引き金は game1 の iGPU パススルー操作で、
  リソース起因ではないことを実測で確認済み。詳細と確認方法は
  [power.md](power.md) の「K11 が固まったときの自動復旧」を参照。
- **game1（VM 100）は `qm stop` で止めない。必ず `qm shutdown` を使います。**
  iGPU（`c6:00.0`）は FLR に非対応で、VM 停止時のリセット手段が**バスリセット
  しかありません**。`c6:00` は APU 内のひとつの部品で、ホストが使用中の
  USB（`.3`/`.4`。UPS とキーボードがここ）・暗号チップ（`.2`）・音声（`.5`/`.6`）
  が同居しているため、GPU を戻すためのリセットが一族を道連れにしてホストが即死
  します。`qm stop` は QEMU を即殺するので、ゲストが GPU を握ったままこの
  リセットに入ります。`qm shutdown` なら ACPI 経由でゲストの systemd が
  amdgpu を正規手順で手放してから終わります。

  ```bash
  # ○ ゲストOSを正常終了させてから QEMU を終わらせる
  ssh root@192.168.10.10 'qm shutdown 100 --timeout 120'

  # × これで 2026-09-20 14:57 にホストごと落ちた（＝家中のネット断）
  ssh root@192.168.10.10 'qm stop 100'
  ```

  2026-09-20 の実測では `qm stop` 3 回のうち 1 回でハングしました
  （13:05・14:43 は生存、14:57 でハング）。**確率的に落ちるので「前回平気
  だった」は根拠になりません。** 停止直後にホストのログが一切残らない
  （OOM も lockup も MCE もなし）のがこの故障の特徴です。

  **Web UI（ブラウザ）ではボタン名で覚えます。** 右上の青い
  「**シャットダウン**」ボタンを**そのまま押す**のが `qm shutdown` です。
  右隣の `∨` を開いて出てくるメニューは、ほぼ全部が危険側です。

  | Web UI の項目 | コマンド | 可否 |
  | --- | --- | --- |
  | （青いボタン本体）**シャットダウン** | `qm shutdown` | ○ これを使う |
  | 再起動 | `qm reboot` | △ 内部で停止→起動するのでリセットを伴う |
  | 一時停止 / ハイバネート | `qm suspend` | △ GPU の状態は解決しない |
  | **停止** | **`qm stop`** | × 2026-09-20 14:57 はこれ |
  | リセット | `qm reset` | × 強制リセット |

  ゲストが固まって「シャットダウン」が完了しないときだけ「停止」を使います。
  そのときは**家のネットが落ちうると理解した上で**押してください
  （watchdog が効けば 1〜2 分で戻ります）。
- **停電**: K11 を UPS のバッテリー側へ接続し、BIOS の「AC 復帰で自動起動」を
  有効にしておくと、復電後にネットまで自動で戻ります（[power.md](power.md)）。
- **K11 が起動しない・故障したとき（コールドスペア）**:
  1. ONU の LAN ケーブルを Aterm の WAN ポートへ戻す。
  2. K11 がまだ動いているなら router-01 を停止する（`qm stop 101`。
     `192.168.10.1` の競合を避ける）。
  3. Aterm の RT/BR/CNV スイッチを RT へ戻して電源を入れ、必要なら保存した
     `.bin` を「設定値の保存＆復元」で復元する。
  4. 家のネットが戻ったら、K11 を落ち着いて修復する。
- **外出中に K11 が落ちた場合、遠隔から戻す手段はありません。** `net-01` も
  K11 上なので当てにしません（受容）。専用ルータ機（K11 の外）や 4G の細い出口
  は、必要になった時点で別作業として検討します。

## 5. 設定の更新

- **UCI の変更（推奨）**: `platform/openwrt/rootfs/etc/shakecloud/config/` を
  直して、稼働中のルータへ scp する。正本は Git で、ルータ上では手編集しない。

  ```bash
  # 末尾の /. は「ディレクトリの中身を上書きする」の意。付けないと
  # /etc/shakecloud/shakecloud ができてしまう。
  scp -r platform/openwrt/rootfs/etc/shakecloud/. root@192.168.10.1:/etc/shakecloud/
  ssh root@192.168.10.1 '/etc/shakecloud/apply && reboot'
  ```

  `apply` は `network` の再読込を含むため、SSH が切れることがあります。
  迷ったら **reboot を付ける**のが確実です。

- **イメージの更新（版を上げるとき・初期状態を作り直すとき）**:
  `platform/openwrt/build.sh` で作り直し、`tools/tf router apply`。

  **`terraform@pve` は置きイメージを削除できません。** `/storage/local` には
  `Datastore.AllocateTemplate`（アップロード）しか与えておらず、
  `Datastore.Allocate`（削除）は無いため、**2 回目以降の apply は
  「古いファイルの destroy」で HTTP 403 になります**。権限を広げず、先に
  root トークンで古いファイルだけ消してから apply します（次の plan は
  `0 to destroy` になります）。

  ```bash
  TOKEN=$(sops -d platform/sops/proxmox-root.sops.yaml     | grep -E '^PROXMOX_VE_API_TOKEN:' | sed 's/^[^:]*: *//')
  curl -sk -X DELETE -H "Authorization: PVEAPIToken=$TOKEN"     'https://192.168.10.10:8006/api2/json/nodes/apextox/storage/local/content/local:import/openwrt-router.raw'
  tools/tf router plan   # 0 to destroy になる
  tools/tf router apply
  ```

  **稼働中の VM には影響しません。** 置きイメージは作成時に取り込むだけで、
  動いているディスクは `local-lvm:vm-101-disk-0` の別ボリュームです。
  イメージは `filesha256` で差分検出されますが、**VM のディスクは自動では
  入れ替わりません**。メンテナンス時間に VM を作り直します
  （`tools/tf router apply -replace=proxmox_virtual_environment_vm.router`。
  **LAN の MAC が変わる**点に注意）。

## 6. 検証（N06 の完了条件）

**まず検証スクリプトを回します。** LAN 端末（dev-b など）から実行し、
`192.168.10.1` が本当にルータ VM か（Aterm が残っていないか）、外部ポートが
MAP-E の割当に収まっているか、PMTU が 1460 か、IPv6 relay が効いているかを
まとめて見ます。`--pve` を付けるとホストのリンク速度も確認します。

```bash
python3 tools/verify-router.py
python3 tools/verify-router.py --pve root@192.168.10.10   # ホストのリンクも見る
```

**切替前でも実行できます**（現在の Aterm 回線の基準値が取れ、切替後に
PSID が変わっていないことの比較になります）。個別の確認は以下です。

ルータのコンソール、または LAN の端末から実行します。

```bash
# MAP-E の割当を確認する（mapcalc の結果がそのまま残る）
cat /tmp/map-wan.rules
ip -d link show map-wan

# 外部 IPv4 とポート。STUN は LAN 内の任意の Linux から（N06「実値の求め方」）
curl -s4 ifconfig.co/json
# 観測ポートの中央 8bit が PSID で、240 個の割当範囲に収まること

# PMTU 1460（ICMP ヘッダ 8 + IP ヘッダ 20 を引いた 1432 で割らない）
ping -M do -s 1432 8.8.8.8

# IPv6: LAN 端末が RA で GUA を受け、外部へ出られること
ip -6 addr; ip -6 route; ping -6 -c2 2001:4860:4860::8888
```

- LAN 端末が `192.168.10.20〜.99` を DHCP で取得し（`.2〜.19` は機器帯）、IPv4・IPv6 の双方で
  外部へ到達する。
- Aterm が AP としてのみ動作し、**DHCP を返さない**。Wi-Fi の両 SSID で接続
  できる。
- `nic1` が 1000Mbps を維持し、リンク断が起きない。8 並列で 180Mbps 前後。
- Proxmox ホストと全 VM が従来どおり到達でき、`https://pve.apextox.dpdns.org:8006`
  と各サービスの HTTPS 名が引ける。
- ホスト再起動後、ルータ VM が自動起動してインターネットが自力で復旧する。

## 実施記録

- 2026-09-19: `platform/openwrt/build.sh` でイメージを作成
  （`dist/openwrt-router.raw`、このときの sha256 は `593dd771…eafb229`）。
- 2026-09-19: ホストへ `vmbr1`（nic0、IP なし）を追加し、実体のない `nic2` の
  定義を削除。`vmbr0` と `192.168.10.10` は無傷。`tools/site-yaml.py --api` は
  「すでに一致」で差分なし。
- 2026-09-19: `tools/tf router apply` で VM 101（`router-01`）を作成。
  イメージは `local:import/openwrt-router.raw`。net0/net1 とも `link_down`。
  `qm set 101 -startup order=1,up=30` をホストで設定し、再 plan は No changes。
- 2026-09-19: シリアルコンソールで OpenWrt 24.10.8・ホスト名 `router-01`・
  LAN `192.168.10.1`・MAP-E パラメータ・relay 設定・SSH 鍵 3 本を確認。
  両 NIC はリンクダウンのまま（既存 LAN へ影響なし）。
- 2026-09-20: 切替を実施。router-01 が `192.168.10.1` を持ち、LAN・DHCP・DNS・
  IPv6（ルータの WAN 側）は動いたが、**IPv4 だけが一切通らない**状態になった。
- 2026-09-20: 上の障害を `legacymap` の欠落と特定し、修正して IPv4 が復旧。
  経緯は N06「[切替後に IPv4 だけ通らなかった原因](../development/N06-router.md)」。
  `verify-router.py` の `map_ports` が PASS（STUN 6 サンプルがすべて MAP-E の
  割当内）。**実機には `uci set` で入れてあるが、
  正本は `rootfs/etc/shakecloud/config/network`** で、VM を作り直す前に
  イメージを焼き直すこと。
- 2026-09-20: LAN へ IPv6 が配られていなかった（`br-lan` に RA が 1 つも
  出ない）。原因は `dhcp.wan6` に relay のモードが無かったこと。`master '1'`
  だけでは中継は始まらず、**master 側にも `ra`/`dhcpv6`/`ndp` = `relay` が要る**。
  3 行足して `odhcpd` を再起動したら LAN 端末が GUA と既定ルートを取得し、
  `verify-router.py` の `ipv6` が PASS になった。正本は
  `rootfs/etc/shakecloud/config/dhcp`。
- 2026-09-20: ポートセット分散スクリプト（`90-mape-ports`）を実機で検証し、
  `extras/`（未検証・無効）から `rootfs/etc/hotplug.d/iface/` へ移して**既定で
  有効**にした。投入直後の 226 接続が 15/15 ブロックへ分散し、割当外は無し。
  **同時に ICMP も割当内へ入り、インターネットへの ping と `ping -M do` に
  よる PMTU 実測（1432 = MTU 1460）ができるようになった。**
- 2026-09-20: `router.yaml` の `lan_connected` が `false` のまま実機とずれて
  いた（切替当日に LAN を Proxmox UI で上げたため。手順 7 の apply が未実施）。
  **この状態で `tools/tf router apply` すると LAN のリンクが落ち、家中のネットが
  止まる。** `true` に直して `tools/tf router plan -detailed-exitcode` が
  `No changes`（exit 0）になることを確認した。
- 2026-09-20: `tools/verify-router.py` の 2 つの不具合を修正。ルータへ SSH する
  ユーザが固定で、鍵を焼いてある `root` にできなかった（`--router-user` を追加）。
  その先で IPv4 の所属判定が文字列のまま行われ `AttributeError` になっていた。
  修正後、**5 PASS / 0 FAIL**（`host_links` は `--pve` 未指定の WARN）。
- 2026-09-20: K11 を再起動して自動復旧を確認（上記）。**全断は 53 秒。**
  同時に、**odhcpd の `ndp relay` では再起動後に固定アドレスの端末が IPv6 を
  失う**ことが判明した（下記）。
- 2026-09-20: IPv6 の近隣代理を odhcpd から **ndppd** へ差し替えた。
  `openwrt.yaml` に `ndppd` を追加、`rootfs/etc/ndppd.conf` と
  `rootfs/etc/hotplug.d/iface/91-lan-prefix-route`（委譲 /64 を `br-lan` へ）を
  追加し、`dhcp` の `ndp` を両側 `disabled` に。学習で入っていた `/128` 経路を
  すべて消した状態で LAN 端末の IPv6 が通ることを確認した。
  **実機には `opkg install ndppd` で入れてある**（overlay に残るので再起動では
  消えない）。イメージを焼き直せば正本から入る。
- 2026-09-20: ルータ VM を再起動して ndppd 構成の永続性を確認。ndppd が自動
  起動し、`91-lan-prefix-route` が /64 を `br-lan` へ入れ、`90-mape-ports` も
  走った。**`/128` の学習経路がゼロの状態**で LAN 端末の IPv6 が通ることと、
  **上流が一度も見たことのない一時アドレス**（`…::dead:beef`）でも外部と
  往復できることを確認（代理応答が効いている証拠）。再起動後の
  `verify-router.py` は **5 PASS / 0 FAIL**。
- 2026-09-20: **`*.apextox.dpdns.org` が LAN から一切引けなくなっていた。**
  切替から数時間、誰も気づいていなかった（インターネットは通っていたため）。
  原因は dnsmasq の `rebind_protection`。これらの名前は Cloudflare の**公開**
  レコードが **LAN のアドレス**（`192.168.10.x`）を指しており、rebind
  protection は「公開 DNS が返したプライベートアドレス」を捨てる。Aterm は
  捨てていなかったので、切替で初めて出た。`list rebind_domain
  'apextox.dpdns.org'` を足して解決（protection 自体は残す）。
  `tests/test_router.py` が `dns.yaml` のゾーンと突き合わせて検査する。
- 2026-09-20: イメージを再ビルドし、`tools/tf router apply` で Proxmox の
  置きイメージを入れ替えた（`No changes` まで確認）。VM は無傷
  （`import_from` の in-place 更新のみで、稼働中のディスクは
  `local-lvm:vm-101-disk-0` の別ボリューム）。
  ビルドには dev-b へ `make` `gawk` `bzip2` の追加が必要だった。
- 2026-09-20: **DNS の窓口を dnsmasq から AdGuard Home へ移した。**
  `opkg install adguardhome`（0.107.57）→ 設定を配置 → dnsmasq を `:5353` へ
  （`port`・`noresolv`・`server 127.0.0.1#53`）→ AdGuard 起動。実測:
  `example.com` は DoH で解決、`doubleclick.net` は `0.0.0.0`（遮断）、
  `aterm.lan` は dnsmasq 経由で `.2`、`nextcloud.apextox.dpdns.org` は `.101`、
  ルータ自身の解決も通る。フィルタは約18万件。
  **IPv6 の RDNSS は配れない**（JPNE の上流 RA に RDNSS が無く、odhcpd の
  relay は上流 RA の RDNSS を書き換える方式のため。実測確認）。端末は DHCPv4 の
  `192.168.10.1` を使う。
  **24.10 のパッケージは既定で `/etc/adguardhome.yaml` を見る**ため、UCI
  `adguardhome.config.config` を `/etc/adguardhome/adguardhome.yaml` に合わせた
  （`uci-defaults/97-shakecloud-adguard` が同じことをする）。
  正本は `rootfs/etc/adguardhome/adguardhome.yaml` と `dhcp`。
- 2026-09-20: **ルータ VM を再起動して AdGuard の永続性を確認。** 起動時に
  `interface.*.up` の trigger で自動起動し、`:53` を取り戻した（dnsmasq は
  `:5353`）。ただし**フィルタのキャッシュが `/var`（tmpfs）にあり、起動直後は
  WAN 未確立で再取得に失敗 → 約18万件が空のまま、次回更新（既定24時間）まで
  遮断が効かなかった**。UCI `adguardhome.config.workdir` を
  `/etc/adguardhome/data` へ移して修正し、`uci-defaults/97` にも反映した。
  `aterm.lan` などの予約名は仕様どおりリース取得後に戻る（リースDBは tmpfs の
  ため、再起動直後は引けない）。
- 2026-09-20: **再起動後に Wi-Fi 端末が「インターネットなし」になった。**
  原因は dnsmasq が DHCP で DNS サーバー（option 6）を配っていなかったこと
  （実測: Offer に 1/3/15/28/51/54 はあるが 6 が無い）。再起動でリースDBが空に
  なり、端末が取り直した時点で DNS が消えた。切替直後は Aterm の古いリースが
  残っていたため気づかなかった。`dhcp.lan` に
  `list dhcp_option '6,192.168.10.1'` を足し、Offer/ACK に option 6 が入ること
  と、スマホが AdGuard で `connectivitycheck.gstatic.com` を引けることを実測。
  あわせて NetBox 同期ツールが**再起動直後の「リース無し」で台帳を削除**して
  いたのを直した（起動がリース期間未満なら削除しない。[netbox.md](netbox.md)）。

- 2026-09-20: **AdGuard の管理画面に HTTPS 入口を付けた。**
  `adguard.apextox.dpdns.org`（services-01 の Caddy → ルータの
  `192.168.10.1:3000`、Forward Auth で SSO）。ルータのファイアウォールは
  `:3000` を services-01 だけに許可し、LAN からの直接アクセス（SSO 迂回）を
  塞いだ。設定は `dns.yaml`・`stacks/identity/configure.py`・
  `rootfs/etc/shakecloud/config/firewall`・`adguardhome.yaml`。

- 2026-09-20: **予約名（`.lan`）が静的 IP の端末で引けない問題を直した。**
  dnsmasq の `dhcp-host` は**実際にリースを配った端末にしか DNS 名を付けない**
  （実機 2.93 で確認。リース無しの `dhcp-host` は NXDOMAIN、`host-record` は
  解決）。Pi・AP・Proxmox のように IP を自分で持つ機器は DHCP に来ないため、
  `tarakoserver.lan` などの予約名が永久に生えなかった。
  `tools/netbox-dhcp-sync.py` が予約から `host-record=<名前>.lan,<IP>` も生成
  するようにし、`pull` で反映する（`tests/test_netbox_dhcp_sync.py` が検査）。

- 2026-09-22: **ブロックリストを足した。** 既存の AdGuard DNS filter だけでは
  網羅が足りないため、HaGeZi's Pro Blocklist（HostlistsRegistry の
  `filter_48`、`id: 48`）を `filters` に追加。`stats.grafana.org` の遮断は
  トラッカーなので意図どおり（Grafana の匿名統計は停止済み）。反映は scp →
  `/etc/init.d/adguardhome restart` → フィルタ更新 API。

## ホスト再起動での自動復旧（確認済み・2026-09-20）

N06 の完了条件。K11 を再起動し、`onboot` と `startup order=1` でルータ VM が
先に上がってインターネットが自力で戻ることを確認した。**家のネットが止まって
いたのは 53 秒**（ルータ VM の停止から復帰まで）。ホスト自体の停止・起動を
含めた全体では約 4 分半。

| 見たもの | 結果 |
| --- | --- |
| ルータ VM の自動起動 | 他の VM より先に起動した |
| IPv4（MAP-E） | 自力で復旧。`curl` も `ping` も通る |
| `legacymap` の CE アドレス | 維持された |
| `90-mape-ports` | **起動時に自動実行**（`installed 15 port sets`） |
| 全 VM | 再起動前と同じ組が戻った |

**このとき IPv6 の欠陥が見つかった**（次節）。再実施するときは次の手順。
**数分の全断になるので、利用者がいない時間帯に行う。**

```bash
ssh root@192.168.10.10 'qm config 101 | grep -E "^(onboot|startup):"'
ssh root@192.168.10.10 reboot
# 戻ったら
python3 tools/verify-router.py --pve root@192.168.10.10
```

## 既知の課題（未確定）

- ~~**odhcpd の relay モード**~~（2026-09-20 解決）。切替直後に LAN へ RA が
  出なかったのは設定の欠落が原因だったが、**`ndp relay` には本質的な欠陥が
  あった**（[openwrt/odhcpd#37](https://github.com/openwrt/odhcpd/issues/37)）。
  端末がアドレスを作る瞬間（DAD）しか学習できず、ルータを再起動しても端末は
  アドレスを作り直さないため、**MAC 由来の固定アドレス（サーバ類）は再起動の
  たびに IPv6 を失う**。上流は古いキャッシュでルータへ届け続けるので聞き直しも
  来ない（膠着）。`ndp` は `disabled` にして **ndppd** へ移した（実施記録）。
  RA と DHCPv6 の relay は odhcpd のまま。
- ~~**MAP-E の fw4 連携**~~（2026-09-20 解決）。fw4 は map.sh が渡す SNAT のうち
  **tcp/udp しか nftables へ translate せず、icmp は落とす**。加えて nftables の
  NAT は範囲が埋まっても次のルールへ落ちないため、既定では最初の 16 ポートしか
  使われない。`rootfs/etc/hotplug.d/iface/90-mape-ports` が
  `{ tcp, udp, icmp }` を 15 ブロックへラウンドロビンさせて両方を解決する
  （既定で有効。実施記録）。
- **mapcalc の 64bit 既知バグ**（[openwrt#16080](https://github.com/openwrt/openwrt/issues/16080)）は
  `offset=16` の構成で出る。JPNE の `offset=4` では条件に当たらないが、
  ポート計算の結果は実機で `/tmp/map-wan.rules` を必ず読む。
- **フローオフロードは MAP-E のカプセル化に効かない。** 1Gbps 回線では問題に
  ならない見込みだが、実測で確認する（N06）。
