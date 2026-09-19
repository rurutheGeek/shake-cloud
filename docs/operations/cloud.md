---
title: クラウドAPIの構築
updated: 2026-09-13
section: 運用手順
audience: 管理者
tags:
  - ops
  - cloud
---

# クラウドAPIの構築

> **更新日** 2026-09-13 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: Proxmox・NetBox 側の土台は実機へ適用・検証済み。API の Phase 1（ログイン・アクセスキー・監査ログ）を cloud-01 へ配備・確認済み（3-8）。LAN の中の HTTPS も構築・確認済み（3-9）。Phase 2（API から VM が作れる）も実機で確認済み（3-10）。上限の変更と容量の表示（3-11）も入った。Phase 3（イメージのアップロード・SSH鍵・Webコンソール）は実機で確認済み（3-12・3-13）。Phase 4（ボリュームとセキュリティグループ、データセンターFW有効化）も実機で確認済み（3-14）。Phase 5（既存VMの引き取り、ポータルの仕上げ、ブートストラップ管理キーの無効化）も完了（3-15）。Phase 6（CLI・Terraform Provider）も完了。Phase 7（Garage と、バケット・S3キーの API）も実機で確認済み（3-16）。database（3-20）・function（3-21）も実機で確認済み

設計は[最小クラウドとProvider](../architecture/cloud.md)、所有境界は[IaCの所有境界](../architecture/iac.md)を参照してください。ここでは**実際に手を動かす順番**と、**コードにできない作業とその理由**を書きます。


この手順は4ページに分かれています。上から順に実行します。

| ページ | 範囲 |
| --- | --- |
| [土台](cloud.md) | 実機の読み取り、Terraformの適用、SOPS、FW、NetBox、共通ログイン（3-1〜3-7） |
| [API本体とインスタンス](cloud-api.md) | クラウドAPI、名前とHTTPS、インスタンス、容量と上限、イメージとSSH鍵、Webコンソール（3-8〜3-13） |
| [ボリューム・S3・DB・関数](cloud-resources.md) | 追加ディスク、既存VMの引き取り、バケット、招待、DBバックアップ、database、function（3-14〜3-21） |
| [実機プローブと切り戻し](cloud-verify.md) | 実機での検査、元に戻す方法、CI/CDへの委譲 |
## 1. 何ができるか

**API から VM が作れます**（3-10）。土台は次のとおりです。

| あるもの | 実体 |
| --- | --- |
| 実行アカウント `cloudapi@pve` とAPIトークン | `platform/terraform/00-bootstrap/identities.tf`（**適用済み**、資格情報は `platform/sops/cloudapi.sops.yaml`） |
| ロール4種（Operator / Storage / Images / NodeAudit） | `platform/terraform/00-bootstrap/roles.tf` |
| クラウド用のIP採番元（NetBox IP Range） | `platform/terraform/10-platform/ledger.tf` |
| NetBoxの書き込みアイデンティティ `cloudapi` | `stacks/netbox/seed_cloudapi_identity.py`（**作成済み・権限を実測済み**、トークンは `platform/sops/cloudapi.sops.yaml`） |
| `identity`(VMID 110, 192.168.10.204) と `cloud-01`(VMID 140, 192.168.10.205) | `platform/terraform/hosts.yaml`（**作成・起動済み**、guest agent 導入済み） |
| 共通ログイン Authentik（新規構築）と `cloud` OIDC クライアント | `stacks/identity/`、`platform/ansible/identity.yml`（**構築済み**、3-7） |
| クラウドAPI の Phase 1（Authentik ログイン、アクセスキー、監査ログ、ブートストラップ管理キー） | `cloud/`、`platform/ansible/cloud.yml`（3-8） |
| クラウドAPI の Phase 2（VM の作成・電源操作・削除、IP 採番、seed ISO、クォータ、差分リコンサイラ） | `cloud/api/internal/compute/`（3-10） |
| 上限の変更（管理者）と容量の表示 | `GET /v1/capacity`、`GET`/`PUT /v1/limits`、ポータルの「容量」「上限」（3-11） |
| Phase 3（イメージアップロード、SSH鍵、Webコンソール） | `cloud/api/internal/compute/images.go`、keypairs、console、noVNC（3-12・3-13） |
| Phase 4（追加ボリューム、セキュリティグループ、データセンターFW有効化） | `cloud/api/internal/compute/{volumes,securitygroups,firewall}.go`、`platform/terraform/00-bootstrap/firewall.tf`（3-14） |
| Phase 5（既存VMの引き取り） | `POST /v1/instances/adopt`、`cloud/api/internal/compute/adopt.go`、DBマイグレーション `0007`（3-15） |
| Phase 6（CLI と Terraform Provider） | `cloud/client`（型付きクライアント）、`cloud/cli`（`shakecloud`）、`cloud/provider`（`shakecloud_*`）。CLI は標準ライブラリのみ（[CLI](cli.md)・[Provider](terraform-provider.md)） |
| Phase 7（Garage と バケット・S3キー API） | `platform/ansible/roles/garage`（[Garage](garage.md)）、`cloud/api/internal/garage/`（管理APIクライアント）、`cloud/api/internal/compute/buckets.go`、DBマイグレーション `0008`（3-16） |

