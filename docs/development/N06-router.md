# N06 ルータ自作（OpenWrt）

更新日: 2026-09-20。区分: **新規実装・切替済み**。状態: **router-01 が家庭内ルータとして稼働中。IPv4（MAP-E）・IPv6 とも LAN 端末から疎通する。** `verify-router.py` は 5 PASS / 0 FAIL、ホスト再起動での自動復旧も確認済み（全断 53 秒）。**完了条件はすべて満たした。** 手順と実施記録は [router-01（OpenWrt）](../operations/router.md)。

## 目的・現状・配備先

家庭用ルータ Aterm WG1200HP4 の設定が GUI でしか行えず、IaC 化できない。これを K11（Proxmox ホスト `apextox`）上の **OpenWrt VM** へ置き換え、ルータ設定を Git 管理下へ移す。Aterm は AP モードへ移行し、Wi-Fi のみを担当する。

配備先は `cloud` プールではなく、**ホストの起動順に組み込む単独の VM** とする（後述の起動順序）。VLAN 分離は本作業に含めない（[N03](N03-vlan.md)）。

### 調査の結論（2026-09-19）

- **回線は DS-Lite ではなく MAP-E（v6プラス / JPNE）だった。** 以前の構成メモにあった「DS-Lite 前提」は誤りで、候補に挙げていた **VyOS は MAP-E 非対応のため採用できない**。
- **MAP-E は CGNAT ではなく、ポート開放は可能。** ただし割り当てられた 240 個の番号に限られ、**80/443 は使えない**。
- K11 には未使用の有線ポートが 1 つあり、WAN 用に転用できる。配線の追加購入は不要。

## 実測で確定した前提

すべて 2026-09-19 に実機で測定した。**個別の実値（グローバル IPv4・PSID・IPv6 プレフィックス）は本書に書かない。** このリポジトリは GitHub で public なので、コミットすると家の住所と「開けられる 240 ポート」が永久に公開される。下記の手順でいつでも再取得でき、**手元の控えは Git 管理外の `.local/router-values.md`** に置いた。

**値は ISP が `/64` を振り直せば変わる。** 変わっても `platform/openwrt/` の設定は触らなくてよい（プレフィックスを書いていないので `mapcalc` が導出し直す）。

### 回線（MAP-E / v6プラス）

| 項目 | 値 | 備考 |
| --- | --- | --- |
| 方式 | MAP-E（v6プラス・JPNE） | enひかり Lite は公式に MAP-E 固定。固定IP・transix・Xpass へは変更できない |
| BR アドレス | `2404:9200:225:100::64` | ISP 共通値 |
| Rule IPv6 prefix | `240b:10::/31` | ISP 共通値 |
| Rule IPv4 prefix | `106.72.0.0/15` | ISP 共通値 |
| EA-bits 長 / PSID 長 / オフセット | 25 / 8 / 4 | ISP 共通値 |
| 使えるポート | **240 個**（16 ポート × 15 ブロック） | 番号は PSID から決まる。**80・443・22 は使用不可** |
| IPv4 の MTU | **1460**（MSS clamp 1420） | `ping -M do` で実測 |
| IPv6 | RA で **/64 を 1 つ**受信。DHCPv6-PD なし | ひかり電話を契約していないため |

