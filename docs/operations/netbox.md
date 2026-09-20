# NetBox の使い方（台帳）

更新日: 2026-09-12。状態: **稼働中（services-01）。**

NetBox は **IP と VM の台帳**です。次の3者が読み書きし、**人が直接編集するのは例外**です。

- **Terraform `10-platform`** が VM と IP を登録する（書き込みトークン）。
- **Ansible の動的インベントリ**がホスト一覧を引く（読み取り専用トークン）。
- **クラウドAPI** が利用者VMの IP を採番する（`managed-by-cloud-api` タグ）。

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
| **DCIM → Sites / Devices** | サイト（K11）とノード |
| **Tenancy** | 所有者（利用者） |

`https://netbox.apextox.dpdns.org/` は Caddy が TLS を終端します。**LAN の中だけ**です（[接続先一覧](urls.md)）。

## API トークン

| 用途 | 置き場 | 権限 |
| --- | --- | --- |
| Ansible 動的インベントリ（読み取り） | `platform/ansible/netbox.env`（`NETBOX_TOKEN`。`nbt_<key>.<token>` 形式） | 読み取り |
| Terraform `10-platform`（書き込み） | `platform/sops/netbox.sops.yaml`（`NETBOX_API_TOKEN`） | `dcim`/`virtualization`/`ipam`/`tenancy`/`extras` の CRUD。**superuser ではない** |

**用途ごとに別のトークンを使います。** superuser のトークンを Ansible や Terraform へ渡しません。

## 触ってよい範囲

- **台帳の正本はコード（Terraform）です。** GUI で VM・IP を直すと IaC と乖離し、次の `apply` で戻されたり、別の作業機の plan が「消す」と読みます。修正は `hosts.yaml` / `network.yaml` を直して `10-platform` を流します。
- IP の予約など、GUI でしかできない例外を足したときは、**何をなぜ足したかをこの文書か コミットメッセージに残します**。
- クラウドが採番した IP（`managed-by-cloud-api`）は API が管理します。手で消しません。

## 障害時

- NetBox は services-01 の Compose です。再配備は `platform/ansible/netbox.yml`。
- **Postgres の接続が飽和することがあります**（2026-09-12 に発生。`sorry, too many clients already`）。`media-netbox-netbox-1` と worker を再起動すると解放されます。恒久対策（`max_connections` や接続プール）は未実施です。
- NetBox が落ちると、Terraform `10-platform` と Ansible のインベントリが止まります。**クラウドAPI も IP 採番に NetBox を使うため、新規VMの作成が止まります**（既存VMの操作は続きます）。

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
- プール内の reserved は、その端末が DHCP を取れば名前も引けるようになる
  （静的のままなら予約と衝突防止だけ）

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
- 固定IPを持たないが**名前だけ付けたい機器**（カメラ・家電など）は `devices.yaml`
  の `clients` に書きます。`dhcp-host=MAC,名前` を生成し、動的IPのまま DNS 名が
  引けます（例: `eufycam-s4`）
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
- 予約した名前が DNS で引けるのは、その機器が実際にリースを取った後です

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

## 関連

- [IaCの所有境界](../architecture/iac.md)（誰が台帳を書くか）
- [Terraformの実行](terraform.md)
- [クラウドAPIの構築](cloud.md)
- [接続先一覧](urls.md)