**まだ無いもの**: VLAN分離の実機切替（宣言・安全装置・手順は用意済み）。

## 1-2. 実機の現状（2026-09-10 に API から実測）

`site.yaml` は推測ではなくこの実測から生成しています。**文書の想定と食い違う点が3つ**あります。

この表は `site.yaml` を作った時点の記録です。**いまの空き容量はポータルの「容量」か `GET /v1/capacity` で見てください**（3-11）。稼働VMが増えたので、空きRAMはこの値より減っています。

| 項目 | 実測値 |
| --- | --- |
| ノード / 版 | `apextox` / PVE 9.2.2 / Ryzen 9 8945HS 16スレッド |
| RAM | 総 59.7GiB、使用 22.6GiB、**空き 37.1GiB** |
| `local-lvm`（VMディスク） | 総 794.3GiB、空き **728.9GiB** |
| `local`（ISO・イメージ・バックアップ、ルートFS上） | 総 93.9GiB、空き **76.2GiB** |
| bridge | `vmbr0`（ports=nic1、**vlan_aware=0**） |
| SDNゾーン | 未定義 → 暗黙の `localnetwork` |
| データセンターFW | 無効（既定のまま） |

### 食い違い1: `00-bootstrap` は既に適用済み

ロール（`TerraformAdmin` / `TerraformStorage` / `TerraformNetwork` / `DevVMOperator` / `CloudApiOperator`）と `terraform@pve` のACLが実機に存在します。複数の文書にある「実機への適用は未実施」は**古い記述**です。

`cloudapi@pve` はこの実測の時点では未作成で、`CloudApiOperator` も未割り当てでした。**その後 3-3・3-4 で作成・トークン投入済みで、`CloudApiOperator` も適用済みです**（[実機プローブ](cloud-verify.md)が 6/6 PASS、[3-14](cloud-resources.md) で実測）。

### 食い違い2: 開発VMのメモリ（解決済み。I01 の軽量化で6GiBへ）

2026-09-10 時点では、`dev-a` / `dev-b` は実機が 8192 MiB（balloon 1024）で、`hosts.yaml` の宣言は `small` = 2048 MiB でした。**手で広げたものが正**として台帳を実機へ合わせました。その後 2026-09-12 の I01（資源の実測と軽量化）で、実機・宣言とも **6144 MiB（下限 2048）** になっています。

```yaml
  dev-a:
    flavor: small
    memory_mib: 6144        # I01（2026-09-12）の実測に合わせる。flavor の既定を上書き
    memory_min_mib: 2048
```