ひかり電話なしのため、上流は単一 /64 を投げてくるだけで、プレフィックス委譲がない。現在の Aterm は **ND Proxy** でこの /64 を LAN へ中継している（LAN 側の 1 ホップ上に、同一 /64 内のアドレスが見える）。OpenWrt でも同じ中継を再現する必要がある。古河電工の公式設定例「[v6プラス設定例（MAP-E方式-3）](https://www.furukawaelectric.com/fitelnet/setting/ipoe/pdf/v6plus_mape-3.pdf)」の**パターン3（HGWなし・ひかり電話なし）**がこの構成に対応する。

#### 実値の求め方

PSID と割り当てポートは、LAN 内の任意の Linux から STUN で外部ポートを数回観測すれば判定できる。観測されたポート番号を 16 進で並べ、**中央 8 ビットが全件で一致していればそれが PSID**（一致しなければ MAP-E ではなく DS-Lite 等を疑う）。

```bash
python3 - <<'EOF'
import socket, struct, os
for _ in range(6):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(3); s.bind(('0.0.0.0', 0))
    magic = b'\x21\x12\xa4\x42'
    s.sendto(struct.pack('>HH', 0x0001, 0) + magic + os.urandom(12), ('stun.l.google.com', 19302))
    data, _ = s.recvfrom(2048)
    off, end = 20, 20 + struct.unpack('>H', data[2:4])[0]
    while off < end:
        at, al = struct.unpack('>HH', data[off:off+4])
        if at == 0x0020:
            port = struct.unpack('>H', data[off+6:off+8])[0] ^ 0x2112
            print(f'external port = {port} (0x{port:04X})')
        off += 4 + al + ((4 - al % 4) % 4)
    s.close()
EOF
```

PSID が分かれば、使えるポートは `port = (i << 12) | (psid << 4) | j`（`i` = 1〜15、`j` = 0〜15）で全 240 個が決まる。グローバル IPv4 は `curl -s4 ifconfig.co/json`、IPv6 プレフィックスは `ip -6 addr` で確認する。

### ホスト（K11 / apextox）

| 項目 | 値 |
| --- | --- |
| 有線 NIC | **Intel I226-V × 2**（`0000:02:00.0` = `nic0`、`0000:03:00.0` = `nic1`） |
| IOMMU グループ | 15 と 16 に**分離済み** → 個別に PCI パススルー可能 |
| 現在の使用 | `nic1` のみ `vmbr0` に接続（`192.168.10.10/24`）。**`nic0` は未接続・未使用** |
| 無線 | MediaTek MT7922（未使用） |
| 余力 | 16 スレッド / RAM 59.7GiB（47.0GiB 使用中） |

`/etc/network/interfaces` に **`nic2` という実体のない定義が残っている**（API の `exists` が立たない）。本作業で整理する。

GPU パススルー（game1）が動作しているため IOMMU は有効。カーネルコマンドラインは `quiet` のみで、IOMMU 用のパラメータは付いていない（AMD は既定で有効）。

### 解決済みの障害：LAN ケーブル不良（記録）

調査中に、`nic1` が **100Mbps でしかリンクせず、11 日間で 212 回のリンク断**を起こしていたことが判明した。K11 と Aterm を結ぶケーブルの不良で、交換により解消した。

| | 交換前 | 交換後 |
| --- | --- | --- |
| ネゴシエート速度 | 100 Mbps | **1000 Mbps** |
| 実効スループット（8 並列） | 92.6 Mbps | **183.1 Mbps** |

ホストの唯一の上流が 100Mbps に制限されていたため、**全 VM と LAN 内通信（Nextcloud の転送、Moonlight の映像を含む）が影響を受けていた**。回線の実効速度は 180〜200Mbps 程度で、これは Lite プランの実力とみられる。

**同種の障害はホストのログで検出できる。** SSH が通らなくても、root API トークンでカーネルログを読める。

```bash
TOKEN=$(sops -d platform/sops/proxmox-root.sops.yaml | grep -E '^PROXMOX_VE_API_TOKEN:' | sed 's/^[^:]*: *//')
curl -sk -H "Authorization: PVEAPIToken=$TOKEN" \
  "https://192.168.10.10:8006/api2/json/nodes/apextox/syslog?start=0&limit=60000" \
  | python3 -c 'import json,sys,re; [print(e["t"]) for e in json.load(sys.stdin)["data"] if re.search(r"NIC Link is", e["t"])]' | tail -20
```

ルータ VM 化後はこのポートが家中の全トラフィックを運ぶため、**着手前にリンク速度が 1000Mbps であることを必ず確認する**。

## 変更範囲と実装

### 実装と実機配備（2026-09-19）

| 成果物 | 場所 |
| --- | --- |
| UCI 設定の正本（MAP-E・LAN・DHCP・DNS・relay・MTU） | `platform/openwrt/rootfs/etc/shakecloud/config/` |
| 初回起動と更新の反映スクリプト | `platform/openwrt/rootfs/etc/shakecloud/apply` |
| Image Builder のビルド（版・チェックサム固定、`.raw` 出力） | `platform/openwrt/openwrt.yaml`・`build.sh` |
| VM 宣言（2 NIC、cloud-init なし、リンク状態を YAML で） | `platform/terraform/router.yaml`・`router/` |
| ホスト準備・ビルド・配備・切替・ロールバックの手順 | [router-01（OpenWrt）](../operations/router.md) |
| 切替後の検証（STUN・PMTU・relay・リンク速度） | `tools/verify-router.py`（切替前の基準取りにも使える） |
| 補完（ポートセット分散と icmp の SNAT。**実機で検証済み・既定で有効**） | `platform/openwrt/rootfs/etc/hotplug.d/iface/90-mape-ports` |
| 実機: `vmbr1`（nic0、IP なし）追加と `nic2` 削除 | 2026-09-19。`vmbr0`・管理 IP は無傷 |
| 実機: `router-01`（VM 101）作成、起動順を `qm set`、両 NIC リンクダウン | 2026-09-19。シリアルコンソールで設定反映を確認、再 plan は No changes |

実装中に確定した事項:

- **`wan6` には `extendprefix '1'` が要る。** mapcalc は PD を `ipv6-prefix` から
  探すが、PD が無い本構成では RA の /64 がそこに出ない。RFC 7278 の
  `extendprefix` で RA の /64 を `ipv6-prefix` として見せる（`dhcpv6.script` の
  実装を確認）。これが無いと `map` は `NO_MATCHING_PD` で止まる。
- **イメージは `.raw` にする。** Proxmox の import content は `.raw`/`.qcow2`/
  `.vmdk` のみ受け付け、Image Builder の `.img.gz` はそのままでは取り込めない。
- **構築中は両 NIC をリンクダウンにする。** LAN を `vmbr0` に繋いだまま起動すると、
  既存 Aterm と 192.168.10.1・DHCP が衝突する。「WAN を未接続のまま」だけでは
  足りないため、`router.yaml` の `wan_connected` / `lan_connected` で両方を
  落とし、切替日に Git の変更で上げる方式にした。
- **`vmbr1` の追加に `tools/site-yaml.py` の修正が必要だった。** bridge 候補が
  2つになると再生成が止まるため、「ホストのアドレスを持つ bridge」だけを
  管理 bridge として選ぶよう変えた（`tests/test_site_yaml.py`）。
- **`offset=16` の 64bit mapcalc バグ（[openwrt#16080](https://github.com/openwrt/openwrt/issues/16080)）
  は JPNE の `offset=4` では条件に当たらない。** ただし実機で
  `/tmp/map-wan.rules` のポートセットを必ず読む。
- **起動順は terraform@pve では設定できない。** Proxmox は `startup` の設定に
  `Sys.Modify` on `/` を要求する（`PVE/API2/Qemu.pm` の特別扱い）。広い権限を
  渡さず、**ホストで `qm set` を一度**実行し、Terraform 側は `ignore_changes` で
  消しに行かせない（`router.yaml` の値が正本、手順は router.md）。
- **切替はオフラインで進められる形にした。** opencode の応答はインターネット
  越しなので切替中は会話できない。WAN は切替前に有効化しておき（ケーブルが
  無い間は無害で、挿した瞬間に MAP-E が始まる）、LAN は Proxmox UI の
  「切断」を外して上げる。Terraform の apply と検証は復旧後にまとめて行う。
- **`wan` には `legacymap '1'` が要る。** JPNE の BR は OpenWrt の既定
  （RFC 7597）と 1 バイトずれた CE アドレスを期待する。切替当日に IPv4 だけが
  全滅した原因がこれだった（次節）。
- **relay の master 側にもモードが要る。** `dhcp.wan6` に `master '1'` を
  置くだけでは中継は始まらない。odhcpd はモードをインターフェースごとに
  持つので、**上流側にも `ra`/`dhcpv6` = `relay`** を書く。これが抜けて
  いて、切替後に LAN へ RA が 1 つも出なかった。
- **自分のゾーンを `rebind_domain` で除外する。** `*.apextox.dpdns.org` は
  公開レコードが LAN のアドレスを指すので、dnsmasq の `rebind_protection` が
  応答を捨てる。除外しないと**家中のサービス名が引けない**。インターネットは
  通るので気づきにくい（切替後、数時間そのままだった）。
- **近隣代理は odhcpd ではなく ndppd。** `ndp relay` は端末がアドレスを作る
  瞬間しか学習できず、**ルータ再起動後に固定アドレスの端末が IPv6 を失う**
  （後述）。`ndp` は両側 `disabled` にする。

### 切替後に IPv4 だけ通らなかった原因（2026-09-20・解決済み）

切替後、LAN・DHCP・DNS とルータ WAN 側の IPv6 は動いたのに、**IPv4 が一切
通らなかった**。原因は `wan` の `legacymap` の欠落で、1 行の追加で解決した。

切り分けの経過:

| 見たもの | 結果 |
| --- | --- |
| `map-wan` のトンネル | UP。グローバル IPv4 の `/32` が付き、既定ルートもある |
| SNAT | 正しく割当ポート（PSID の第 1 ブロック）へ書き換わっている |
| `ip -s link show map-wan` | **TX 245,034 / RX 0** |
| `/proc/net/nf_conntrack` | 全エントリ `[UNREPLIED]` |
| CE アドレス発の IPv6 → BR / 外部 | **正常に往復**（片道障害ではない） |

「出ているが一切返らない」ので、WAN 側で上流の Neighbor Solicitation を
捕まえた。

```
$ tcpdump -nti eth0 -Q in "icmp6 and ip6[40]==135"
IP6 <上流のリンクローカル> > ff02::1:ff<…>:
    ICMP6, neighbor solicitation, who has <上流が期待する CE アドレス>
```

プレフィックス部は一致していて、**インターフェース ID（下位 64 ビット）の
並びだけ**が違っていた。

```
上流が期待（draft-03）  : 00 <IPv4 4byte> <PSID> 00
OpenWrt 既定（RFC 7597）: 00 00 <IPv4 4byte> <PSID>
                             ^^ 1 バイト右へずれている
```

誰もそのアドレスを名乗らないので、BR からの戻りは上流で捨てられていた。
IPv6 は無傷なので「IPv6 だけ動いている」ように見え、切り分けを難しくする。

`map.sh` は `LEGACY="$legacymap"` を `mapcalc` に渡すだけなので、実機で確かめた。

```
$ LEGACY=1 mapcalc wan6 type=map-e,ipv6prefix=240b:10::,prefix6len=31,…
RULE_1_IPV6ADDR=<draft-03 の並びの CE アドレス>   ← NS の宛先と一致
RULE_1_IPV4ADDR=<グローバル IPv4>                 ← 変わらない
RULE_1_PORTSETS=<240 ポート>                      ← 変わらない
```

**IPv4 アドレス・PSID・ポートセットの計算はどちらの形式でも同じ**なので、
`/tmp/map-wan.rules` や `verify-router.py` のポート検証だけでは気づけない。
`option legacymap '1'` を入れて `ifup wan` した直後に RX が動き出し、
LAN から `curl -4 ifconfig.co/json` が MAP-E の割当どおりのグローバル IPv4
（逆引きは `M<10桁>.v4.enabler.ne.jp`）を返した。

**この形式差は N06 の事前調査で見落としていた項目で、ISP 共通値の表にも
載っていなかった。** 同型の構成を組むときは、BR アドレスや EA/PSID 長と
同じ並びで CE アドレス形式を確認すること。

### 1. ソフトの選定（確定）

MAP-E にネイティブ対応するのは実質 **OpenWrt** のみ。

| 候補 | MAP-E | 判定 |
| --- | --- | --- |
| **OpenWrt (x86_64)** | **対応**（`map` パッケージ） | **採用。** UCI がテキストで Git 差分が読める。Image Builder で設定入りイメージを再現ビルドできる |
| VyOS 1.4 / 1.5 | 非対応 | 選外。公式課題 [T3260](https://phabricator.vyos.net/T3260) が 2024 年に Wontfix でクローズ済み |
| OPNsense | 非対応 | 選外。[Issue #4983](https://github.com/opnsense/core/issues/4983) が not planned |
| pfSense Plus | 実験的（26.03.1〜） | 選外。有償版限定かつ実験段階 |
| MikroTik RouterOS 7 | 非対応 | 選外 |
| Debian + nftables 手組み | 可能 | 次点。追従が自己責任になる |

**既知の弱点:** OpenWrt の MAP-E は fw4/nftables との噛み合わせに未解決の課題（[openwrt#11972](https://github.com/openwrt/openwrt/issues/11972)）があり、nftables の定義を手で補う必要が出る場合がある。**補った定義もリポジトリに含める**こと。

### 2. 物理構成

```
ONU ──→ nic0 (WAN)  ┐
                     ├─ K11 / Proxmox ── OpenWrt VM ── 192.168.10.1
TL-SG605 ←── nic1 (LAN) ┘                     │
   └─ Aterm（APモード・Wi-Fi専用）────────────┘
```

- **WAN = `nic0`**（現在未使用）。**LAN = `nic1`**（現行 `vmbr0`）。
- NIC の渡し方は **bridge + virtio-net から始める**。ホストから NIC の状態が見えるため障害切り分けが容易で、1Gbps なら性能も足りる。不足したら PCI パススルーへ切り替える。I226-V は SR-IOV 非対応の可能性が高く、選択肢に含めない。
- WAN 側ブリッジには**ホストの IP を与えない**（`iface ... inet manual`）。ホストの管理 IP は LAN 側に残す。

### 3. OpenWrt の設定（Git 管理対象）

| 項目 | 値 | 根拠 |
| --- | --- | --- |
| LAN アドレス | `192.168.10.1/24` | 現行ゲートウェイを引き継ぐ。`platform/terraform/site.yaml` の `gateway` / `dns_servers` を変更せずに済む |
| DHCP 配布範囲 | `192.168.10.20` 〜 `.99` | `.2〜.19` は機器帯（AP・Pi・プリンタ・Proxmox ホスト）として外へ出す。固定は dnsmasq の MAC 予約 |
| DNS | OpenWrt の dnsmasq が `192.168.10.1` で応答 | 現行と同じ |
| WAN | `proto map` / `maptype map-e`、`tunlink` は `wan6` | 上表の MAP-E パラメータを設定 |
| MTU | 1460、MSS clamp 1420 | 実測値 |
| IPv6 | RA・DHCPv6 は odhcpd の **relay モード**、近隣代理は **ndppd** | PD がないため /64 を LAN へ中継する。`ndp relay` は再起動に耐えない（下記） |

他レンジとの衝突がないことを確認済み（`platform/terraform/network.yaml`）。

| レンジ | 用途 |
| --- | --- |
| `.2` 〜 `.19` | 機器帯（Aterm `.2`、Proxmox ホスト `.10`、Pi `.11`/`.12`。dnsmasq 予約） |
| `.20` 〜 `.99` | DHCP（OpenWrt が配る） |
| `.100` 〜 `.180` | cloud プールの利用者 VM（クラウド API が採番） |
| `.201` 〜 `.239` | 管理（Terraform / NetBox） |
| `.240` 〜 `.249` | MetalLB |
| `.250` 〜 `.254` | 予備 |

**Aterm は `.2` に予約する。** AP（BR）モードの既定は DHCP クライアントで、
放っておくと DHCP プールの住所や IP 自動補正の `.210`（NetBox の管理レンジ
`.201〜.239` の内側）を名乗りうる。MAC 予約なので Aterm 側の操作は不要。
2026-09-20 に `.2〜.19` の機器帯と `.20〜.99` の DHCP プールへ整理した。

### 4. 移行

1. **事前**: `nic1` のリンクが 1000Mbps であることを確認する（上記のログ確認）。
2. **構築**: OpenWrt VM を作り、WAN を未接続のまま UCI 設定を投入して Git へ置く。**この段階では既存ネットに一切影響しない。**
3. **起動順**: Proxmox の Start/Shutdown Order でルータ VM を最優先にする。`Startup Delay` は「そのVMの起動を待つ時間」ではなく「**次の VM を起動するまでの待ち時間**」である点に注意。
4. **切替**: ONU のケーブルを `nic0` へ挿し替え、Aterm を AP モードへ変更する。
5. **Aterm の AP 化**: **モード切替で設定が初期化される。** Wi-Fi の SSID・暗号化キーは再投入が必要（値は本書に書かない。運用メモを参照）。DHCP サーバ機能が止まることを必ず確認する（二重 DHCP の回避）。

**ロールバックは配線を戻すだけ。** Aterm は切替当日まで現在の設定のまま残し、AP 化は OpenWrt の疎通確認後に最後に行う。

## 依存と並列作業

- **開発開始:** OpenWrt VM の作成、UCI 設定の作成、MAP-E パラメータの投入、Image Builder のパイプラインは、既存ネットに触れずに単独で着手できる。
- **実機切替:** 物理配線の作業と、切替中の全断（数分）を伴う。家庭内の利用者と時間を調整する。
- **競合:** `192.168.10.1` の所有、DHCP の配布、DNS の応答は**ルータ 1 台だけが持つ**。切替中に Aterm と OpenWrt の双方が応答する状態を作らない。`platform/terraform/network.yaml` のレンジ定義と NetBox の採番を変更する場合は [N03](N03-vlan.md) と調整する。
- **[N03](N03-vlan.md) との関係:** VLAN 分離は本作業に**含めない**。N03 が止まっている理由はルータだけではなく、**TL-SG605 がアンマネージドで VLAN を設定できない**ことにもある。N03 を進めるにはマネージドスイッチの調達が前提条件になる。本作業はスイッチを買い増さずに完了できる。
- **[N01](N01-vpn.md) / [N04](N04-public-edge.md) への影響:** **80/443 が使えない**ため、公開 Web を `https://～/` の形で出すことはできない。N04 の前提として記録する。一方、割り当て済みポートを使えば **WireGuard の公開は可能**で、N01 の選択肢が広がる。Tailscale の待ち受けを割当内のポートに固定すると直接接続が成立しやすくなり、Moonlight の遅延改善が見込める。ポート 240 個は外向き通信と共有するため、開放は数個に留める。

## 検証・完了条件

- LAN の端末が DHCP で `.20〜.99` を取得し（`.2〜.19` は機器帯）、IPv4・IPv6 の双方で外部へ到達する。
- MAP-E の外部ポートが**割り当て範囲内に収まる**（上記 STUN 手順で確認）。IPv4 の PMTU が 1460 で、大きなパケットが通る。
- IPv6 が LAN 端末へ RA で配られ、GUA で外部へ到達する。
- `nic1` のリンクが 1000Mbps を維持し、リンク断が発生しない。8 並列で 180Mbps 前後が出る。
- Aterm が AP としてのみ動作し、**DHCP を返さない**。Wi-Fi の両 SSID で接続できる。
- Proxmox ホストと全 VM が従来どおり到達でき、`https://pve.apextox.dpdns.org:8006` と各サービスの HTTPS 名が引ける。
- ホスト再起動後、ルータ VM が自動起動してインターネットが自力で復旧する。
- **配線を戻すだけで Aterm 運用へ戻せる**ことを、切替前に手順として確認しておく。

### 未確定事項

- OpenWrt の odhcpd relay モードには「起動時に動かない」「数分でデフォルトルートが消える」といった不安定性の報告がある（[openwrt/odhcpd#37](https://github.com/openwrt/odhcpd/issues/37)）。**2026-09-20 に実機で再現し、`ndp` だけ `ndppd` へ移した（解決）。** RA と DHCPv6 の relay は odhcpd のままで問題ない。詳細は次節。

### `ndp relay` が再起動に耐えない（2026-09-20・解決済み）

ホスト再起動の検証中に、**再起動後に dev-b の IPv6 だけが死ぬ**ことが分かった。IPv4 は自力で復旧しており、RA も届いていて、LAN 端末は GUA と既定ルートを持っているのに外へ出られない。

切り分け:

| 見たもの | 結果 |
| --- | --- |
| LAN 端末の GUA・既定ルート | ある（RA は届いている） |
| ルータ WAN 側 (`eth0`) の受信 | **戻りパケットは届いている**（`echo reply` が見える） |
| ルータの IPv6 経路 | 他の端末の `/128` はあるが、**dev-b のぶんだけ無い** |
| 手で `/128` を足す | **即座に復旧** |

odhcpd の `ndp relay` は、**端末がアドレスを作る瞬間（DAD）を捕まえて `/128` 経路を入れる**方式だった。学習できていた端末はいずれもランダムな一時アドレスで、定期的に作り直されるから拾えていただけ。**MAC 由来の固定アドレス（サーバ類）は、ルータを再起動しても端末側はアドレスを作り直さないため、二度と学習の機会が来ない。** 上流は古いキャッシュでルータへ届け続けるので近隣要請も飛んでこない（膠着。100 秒待っても NS は 1 つも来なかった）。odhcpd を再起動しても学習し直さない。

**つまり、ルータを再起動するたびに固定アドレスの端末が IPv6 を失う。** 家の中で最も IPv6 を必要とするのがサーバ類なので、受け入れられない。

対処は N06 が最初から代替に挙げていた **ndppd**。学習せず、近隣要請が来るたびに LAN へ転送して、端末が応えたときだけ代理応答する。再起動とは無関係に成立する。

- `openwrt.yaml` に `ndppd` を追加
- `rootfs/etc/ndppd.conf`（`proxy eth0` → `rule 2000::/3 { iface br-lan }`）
- `rootfs/etc/hotplug.d/iface/91-lan-prefix-route`（委譲された /64 を `br-lan` へ。ndppd 0.2.5 に `autowire` が無いため転送用の経路は別途要る）
- `rootfs/etc/uci-defaults/98-shakecloud-ndppd`（初回起動で有効化）
- `config/dhcp` の `ndp` を `lan`・`wan6` とも `disabled`

**プレフィックスはどちらのファイルにも書かない。** ndppd の rule はグローバル空間 `2000::/3` を対象にし、`iface` 指定なので LAN の端末が実際に応えたときしか代理応答しない。経路のほうは実行時に `ubus` から委譲 /64 を読む。

学習で入っていた `/128` 経路をすべて削除した状態で LAN 端末の IPv6 が通ることを確認済み。
- MAP-E の fw4 連携は、**fw4 が proto データの `firewall` 配列（map.sh の SNAT ルール）を読むことをソースで確認済み**。ただし実機では 2 つ足りなかった（2026-09-20 に確認・解決）。**(1) fw4 は tcp/udp しか nftables へ translate せず、icmp の SNAT は落とす**（[openwrt#11972](https://github.com/openwrt/openwrt/issues/11972)）。素の masquerade に落ちて割当外の ICMP id で出るため、インターネットへの ping が通らず `ping -M do` による PMTU 実測もできない。**(2) nftables の NAT は範囲が埋まっても次のルールへ落ちない**ため、既定では最初の 16 ポートしか使われず枯渇しうる。補完スクリプト `rootfs/etc/hotplug.d/iface/90-mape-ports` が `{ tcp, udp, icmp }` を 15 ブロックへラウンドロビンさせて両方を解決する。**イメージへ焼いて既定で有効**（投入直後の 226 接続が 15/15 ブロックへ分散、割当外なし。PMTU 1432 = MTU 1460 を実測）。
- MAP-E のカプセル化トラフィックにはフローオフロードが効かない。1Gbps 回線では問題にならない見込みだが、実測で確認する。
- **決定（2026-09-19）: 受容＋コールドスペア。** K11 の計画メンテ（Proxmox・
  カーネル更新、再起動）は家に人がいるときに実施し、切替後に一度 K11 を
  再起動してルータ VM が自動復旧することを試験する。K11 が直らない故障のときは
  ONU を Aterm へ戻してルータモードで起動する（設定は保存済み）。**外出中の
  遠隔復旧は行わない**（`net-01` も K11 上なので当てにしない）。専用ルータ機
  （K11 の外）や 4G の細い出口は、痛みが大きければ別作業として検討する
  （手順は [router.md](../operations/router.md)）。
  **追記（2026-09-20）:** game1 の iGPU パススルー操作（開始/停止）の直後に
  K11 がハングする事象が複数回発生（01:28・01:31・01:34・01:40・14:57）。
  リソース（メモリ・ディスク・温度・I/O）は実測でシロ。ハードウェア watchdog
  （SP5100 TCO）を適用し、**ハング後 約10秒で自動リセット → ルータ VM が
  自動起動（全断 1〜2分）**とした。詳細は
  [power.md](../operations/power.md)。
