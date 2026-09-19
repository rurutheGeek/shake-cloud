# N06 ルータ自作（OpenWrt）

更新日: 2026-09-19。区分: **新規実装・事前調査完了**。状態: 調査済み、実装未着手。

## 目的・現状・配備先

家庭用ルータ Aterm WG1200HP4 の設定が GUI でしか行えず、IaC 化できない。これを K11（Proxmox ホスト `apextox`）上の **OpenWrt VM** へ置き換え、ルータ設定を Git 管理下へ移す。Aterm は AP モードへ移行し、Wi-Fi のみを担当する。

配備先は `cloud` プールではなく、**ホストの起動順に組み込む単独の VM** とする（後述の起動順序）。VLAN 分離は本作業に含めない（[N03](N03-vlan.md)）。

### 調査の結論（2026-09-19）

- **回線は DS-Lite ではなく MAP-E（v6プラス / JPNE）だった。** 以前の構成メモにあった「DS-Lite 前提」は誤りで、候補に挙げていた **VyOS は MAP-E 非対応のため採用できない**。
- **MAP-E は CGNAT ではなく、ポート開放は可能。** ただし割り当てられた 240 個の番号に限られ、**80/443 は使えない**。
- K11 には未使用の有線ポートが 1 つあり、WAN 用に転用できる。配線の追加購入は不要。

## 実測で確定した前提

すべて 2026-09-19 に実機で測定した。**個別の実値（グローバル IPv4・PSID・IPv6 プレフィックス）は本書に書かない。** 下記の手順でいつでも再取得できる。

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
| 現在の使用 | `nic1` のみ `vmbr0` に接続（`192.168.10.126/24`）。**`nic0` は未接続・未使用** |
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
  "https://192.168.10.126:8006/api2/json/nodes/apextox/syslog?start=0&limit=60000" \
  | python3 -c 'import json,sys,re; [print(e["t"]) for e in json.load(sys.stdin)["data"] if re.search(r"NIC Link is", e["t"])]' | tail -20
```

ルータ VM 化後はこのポートが家中の全トラフィックを運ぶため、**着手前にリンク速度が 1000Mbps であることを必ず確認する**。

## 変更範囲と実装

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
| DHCP 配布範囲 | `192.168.10.2` 〜 `.99` | 現行 Aterm と同一。**固定割当は使っていないため移行作業はない** |
| DNS | OpenWrt の dnsmasq が `192.168.10.1` で応答 | 現行と同じ |
| WAN | `proto map` / `maptype map-e`、`tunlink` は `wan6` | 上表の MAP-E パラメータを設定 |
| MTU | 1460、MSS clamp 1420 | 実測値 |
| IPv6 | odhcpd の **relay モード**（`ndp relay` + `ra relay`） | PD がないため /64 を LAN へ中継する |

他レンジとの衝突がないことを確認済み（`platform/terraform/network.yaml`）。

| レンジ | 用途 |
| --- | --- |
| `.2` 〜 `.99` | DHCP（OpenWrt が配る） |
| `.100` 〜 `.180` | cloud プールの利用者 VM（クラウド API が採番） |
| `.201` 〜 `.239` | 管理（Terraform / NetBox） |
| `.240` 〜 `.249` | MetalLB |
| **`.250`** | **Aterm の管理 IP（本作業で新規に確保）** |

**Aterm の管理 IP に注意。** AP モードの既定値は `192.168.10.210` で、これは管理レンジ `.201〜.239` の**内側**にあり NetBox の採番と衝突する。`.250` へ固定すること。

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

- LAN の端末が DHCP で `.2〜.99` を取得し、IPv4・IPv6 の双方で外部へ到達する。
- MAP-E の外部ポートが**割り当て範囲内に収まる**（上記 STUN 手順で確認）。IPv4 の PMTU が 1460 で、大きなパケットが通る。
- IPv6 が LAN 端末へ RA で配られ、GUA で外部へ到達する。
- `nic1` のリンクが 1000Mbps を維持し、リンク断が発生しない。8 並列で 180Mbps 前後が出る。
- Aterm が AP としてのみ動作し、**DHCP を返さない**。Wi-Fi の両 SSID で接続できる。
- Proxmox ホストと全 VM が従来どおり到達でき、`https://pve.apextox.dpdns.org:8006` と各サービスの HTTPS 名が引ける。
- ホスト再起動後、ルータ VM が自動起動してインターネットが自力で復旧する。
- **配線を戻すだけで Aterm 運用へ戻せる**ことを、切替前に手順として確認しておく。

### 未確定事項

- OpenWrt の odhcpd relay モードには「起動時に動かない」「数分でデフォルトルートが消える」といった不安定性の報告がある（[openwrt/odhcpd#37](https://github.com/openwrt/odhcpd/issues/37)）。本環境で安定するかは実機で確認する。不調なら `ndppd` を代替として検討する。
- MAP-E のカプセル化トラフィックにはフローオフロードが効かない。1Gbps 回線では問題にならない見込みだが、実測で確認する。
- ルータを K11 に載せると、**Proxmox の再起動・カーネル更新が家中のネット断になる**。復旧経路の `net-01` も同一ホスト上にあり（[net.md](../operations/net.md)）、K11 が落ちると外からも中からも到達できなくなる。K11 の外に出口を 1 つ残す設計は本作業の範囲外だが、切替前に方針を決めること。