`flavor` はサイズの既定で、`hosts.yaml` が台ごとに上書きできます。手で広げた基盤VMを台帳が縮めに行かないための逃げ道で、利用者向けの語彙（flavor）は歪めません。I01 の実測は[配分と運用設計](../architecture/operations.md#measured-budget)にあります。

あわせて**メモリはバルーニングを既定**にしました（`flavors.yaml` の各サイズに `memory_min_mib` を追加）。`probe-01` は balloon が 0 なので、次の apply で下限 512 が付く差分が出ます。無害ですが差分としては出ます。

`services-01` は `05-seed` の管轄で、DBを載せるため固定割り当てのままにしています（[配備台帳](../architecture/operations.md)の方針どおり）。

### 食い違い3: VMID 100 の `game1`（2026-09-11 に引き取り済み）

`platform/terraform/pools.yaml` の `reserved_vmids` に記録しました。`hosts.yaml` が同じVMIDを使おうとすると**テストが落ちます**。VMID 100 は引き取り後もここで確保したままにします。

2026-09-11 に **VMを作り直さず**、`cloud` プールへ移してクラウドAPIの管理下へ入れ、`shunyazhiyuan97` のインスタンスとして引き取りました。ACLは `/pool/cloud` に付いていてVMIDには付いていないので、プールへ入れるだけで `cloudapi@pve` の到達範囲に入ります。詳細は[最小クラウドとProvider](../architecture/cloud.md)の「既にあるVMをクラウド管理下へ移す」と、この文書の 3-15。

**`public-edge` は VMID 100 を使いません。** 配備台帳のとおり、公開要件が揃ったら API の通常採番（5000–5999）で新規cloud VMとして追加します（[配備台帳](handover.md)の「未決事項と後回しにしたこと」）。

### イメージ置き場の容量に注意

`cloud-images` は `/srv/cloud-images`、つまり**ルートファイルシステム（残り 76.2GiB）**に載ります。`local` のバックアップ・ISO・テンプレートと同じ領域を分け合います。VMディスクが載る `local-lvm`（728.9GiB）とは別枠です。

利用者がアップロードするイメージはここへ入るので、**API側のクォータで抑えないとバックアップ領域を食い潰します**。seed ISO 自体は1台あたり数MBなので問題になりません。

## 2. コードにできない作業

リポジトリ `README.md` の「開発方針・引き継ぎ」にある**手作業の最小化**に従い、コードにできるものはすべてコードにしています。残るのは次の4つで、それぞれ構造的な理由があります。

| # | 作業 | コードにできない理由 |
| --- | --- | --- |
| 1 | 実機の読み取りを1回走らせる | ノード名・ストレージ名・bridge名は実機にしか無い。**値の転記はもう要らない**（3-1）。走らせる操作だけが残る |
| 2 | `tools/tf 00-bootstrap apply` | **`00-bootstrap` はロール・ユーザー・ACLを作る。それができるアカウントは自分に何でも付与できる**ので、実質 root と同じ。誰がどこで持つかは委譲の設計そのもの（[実行の委譲](cloud-verify.md)）。**2026-09-10 に適用済み**（12 added / 1 changed / 0 destroyed、再実行で差分なし） |
| 3 | [実機プローブ](cloud-verify.md) | 「この版のProxmoxでこのAPIが通るか」は実機に聞くしかない。**判定は自動**で、人が読むのは結果だけ。**2026-09-11 に6つとも PASS** |
| 4 | データセンターFWの有効化とVLAN工事 | 前者は**失敗するとホストから締め出される**。後者は物理機器 |

**以前ここにあった3つは自動化しました。**

- `pvesm add` によるストレージ作成 → `platform/terraform/00-bootstrap/storage.tf` の `proxmox_storage_directory`（`create_base_path = true` なのでディレクトリ作成込み）
- `tfvars` への値の注入 → `platform/terraform/site.yaml` に集約し、ACLのパスは資源とノード名から**導出**
- 実機プローブの curl を人が読む作業 → `tools/verify-cloud.py` が機械判定

## 3. 手順

### 3-1. 実機の読み取りと site.yaml の生成

```bash
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/survey-pve.yml
```

`.survey/<ホスト名>.md`（人が読む）と `.survey/<ホスト名>.facts.json`（機械が読む）ができます。どちらも LAN 構成を含むので Git へ入れません。

```bash
python3 tools/site-yaml.py .survey/<ホスト名>.facts.json
```

`platform/terraform/site.yaml` が**実測から生成されます**。値を書き写す作業はありません。site.yaml は秘密値を含まないのでコミットします。

候補が1つに絞れないときは、**推測せずに候補名を出して止まります**。

```
Cannot decide from the survey: 2 candidates for storage.vm_disks: fast-nvme, local-lvm.
Pick the one that should hold user VM disks and set it by hand.
```

そのときだけ site.yaml を手で直してください。「どちらでもよい」ではなく「どちらに置きたいか」は人にしか決められません。

生成前の site.yaml には `UNMEASURED` が入っています。**これは推測値ではなく「まだ実機に聞いていない」という印**です。残したまま plan すると、どの値が足りないかを名前で言って止まります。

### 3-2. tfvars は要りません

`00-bootstrap` も `10-platform` も `terraform.tfvars` なしで動きます。以前あった値は性質ごとに正本へ移しました。

| もとの変数 | いまの正本 | 性質 |
| --- | --- | --- |
| `proxmox_node_name` / `vm_datastore_id` / `network_bridge` | `site.yaml` | 実測 |
| `management_prefix` / `gateway` / `dns_servers` | `site.yaml` | 実測 |
| `management_range_*` / `cloud_*` | `network.yaml` | 決めごと |
| `admin_ssh_public_keys` / `host_ssh_public_keys` / `seed_ssh_public_keys` | `access.yaml` | 決めごと |
| `cloud_images` / `image_file_id` | `images.yaml` | 決めごと |

残る変数はすべて既定値を持ちます。上書きしたいときだけ tfvars を作ってください。

`network.yaml` の範囲は**実測できない決めごと**なので、生成されません。管理用とクラウド用が重ならないこと、どちらも実測した prefix の中に収まることをテストが検査します。

### 3-3. 適用する

```bash
tools/tf 00-bootstrap plan
```

差分を読んでから apply します。既存の18リソースが壊れないこと、`CloudApiOperator` の権限が**置き換わる**こと（`TerraformAdmin` との共用をやめたため）を確認してください。

```bash
tools/tf 00-bootstrap apply
```

適用後、2回目の plan が `No changes` になることを確認します。

### 3-4. トークンをSOPSへ入れる

```bash
tools/tf 00-bootstrap output -raw cloudapi_token_value
```

出力は `user@realm!id=uuid` の**完全な形**です。接頭辞を足さないでください。値を `platform/sops/cloudapi.sops.yaml` へ入れます。**表示は一度だけにします。**

```bash
sops platform/sops/cloudapi.sops.yaml
```

この値は Terraform の state にも平文で入ります。扱いは[Terraformの実行手順](terraform.md)に従ってください。

### 3-5. データセンターFWの有効化（`firewall.tf` が安全に自動化。適用済み）

VM単位のファイアウォール（＝セキュリティグループ）は、データセンター階層のFWが有効でないと効きません。単一ノードの本番機でこれを有効にすると、順序を間違えるとホストから締め出される危険があります。

そこで**手作業ではなく `platform/terraform/00-bootstrap/firewall.tf` が自動化**しています。`00-bootstrap` の apply に含まれ、2026-09-11 に適用済みです（再 plan は No changes）。安全の根拠は:

1. **ノードFWは無効のまま**（`proxmox_node_firewall.node` の `enabled=false`）。ホスト自身への通信は今までどおり素通しになり、`8006` や SSH を失いません。
2. **DC FW の既定ポリシーは ACCEPT**。あとで誰かがノードFWを有効にしても、いきなり全部は落ちません。
3. **ノードFW→DC FW の順で適用**（`depends_on`）。逆順だと一瞬だけ既定設定で動く隙ができます。
4. **`nf_conntrack_allow_invalid=1`** を入れ、有効化でゲストの RST が INVALID 扱いで落ちて「拒否」が「無応答（タイムアウト）」に化けるのを防ぎます。プロバイダに項目が無いので `scripts/node-firewall-options.py` が API を直接叩き、値を読み戻して確認します。

絞られるのは `firewall=1` のNICとVM側 `enable=1` が揃ったVMだけです。DC FW を有効にした時点（2026-09-11）では、基底VM（identity・cloud-01・services-01・dev-*）は NIC `firewall=0`、game1 は `firewall=1` でも VM `enable` が無いので影響しませんでした。**その後 game1 は引き取り（[3-15](cloud-resources.md#3-15)）で既定SG（全許可）が付き、VM FW が `enable=1` になっています**（all-allow なので透過）。適用後の既存VMへの影響と `nf_conntrack_allow_invalid` の値は、[実機プローブ](cloud-verify.md)の `vm_firewall` と [3-14](cloud-resources.md#3-14) の確認で見えます。

**もし将来 DC FW の設定そのものを手で触る必要が出たら**、物理コンソールか IPMI を用意し、管理端末からの到達を許可するルールを先に入れてから変えてください。通常は `firewall.tf` を編集して `tools/tf 00-bootstrap apply` すれば十分です。

### 3-6. NetBox 側

`10-platform` の apply でIP Rangeができます。書き込みアイデンティティは Ansible が作ります。

```bash
.venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/netbox.yml
```

`CHANGED: registered cloud API write identity` が出れば作成、`OK:` なら既にあります。トークンは NetBox ホストの `secrets/cloudapi-token.json` にでき、`nbt_<key>.<token>` の形で組み立てて使います。

このアイデンティティは Terraform 用より**狭く**、`virtualization` と `ipam` にしか書けません。`dcim` と `extras` は参照のみです。利用者向けAPIの不具合が基盤の機器台帳を書き換えないようにするためです。

2026-09-10 に作成し、トークンの権限を実測しました。書き込み可否は**空の本文でPOST**して判定しています。許可されていれば検証で 400、拒否なら 403 が返るので、何も作らずに確かめられます。

| 操作 | 結果 | 期待どおりか |
| --- | --- | --- |
| ipam / virtualization / dcim の読み取り | 200 | ✅ |
| ipam（IPアドレス）への書き込み | 400（権限は通過） | ✅ |
| virtualization（VM）への書き込み | 400（権限は通過） | ✅ |
| dcim（サイト）への書き込み | **403** | ✅ |
| tenancy（テナント）への書き込み | **403** | ✅ |

NetBox は 2026-09-10 から **LAN に公開**しています（`http://192.168.10.200:8000`）。クラウドAPI（cloud-01）や将来の AWX がトンネル無しで台帳へ届くようにするためです。公開範囲は `platform/ansible/roles/netbox/defaults/main.yml` の `netbox_bind_address` で決まり、`netbox.yml` を流すと既存ホストの `.env` もその値へ揃います。`platform/sops/netbox.sops.yaml` と `cloudapi.sops.yaml` の `NETBOX_SERVER_URL` もこのアドレスです。

通信は HTTP の平文で、トークンもそのまま LAN を流れます。LAN 内の機器を信頼する前提です。VLAN 分離（管理面と利用者VMを分ける工事）が済むまでは、利用者VMからも届く点に注意してください。書き込みトークンの権限を狭く切ってあるのはこのためでもあります。

### 3-7. 共通ログイン（Authentik）

identity VM の Authentik が共通ログインを担います。**2026-09-12 に配備した media-01 の各入口（Nextcloud・Kavita・FreshRSS・Navidrome・MeTube）は、この Authentik の OIDC / Forward Auth を使います。**

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/identity.yml'
```

秘密値（DBパスワード、secret key、`akadmin` の初期パスワード、API用ブートストラップトークン、OIDC クライアントの秘密値）は**すべて identity VM 上で自動生成**され、`/opt/identity-stack/secrets/` に置かれます。再実行しても作り直しません。

2回目以降の実行はすべて `OK:` になります（2026-09-10 に確認）。`configure.py` が作るもの:

| 対象 | 内容 |
| --- | --- |
| グループ | `users`、`admins`（`akadmin` は `admins`） |
| OIDC クライアント `cloud` | redirect は `https://cloud.apextox.dpdns.org/auth/callback` の完全一致。`sub` は `user_uuid` |
| 利用許可 | 上の2グループだけ。メディア用に招待された人はポータルに入れない |

`sub` を `user_uuid` にしたのは、既定の `hashed_user_id` だとプロバイダを作り直したときに**全員の `sub` が変わり**、クラウドAPI側の持ち主が分からなくなるためです。

入口は現在 **`https://auth.apextox.dpdns.org`**（Caddy が Let's Encrypt で TLS 終端。Authentik 自身の `:9000`・`:9443` は 127.0.0.1 に閉じた）です。**パスキーとパスワードレスも有効**です（[認証基盤](identity.md#パスキーだけでログインするパスワードレス)）。

インベントリ上のグループ名は `identity_provider` です。ホスト名 `identity` と同じ名前にすると、Ansible が「グループを自分自身へ足す」例外でインベントリ全体を読めなくなります（`tests/test_identity_stack.py` が検査）。
