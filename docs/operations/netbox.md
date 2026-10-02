---
title: NetBox の使い方（台帳）
updated: 2026-09-27
section: 運用手順
audience: 管理者
tags:
  - ops
  - netbox
  - network
---

# NetBox の使い方（台帳）

> **更新日** 2026-09-27 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 稼働中（services-01）。

NetBox は **IP・VM・物理機器の台帳**です。ネット接続の有無を問わず、家にある機器をここへ集めます。次の4者が読み書きし、**人が直接編集するのは例外**です。

- **Terraform `10-platform`** が VM と IP を登録する（書き込みトークン）。
- **Ansible の動的インベントリ**がホスト一覧を引く（読み取り専用トークン）。
- **クラウドAPI** が利用者VMの IP を採番する（`managed-by-cloud-api` タグ）。
- **DHCP同期ツール**（dev-b のタイマー）が物理機器の台帳と DHCP 予約を書く（[家にある機器](#assets)）。

## 入口とログイン

| 項目 | 値 |
| --- | --- |
| URL | <https://netbox.apextox.dpdns.org/> |
| 直アクセス | `http://192.168.10.200:8000`（Terraform・Ansible・クラウドAPIが使う） |
| 管理者 | `admin` |
| パスワード | services-01 の `/opt/netbox-stack/secrets/superuser_password` |
| 稼働場所 | `services-01`（Compose。配備は `platform/ansible/netbox.yml`） |

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.200 \
  sudo cat /opt/netbox-stack/secrets/superuser_password
```

<a id="sso"></a>
## SSO（共通ログイン）

NetBox は Authentik で **SSO できます**（ログイン画面の **OpenID**）。OIDC クライアント `netbox` は identity 側の `configure.py` が作り、クライアント秘密は `platform/sops/netbox.sops.yaml` の `NETBOX_OIDC_CLIENT_SECRET` を**正本**として identity と NetBox の両方が読みます。

| Authentik のグループ | NetBox での権限 |
| --- | --- |
| `admins` | **superuser**（すべて操作できる） |
| `users` | **閲覧のみ**（`SSO users (read only)`。dcim/ipam/virtualization/tenancy/extras の view） |

- 初回ログインでユーザーを自動作成し、以後はログインのたびにグループを IdP の `groups` クレームへ合わせます。
- **ローカルの `admin` ログインは残しています**（SSO が壊れたときの非常口）。
- NetBox 標準のグループ同期（`REMOTE_AUTH_GROUP_SYNC_*`）は **HTTP ヘッダー認証でしか動かず OIDC では効きません**。`stacks/netbox/sso_pipeline.py` の pipeline で `groups` クレームから同期しています（`configuration.py` の `SOCIAL_AUTH_PIPELINE`）。
- 変更時は **`identity.yml`（クライアント作成・更新）→ `netbox.yml`（秘密の配布・再作成・権限 seed）** の順で流します。
- **SSO は `https://netbox.apextox.dpdns.org/` から使います。** リダイレクト URI はこの名前で厳密一致で登録しているため、IP 直（`http://192.168.10.200:8000`）からの SSO は `redirect_uri_no_match` で失敗します。IP 直は API・Terraform 用で、ブラウザのログインは名前を使ってください（IP 直でもローカル `admin` は使えます）。

## 主な画面

| 画面 | 何が見えるか |
| --- | --- |
| **IPAM → IP Addresses** | 管理レンジ `.201–.239` とクラウドレンジ `.100–.180`。クラウドが採番したものには `managed-by-cloud-api` タグが付く |
| **IPAM → IP Ranges** | クラウド用レンジ（API がここから配る） |
| **Virtualization → Virtual Machines** | 基盤VM（`platform` プール）。役割は `tags.yaml` のタグと Ansible グループに対応 |
| **DCIM → Sites / Devices** | サイト（K11）と物理機器。マイコン・マイク・アンマネージドスイッチなど、ネット接続の無い機器も載る（[家にある機器](#assets)） |
| **Tenancy** | 所有者（利用者） |

`https://netbox.apextox.dpdns.org/` は Caddy が TLS を終端します。**LAN の中だけ**です（[接続先一覧](../reference/urls.md)）。

## API トークン

| 用途 | 置き場 | 権限 |
| --- | --- | --- |
| Ansible 動的インベントリ（読み取り） | `platform/ansible/netbox.env`（`NETBOX_TOKEN`。`nbt_<key>.<token>` 形式） | 読み取り |
| Terraform `10-platform`（書き込み） | `platform/sops/netbox.sops.yaml`（`NETBOX_API_TOKEN`） | `dcim`/`virtualization`/`ipam`/`tenancy`/`extras` の CRUD。**superuser ではない** |

**用途ごとに別のトークンを使います。** superuser のトークンを Ansible や Terraform へ渡しません。

## 触ってよい範囲

- **台帳の正本はコード（Terraform）です。** GUI で VM・IP を直すと IaC と乖離し、次の `apply` で戻されたり、別の作業機の plan が「消す」と読みます。修正は `hosts.yaml` / `network.yaml` を直して `10-platform` を流します。
- **物理機器の正本は `platform/netbox/devices.yaml` です。** 画面で機器・型番・MAC を直すと次の `ensure` で戻ります。修正は YAML を直して `ensure`（[家にある機器](#assets)）。
- IP の予約など、GUI でしかできない例外を足したときは、**何をなぜ足したかをこの文書か コミットメッセージに残します**。
- クラウドが採番した IP（`managed-by-cloud-api`）は API が管理します。手で消しません。

## 障害時

- NetBox は services-01 の Compose です。再配備は `platform/ansible/netbox.yml`。
- **Postgres の接続が飽和することがあります**（2026-09-12 に発生。`sorry, too many clients already`）。`media-netbox-netbox-1` と worker を再起動すると解放されます。恒久対策（`max_connections` や接続プール）は未実施です。
- NetBox が落ちると、Terraform `10-platform` と Ansible のインベントリが止まります。**クラウドAPI も IP 採番に NetBox を使うため、新規VMの作成が止まります**（既存VMの操作は続きます）。

<a id="lan-の-ip-とルータの-dhcp-を同期する"></a>
## LAN の IP とルータの DHCP を同期する

**分担**: 機器帯（`.2〜.19`）の予約は NetBox が正本、実際に配ったリースは
ルータが正本。`tools/netbox-dhcp-sync.py` が両者をつなぎます。

| コマンド | 向き | 内容 |
| --- | --- | --- |
| `ensure` | devices.yaml → NetBox | 機器・インターフェース（MAC）・reserved な IP を揃える |
| `pull` | NetBox → ルータ | reserved な IP を dnsmasq の予約（`/etc/dnsmasq.d`）へ反映 |
| `push` | ルータ → NetBox | DHCP リースを `status=dhcp` の IP として写す |
| `discover` | LAN → 画面 | ARP とリースを一覧し、未宣言の機器を提案する（読むだけ） |

宣言の正本は `platform/netbox/devices.yaml`。**IP を変えるときはここを直して
`ensure` → `pull`。** NetBox の画面やルータの UCI を直接編集しません。

### どうやって台帳に載るか（登録の仕組み）

| 端末 | 載り方 |
| --- | --- |
| **DHCP でリースを取る端末** | `push`（15分ごと）が `status=dhcp` として自動で書く。名前は端末が名乗ったホスト名 |
| **devices.yaml に宣言した端末** | `ensure` が dcim（機器・MAC）と `status=reserved` の IP を作る。`pull` が dnsmasq の予約にする |
| **静的 IP を使う端末** | **自動では載らない**（リースを取らないため）。`discover` で見つけて devices.yaml に宣言する |

```bash
# LAN に居るのに台帳へ無い物を探す（読み取りのみ。候補を YAML で出す）
sops exec-env platform/sops/netbox.sops.yaml \
  'python3 tools/netbox-dhcp-sync.py discover'
```

`discover` の例（Alexa が未宣言だったとき）:

```
192.168.10.46    4c:ef:c0:58:ea:66  alexa                    未宣言  NetBox: なし
...
# devices.yaml に足す候補
  - name: alexa
    device_type: Client Device
    role: Client
    interface: {name: eth0, type: 1000base-t, mac: '4c:ef:c0:58:ea:66'}
    address: 192.168.10.46/24
    dns_name: alexa
```

- **DHCP プール内（`.20〜.99`）に静的な端末が居ても、reserved にすれば
  衝突しません。** dnsmasq は予約された IP を他の端末へ配らない（例: Alexa
  `.46`、Eufy `.98`、SwitchBot `.99`）。プールの外（機器帯 `.2〜.19`）へ
  引っ越す必要はなく、端末側の設定も変えなくてよい
- reserved の名前は `host-record` でも DNS に書くので、DHCP を取らない静的 IP の
  端末（Pi・AP など）でも `.lan` 名が引ける。プール内の予約は他端末への払い出し
  防止も兼ねる

```bash
sops exec-env platform/sops/netbox.sops.yaml \
  'python3 tools/netbox-dhcp-sync.py ensure'   # 機器・予約を揃える
sops exec-env platform/sops/netbox.sops.yaml \
  'python3 tools/netbox-dhcp-sync.py pull'     # ルータへ反映
sops exec-env platform/sops/netbox.sops.yaml \
  'python3 tools/netbox-dhcp-sync.py push'     # リースを台帳へ
```

- レンジは `platform/terraform/network.yaml` の `infrastructure` / `dhcp` が正本で、
  Terraform が NetBox の IP Range を作ります
- 固定IPを持たないが**名前だけ付けたい機器**（カメラ・家電など）は、`devices` の
  `interface` に MAC を書くだけで `dhcp-host=MAC,名前` を生成します（`clients` に
  直接書くこともできます）。動的IPのまま DNS 名が引けます
- **リースが消えた DHCP レコードは削除**します。機器が別の住所へ移ったときに
  「廃止済」が並び、機器自体が廃止されたように見えるのを避けるためです。
  ただし**ルータの再起動直後は削除しません**。リースDBは `/tmp`（tmpfs）にあり、
  再起動で空になって端末が取り直すまで「リース無し」に見えるためです。
  リースが1件も無いときと、起動からリース期間（12時間）未満のときは見送ります
  （2026-09-20、再起動後に10件消えた事故の対策。テストは
  `tests/test_netbox_dhcp_sync.py` の `DeleteGuardTests`）
- MAC は NetBox 4.x の `interface.mac_address`。Terraform Provider は読み取り専用
  なので dcim は API（このツール）で管理します
- **UCI に `config host` を手書きしない。** 生成ファイルと重複すると dnsmasq は
  「duplicate dhcp-host」で**起動に失敗**します。起動しないときは
  `ssh root@192.168.10.1 'dnsmasq --test -C /var/etc/dnsmasq.conf.*'`
- 予約した名前は `host-record`（リース不要）と `dhcp-host`（リース取得後に有効）
  の両方で書きます。静的 IP の端末も DHCP の端末も `.lan` で引けます

### 定期実行

dev-b の systemd timer が **15分ごとに `ensure → pull → push`** を流します
（`platform/ansible/netbox-dhcp-sync.yml` とロール `netbox_dhcp_sync`）。
実行ユーザーは `ruru`（SOPS の age 鍵・ルータへの SSH 鍵・リポジトリを持つ人）。

```bash
# 配備・更新
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
     .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml \
       platform/ansible/netbox-dhcp-sync.yml'
# 状態とログ
ssh debian@192.168.10.203 \
  'sudo systemctl list-timers netbox-dhcp-sync.timer; sudo journalctl -u netbox-dhcp-sync -n 20'
```

dev-b が止まっている間は同期も止まります（台帳が遅れるだけで壊れません）。

<a id="assets"></a>
## 家にある機器（資産）を台帳に載せる

**ネットに繋がっていない機器も載せられます。** Arduino のような USB のマイコン、
マイク、アンマネージドスイッチにも名前・型番・役割を付けられます。宣言の正本は
`platform/netbox/devices.yaml` で、ネット接続機器と同じ `ensure` が NetBox の
**DCIM → Devices** へ入れます。IP が無い機器は DHCP の予約には関与しません。

### 載せる物・載せない物

- **載せる**: 筐体のある機器（PC・SBC・ネットワーク機器・ストレージ・モニター・
  周辺機器・マイク・カメラ・UPS・開発ボード・測定器・工具）。型番・保証・買い替えの
  判断に使います。購入日・購入元・価格は `comments` の「購入:」に残します。
- **載せない**: ケーブル・電源タップ・充電器・USB 変換アダプタ・電池・電子部品。
  入れ替わりが早く数も多く、台帳がすぐ古くなるためです。必要になったら個別に
  `devices` へ足せます。microSD・USBメモリは容量と個体を追うため `Storage` として
  載せています。

### 実機の項目

| 項目 | 必須 | 内容 |
| --- | --- | --- |
| `name` | ✅ | 台帳での名前。`ensure` の突き合わせキーなので後から変えない |
| `device_type` | ✅ | `device_types` の `model` と一致させる |
| `role` | ✅ | `roles` の `name`。用意済みは AP・Server・Printer・Hypervisor・Client・Switch・Microcontroller・Audio・Capture・Adapter・Power・Storage・Peripheral・Tool・Camera・Appliance・Modem・Desktop・Laptop・Sensor |
| `description` | | 用途・接続方法などの覚え書き |
| `serial` | | シリアル番号。書いたときだけ同期する（書かなければ画面側の値を消さない） |
| `asset_tag` | | 管理番号。同上 |
| `comments` | | 仕様・JAN・保証・入手先などの自由記述。同上（書いたときだけ同期） |
| `purchase_date` など | | 購入日・購入元（`purchase_from`）・価格（`price_jpy`）・保証期限（`warranty_until`）。`custom_fields` に宣言した NetBox のカスタムフィールドに入り、「保証期限」で検索・並べ替えできる |
| `power_ports` | | 電源の入口（`ac` など）。UPS や PDU から受ける口 |
| `power_outlets` | | 電源の出口（UPS の `battery1`〜`battery6`・`surge1`〜`surge6` など） |
| `status` | | 既定は `active`。`planned`・`offline`・`inventory`（在庫）など NetBox の値 |
| `interface` | | 口が1つのとき。`{name, type, mac}`。**省略可**（USB のマイコン、アンマネージドスイッチなど）。`address` が無く MAC だけ書くと、その機器名で DHCP の名前だけ付く（IP は動的のまま） |
| `interfaces` | | 口が複数のとき（PC の eth0 + wlan0 など）。`interface` とは併記しない |
| `address` | | `192.168.10.x/24`。**省略可**。口が無くても書ける（MAC が無いので DHCP 予約は作られない） |
| `address_interface` | | `address` を割り当てる口の名前。省略時は最初に宣言した口 |
| `dhcp` | | `false` で dnsmasq に何も出さない（家の LAN に居ない機器など）。既定は `true` |
| `dns_name` | | 省略時は `name`。`address` があるときだけ使われる |

- 型番そのものは `device_types` の `model`、型番の補足（Arduino の `A000005` など）は
  `part_number` に書きます。`comments` は型番（`device_types`）にも書けます。長い仕様は
  そちらへ（例: ビデオキャプチャの入出力解像度、JAN、寸法、重さ）。
- `interface.type` は NetBox の値です（`1000base-t`・`ieee802.11ac` など。迷ったら `other`。
  この NetBox に USB の種別は無いので、USB のマイコンは interface を省き `description` に書きます）。
- `ensure` は足りない物を作り、`description`・`serial`・`asset_tag`・`comments`・
  `status`・型番が宣言と違えば直します。**YAML から消しても NetBox からは消えません**
  （廃棄は画面で `status` を変えるか削除。誤って消さないため）。
- **`name` を変えるときは順序に注意**。`ensure` は名前で突き合わせるため、YAML を先に
  変えると別の機器が新しく作られます。先に NetBox 側の名前を API で直すか、旧機器を
  消してから `ensure` を流します。

### 追加の手順

```bash
# 1. platform/netbox/devices.yaml を編集する（製造元 → 型番 → 実機の順に追記）
# 2. 差分を見る（書き込まない）
sops exec-env platform/sops/netbox.sops.yaml \
  'python3 tools/netbox-dhcp-sync.py ensure --dry-run'
# 3. 反映する。IP/MAC を持つ機器は pull まで流す
sops exec-env platform/sops/netbox.sops.yaml \
  'python3 tools/netbox-dhcp-sync.py ensure && python3 tools/netbox-dhcp-sync.py pull'
```

dev-b のタイマーが15分ごとに `ensure → pull → push` を回すので、コミットが dev-b の
チェックアウトへ届けば自動でも反映されます（上の定期実行）。

### 例

```yaml
manufacturers:
  - {name: Arduino, slug: arduino}

device_types:
  - manufacturer: Arduino
    model: Arduino Leonardo
    slug: arduino-leonardo
    part_number: A000057
    comments: |
      ATmega32u4 / USB Micro-B

devices:
  # ネット接続の無い機器。interface も address も省ける。
  - name: arduino-leonardo-1
    device_type: Arduino Leonardo
    role: Microcontroller
    description: Arduino Leonardo（USB。ATmega32u4）

  # IP はあるが MAC が分からない機器。dcim にだけ載り、予約は作られない。
  - name: pi-zero-2w
    device_type: Raspberry Pi Zero 2 W
    role: Server
    interface: {name: wlan0, type: ieee802.11ac}
    address: 192.168.10.15/24
```

- 型番が分からない機器は `Generic` 製造元＋仮の型番で登録し、分かったら `devices.yaml`
  を直して `ensure` を流し直します（画面で直さない）。
- 役割を増やすときは `roles` に1行足すだけです（色は `color_hex`）。

### シリアルの探し方

`serial` は書いたときだけ同期します。全部を埋める必要はなく、保証・故障・紛失の
ときに効くものから。主な探し方は次のとおりです。

| 機器 | 取り方 |
| --- | --- |
| Windows PC | `Get-CimInstance Win32_BIOS \| select SerialNumber`（または `wmic bios get serialnumber`） |
| Raspberry Pi | `cat /sys/firmware/devicetree/base/serial-number` |
| Proxmox ホスト | `dmidecode -s system-serial-number` |
| HDD / SSD / NVMe | `sudo smartctl -i /dev/sdX`（NVMe は `sudo nvme list`） |
| UPS・ルーター・家電・周辺機器 | 本体の裏・底面のラベル（製造番号 / S/N）。箱にも |
| スマホ・タブレット・Echo・SwitchBot・Eufy | 設定やアプリの「端末情報」にも出る |

- **シリアルが無い機器**: Arduino 系（Nano・Leonardo・互換）、CH340、Geekworm の
  拡張ボード、RasTech カメラ、小型モニター、microSD / USBメモリ（ロット番号のみ）。
- 記録済み: `hdd-wd10jpvt-1`（`WD-WXB1C22E3421`）・`hdd-toshiba-mk1255gsx-1`（`Z9BGPD03T`）。

### 接続図（cables）

主要なネットワーク配線と電源（UPS ↔ 機器）は `cables` に宣言すると、NetBox の
**DCIM → Cables** に接続図ができます。両端は `devices` で宣言した口です。

| 項目 | 必須 | 内容 |
| --- | --- | --- |
| `a` / `b` | ✅ | 端点。`{device: 機器名, interface: 口}` / `{device, power_port: 口}` / `{device, power_outlet: 口}` |
| `type` | | `cat6a`・`cat6`・`usb`・`hdmi`・`power` など NetBox の値 |
| `length_m` | | 長さ（メートル） |
| `description` | | 何を繋ぐか |
| `status` | | 既定は `connected`。`planned` など |
| `label` | | 省略時は `a/b - a/b`。突き合わせキーなので変えると別ケーブル扱い |

```yaml
cables:
  - a: {device: onu-1, interface: lan}
    b: {device: apextox, interface: nic0}
    type: cat6a
    description: ONU → Proxmox ホスト nic0（WAN）

  - a: {device: ups-1, power_outlet: battery1}
    b: {device: apextox, power_port: ac}
    type: power
    description: UPS1 バッテリー1 → ミニPC（K11）
```

- 両端の口が `devices` に無いと `ensure` は止まります（先に機器を宣言）。
- **全部のケーブルを載せる必要はありません。** 主要なネットワーク幹線と、UPS の
  バッテリー口につないだ機器だけで十分です（停電時に何が残るかが分かります）。

## 関連

- [IaCの所有境界](../architecture/iac.md)（誰が台帳を書くか）
- [Terraformの実行](terraform.md)
- [クラウドAPIの構築](cloud.md)
- [接続先一覧](../reference/urls.md)
