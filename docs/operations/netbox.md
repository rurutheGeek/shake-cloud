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

## 関連

- [IaCの所有境界](../architecture/iac.md)（誰が台帳を書くか）
- [Terraformの実行](terraform.md)
- [クラウドAPIの構築](cloud.md)
- [接続先一覧](urls.md)
