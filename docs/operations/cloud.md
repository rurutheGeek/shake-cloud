# クラウドAPIの構築

更新日: 2026-09-11。状態: **Proxmox・NetBox 側の土台は実機へ適用・検証済み。API の Phase 1（ログイン・アクセスキー・監査ログ）を cloud-01 へ配備・確認済み（3-8）。LAN の中の HTTPS も構築・確認済み（3-9）。Phase 2（API から VM が作れる）も実機で確認済み（3-10）。上限の変更と容量の表示（3-11）も入った。Phase 3（イメージのアップロード・SSH鍵・Webコンソール）は実機で確認済み（3-12・3-13）。Phase 4（ボリュームとセキュリティグループ、データセンターFW有効化）も実機で確認済み（3-14）。Phase 5（既存VMの引き取り、ポータルの仕上げ、ブートストラップ管理キーの無効化）も完了（3-15）**。

設計は[最小クラウドとProvider](../architecture/cloud.md)、所有境界は[IaCの所有境界](../architecture/iac.md)を参照してください。ここでは**実際に手を動かす順番**と、**コードにできない作業とその理由**を書きます。

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

**まだ無いもの**: CLI、Terraform Provider、VLAN分離、利用者アカウント（招待の仕組み）。

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

`cloudapi@pve` は未作成で、`CloudApiOperator` は**未割り当て**のまま、権限も `TerraformAdmin` と同一の古い定義です。次の apply でここが置き換わります。

### 食い違い2: 開発VMのメモリ（解決済み・台帳を実機へ合わせた）

`dev-a` / `dev-b` は実機が 8192 MiB（balloon 1024）で、`hosts.yaml` の宣言は `small` = 2048 MiB でした。**手で広げたものが正**なので、台帳を実機へ合わせました。

```yaml
  dev-a:
    flavor: small
    memory_mib: 8192        # flavor の既定を上書き
    memory_min_mib: 1024
```

`flavor` はサイズの既定で、`hosts.yaml` が台ごとに上書きできます。手で広げた基盤VMを台帳が縮めに行かないための逃げ道で、利用者向けの語彙（flavor）は歪めません。

あわせて**メモリはバルーニングを既定**にしました（`flavors.yaml` の各サイズに `memory_min_mib` を追加）。`probe-01` は balloon が 0 なので、次の apply で下限 512 が付く差分が出ます。無害ですが差分としては出ます。

`services-01` は `05-seed` の管轄で、DBを載せるため固定割り当てのままにしています（[配備台帳](../architecture/operations.md)の方針どおり）。

### 食い違い3: VMID 100 の `game1`（2026-09-11 に引き取り済み）

`platform/terraform/pools.yaml` の `reserved_vmids` に記録しました。`hosts.yaml` が同じVMIDを使おうとすると**テストが落ちます**。VMID 100 は引き取り後もここで確保したままにします。

2026-09-11 に **VMを作り直さず**、`cloud` プールへ移してクラウドAPIの管理下へ入れ、`shunyazhiyuan97` のインスタンスとして引き取りました。ACLは `/pool/cloud` に付いていてVMIDには付いていないので、プールへ入れるだけで `cloudapi@pve` の到達範囲に入ります。詳細は[最小クラウドとProvider](../architecture/cloud.md)の「既にあるVMをクラウド管理下へ移す」と、この文書の 3-15。

**配備台帳は VMID 100 を `public-edge` と計画しているので、そちらへ別のVMIDを割り当ててください。**

### イメージ置き場の容量に注意

`cloud-images` は `/srv/cloud-images`、つまり**ルートファイルシステム（残り 76.2GiB）**に載ります。`local` のバックアップ・ISO・テンプレートと同じ領域を分け合います。VMディスクが載る `local-lvm`（728.9GiB）とは別枠です。

利用者がアップロードするイメージはここへ入るので、**API側のクォータで抑えないとバックアップ領域を食い潰します**。seed ISO 自体は1台あたり数MBなので問題になりません。

## 2. コードにできない作業

リポジトリ `README.md` の「開発方針・引き継ぎ」にある**手作業の最小化**に従い、コードにできるものはすべてコードにしています。残るのは次の4つで、それぞれ構造的な理由があります。

| # | 作業 | コードにできない理由 |
| --- | --- | --- |
| 1 | 実機の読み取りを1回走らせる | ノード名・ストレージ名・bridge名は実機にしか無い。**値の転記はもう要らない**（§3-1）。走らせる操作だけが残る |
| 2 | `tools/tf 00-bootstrap apply` | **`00-bootstrap` はロール・ユーザー・ACLを作る。それができるアカウントは自分に何でも付与できる**ので、実質 root と同じ。誰がどこで持つかは委譲の設計そのもの（§6）。**2026-09-10 に適用済み**（12 added / 1 changed / 0 destroyed、再実行で差分なし） |
| 3 | 実機プローブ（§4） | 「この版のProxmoxでこのAPIが通るか」は実機に聞くしかない。**判定は自動**で、人が読むのは結果だけ。**2026-09-11 に6つとも PASS** |
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
| `admin_ssh_public_keys` / `host_ssh_public_keys` | `access.yaml` | 決めごと |
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

絞られるのは `firewall=1` のNICとVM側 `enable=1` が揃ったVMだけです。DC FW を有効にした時点（2026-09-11）では、基底VM（identity・cloud-01・services-01・dev-*）は NIC `firewall=0`、game1 は `firewall=1` でも VM `enable` が無いので影響しませんでした。**その後 game1 は引き取り（3-15）で既定SG（全許可）が付き、VM FW が `enable=1` になっています**（all-allow なので透過）。適用後の既存VMへの影響と `nf_conntrack_allow_invalid` の値は、§4 の `vm_firewall` プローブと 3-14 の確認で見えます。

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

identity VM に Authentik を**新しく**建てました。作業機上の `stacks/hub` は検証用なので移行していません。メディア系サービスは今もそちらを使います。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  '.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/identity.yml'
```

秘密値（DBパスワード、secret key、`akadmin` の初期パスワード、API用ブートストラップトークン、OIDC クライアントの秘密値）は**すべて identity VM 上で自動生成**され、`/opt/identity-stack/secrets/` に置かれます。再実行しても作り直しません。

2回目以降の実行はすべて `OK:` になります（2026-09-10 に確認）。`configure.py` が作るもの:

| 対象 | 内容 |
| --- | --- |
| グループ | `cloud-users`、`cloud-admins`（`akadmin` は `cloud-admins`） |
| OIDC クライアント `cloud` | redirect は `http://192.168.10.205:8080/auth/callback` の完全一致。`sub` は `user_uuid` |
| 利用許可 | 上の2グループだけ。メディア用に招待された人はポータルに入れない |

`sub` を `user_uuid` にしたのは、既定の `hashed_user_id` だとプロバイダを作り直したときに**全員の `sub` が変わり**、クラウドAPI側の持ち主が分からなくなるためです。

入口は `http://192.168.10.204:9000`（HTTP）と `https://192.168.10.204:9443`（Authentik 自身の自己署名証明書）です。所有ドメインが決まったら固定名と正規の証明書へ移します。パスキーは固定の HTTPS 名が要るので、それまで使えません。

インベントリ上のグループ名は `identity_provider` です。ホスト名 `identity` と同じ名前にすると、Ansible が「グループを自分自身へ足す」例外でインベントリ全体を読めなくなります（`tests/test_identity_stack.py` が検査）。

### 3-8. クラウドAPI（Phase 1）

cloud-01 に API と管理DB（PostgreSQL）を置きます。OIDC クライアントの秘密値を identity VM から読むので、`identity.yml` の後に流します。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/cloud.yml'
```

API のイメージは cloud-01 の上で `cloud/api/` からビルドします。ベースイメージは `cloud/api/Dockerfile`、PostgreSQL は `cloud/compose.lock.yaml` で digest を固定しています。

| 入口 | 中身 |
| --- | --- |
| `https://cloud.apextox.dpdns.org/` | Phase 1 の最小ページ。Authentik でログインし、アクセスキーの発行・削除と操作履歴の閲覧ができる。Phase 5 でセルフサービスポータルに置き換える |
| `https://cloud.apextox.dpdns.org/v1/…` | JSON API。正本は `cloud/openapi/shakecloud.yaml`。Go のルート表と食い違うとテストが落ちる |
| `https://cloud.apextox.dpdns.org/healthz` | 管理DBに届くか。**Authentik は見ない**（Authentik が止まっていても API は正常） |

秘密値はすべて cloud-01 上で自動生成し、再実行しても作り直しません。Git には入りません。

| 場所 | 中身 |
| --- | --- |
| `/opt/cloud-stack/secrets/db_password` | 管理DBのパスワード |
| `/opt/cloud-stack/secrets/bootstrap_admin_key` | ブートストラップ管理キー（下記） |
| `/opt/cloud-stack/secrets/oidc_credentials` | identity VM の `/opt/identity-stack/secrets/oidc-cloud.json` の写し |
| `/srv/cloud-stack/storage/postgres` | 管理DB |

**OIDC クライアントの秘密値は SOPS に入れていません。** 以前は `cloudapi.sops.yaml` へ入れる予定でしたが、正本は identity VM にあり、2か所に持つと Authentik 側で作り直したときに食い違います。配備のたびに Ansible が identity VM から直接写し、ログには出しません（`tests/test_cloud_stack.py` が `no_log` を検査）。

#### 実機での確認（2026-09-10）

| 確認 | 結果 |
| --- | --- |
| `cloud.yml` の初回 | 失敗。PostgreSQL 18 がマウント先に入れなかった（下記）。直して再配備し成功 |
| `cloud.yml` の再実行 | `changed=0` |
| コンテナ | `api`・`postgres` とも healthy。メモリは API 7MiB、PostgreSQL 65MiB、VM 全体で約500MiB / 2GiB |
| `/healthz` | 200 |
| `/auth/login` | Authentik の authorize へ 302。`redirect_uri` は `http://192.168.10.205:8080/auth/callback`、PKCE は S256。Authentik はエラーでなくログイン画面へ進んだ |
| ブートストラップ管理キーで `GET /v1/caller-identity` | 200、`bootstrap-admin`（管理者） |
| アクセスキーで `POST /v1/access-keys` | 403 `UnauthorizedOperation` |
| 秘密値だけ違うキー | 401。監査ログに `AuthFailure`（`secret_mismatch`） |
| 資格情報なし／クロスサイトの POST | 401／403 `CrossOriginRequestBlocked` |
| ブラウザで Authentik にログインする | **未確認。**パスワード入力が要るので人が行う |

初回の失敗: PostgreSQL 18 のイメージは、postgres ユーザー（uid 70）になってから `<マウント先>/18/docker` を作ります。マウント元が root 所有の 0700 だと入れず、`mkdir: can't create directory '/var/lib/postgresql/18/'` で再起動を繰り返しました。`manage.py init` がマウント元を uid 70 にするよう直しました。

#### アクセスキー

- ポータルで発行し、`Authorization: Bearer sca_<キーID>.<秘密値>` で送ります。秘密値は発行時に一度だけ表示し、DB にはハッシュだけを置きます。
- **アクセスキーでアクセスキーは作れません。** 発行はポータルのログインからだけです。漏れたキーが自分の複製を作って居座れないようにするためです。一覧と削除はキーからもできます。
- 1アカウント5本まで。期限は任意（30日・90日・1年・無期限）です。
- 削除したキーは行を残して無効にします。監査ログがキーIDを指したままにするためです。
- 他人のキーを削除しようとすると「存在しない」と同じ 404 を返します。cloud-admins は誰のキーでも削除できます。

#### ブートストラップ管理キー（2026-09-11 に無効化済み）

ポータルでログインしなくても、Authentik が止まっていても、管理者が API を叩けるキーです。持ち主は `bootstrap-admin` という専用アカウントで、cloud-admins と同じく全体が見えます。

**セルフサービスが実利用できるようになったので、2026-09-11 に無効化しました**（ファイルは空、DBのキーは失効）。以後の機械アクセスは、ポータルにログインして発行するアクセスキーを使ってください。`akadmin` は `cloud-admins` に入っているので、`https://cloud.apextox.dpdns.org` からログインしてキーを発行できます。

再び管理用キーが要る場合（ポータルに入れない等の緊急時）:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.205
sudo sh -c 'cd /opt/cloud-stack && python3 manage.py rotate-bootstrap-key'
```

取り出し方（無効化前・再有効化後のみ。通常は空）:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.205 sudo cat /opt/cloud-stack/secrets/bootstrap_admin_key
```

使い方:

```bash
curl -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" https://cloud.apextox.dpdns.org/v1/caller-identity
```

**ファイルが正本です。** API は起動時に DB をファイルへ合わせます。

| やりたいこと | cloud-01 の `/opt/cloud-stack` で実行 |
| --- | --- |
| 取り替える（古いキーは失効） | `sudo sh -c 'cd /opt/cloud-stack && python3 manage.py rotate-bootstrap-key'` |
| 無効にする | `sudo sh -c 'cd /opt/cloud-stack && python3 manage.py disable-bootstrap-key'` |

ただし、**API から削除したキーはファイルに残っていても復活しません**。緊急の失効を再起動で取り消さないためです。使い直すときは `rotate-bootstrap-key` で新しいキーにします。

#### 監査ログ

- 記録するもの: すべての変更、ログイン（拒否も含む）、**実在する**キーIDでの認証失敗。存在しないキーIDでの失敗はアプリのログだけに出します。誰でも作れる値で DB を埋めさせないためです。
- `event_name` は OpenAPI の operationId です。項目名は CloudTrail の LookupEvents に揃えています。
- テーブルは追記専用です。UPDATE・DELETE・TRUNCATE はトリガーが拒否します。
- `GET /v1/audit-events` で読めます。利用者は自分のアカウントの分だけ、cloud-admins は全体です。

#### ログインの扱い

- Authentik 側で `cloud-users` / `cloud-admins` 以外は弾いていますが、API でも `groups` を確認します。Authentik の設定を誤って外しても、全員に開かないようにするためです。
- 管理者かどうかはログインのたびに `groups` から読み直します。`cloud-admins` から外した人は、次のログインで一般利用者になります。
- **知らない `sub` が既存アカウントのメールアドレスで来たら、ログインを拒否します。** Authentik のユーザーを作り直したときに起きます。別アカウントを黙って作ると、その人のリソースが2つに分かれるためです。起きたら監査ログに `AccountConflict` が残るので、管理DBの `accounts.subject` を新しい値へ直します。

#### 開発とテスト

```bash
cd cloud/api && go test ./...
```

DB を使うテストは `SHAKECLOUD_TEST_DATABASE_URL`（データベースを作れるユーザー）を設定したときだけ走り、テストごとに DB を作って消します。CI は PostgreSQL のサービスコンテナで走らせます。ログインのテストは偽の OIDC プロバイダを立て、state・nonce・PKCE の検査まで本物のコードを通します。

### 3-9. 名前と HTTPS

LAN の中の管理画面に `*.apextox.dpdns.org` の名前を付け、Let's Encrypt の証明書で HTTPS にしています。**インターネットには公開していません。** 決めた理由は[ネットワーク・公開範囲・SSO](../architecture/network-auth.md)の「DNSとHTTPS」にあります。

仕組みは3段です。どれも `platform/terraform/dns.yaml` が正本です。

| 段 | 担当 | すること |
| --- | --- | --- |
| 1. 名前 | Terraform `20-dns` | Cloudflare に A レコードを書く。アドレスは 10-platform・05-seed の出力から引き、書き写さない |
| 2. 証明書と入口 | Ansible ロール `tls_proxy`（`stacks/tls-proxy/`） | 各ホストに Caddy を置き、DNS-01 で証明書を取り、127.0.0.1 のサービスへ中継する |
| 3. サービス側 | 各ロール | Authentik と API は 127.0.0.1 に閉じ、URL を HTTPS の名前にする。NetBox は名前を許可に足す |

名前を足すときは、`dns.yaml` にレコードを足してから次を流します。

```bash
tools/tf 20-dns apply
```

そのあと、そのホストの playbook を流すと Caddy が名前を受けるようになります。identity は `identity.yml`、cloud-01 は `cloud.yml`、services-01 は `netbox.yml` か `docs-site.yml` です。**services-01 の2つは静的インベントリ `platform/ansible/seed.ini` で流します**（NetBox の動的インベントリに services-01 は居ません。動的インベントリで流すと何もせずに成功したように終わります）。

Caddy が使う Cloudflare のトークンは `platform/sops/cloudflare-dns.sops.yaml` にあり、**ゾーンの読み取りと DNS の編集**の2つの権限が要ります。テンプレート「ゾーン DNS を編集する」で作れば、両方が付きます。

証明書は Caddy が期限の約30日前に自動で更新します。証明書は各ホストの `/srv/tls-proxy/storage/data` にあり、ここを消すと取り直しになります。Let's Encrypt には1ドメインあたり週50枚の上限があるので、何度も消さないでください。

クラウドAPI は Caddy の後ろにいるので、監査ログの送信元は Caddy が付ける `X-Forwarded-For` から取ります。**信用するのは同じホストの Caddy から来たときだけ**です（`SHAKECLOUD_TRUSTED_PROXIES`）。直接つないで偽の値を送っても、ログには記録されません。

#### 実機での確認（2026-09-10）

| 確認 | 結果 |
| --- | --- |
| 証明書 | `auth`・`cloud`・`netbox`・`docs` とも Let's Encrypt。警告は出ない |
| `http://` で開く | `https://` へ転送（308） |
| Authentik の issuer | `https://auth.apextox.dpdns.org/application/o/cloud/` |
| ポータルからのログイン開始 | 戻り先 `https://cloud.apextox.dpdns.org/auth/callback` を Authentik が受け付け、ログイン画面へ進んだ |
| セッション Cookie | `Secure` が付いた |
| LAN から Authentik の `:9000`・`:9443`、API の `:8080` | 閉じている |
| HTTPS 越しの NetBox のログイン | CSRF 検査を通る。誤った資格情報で試し、403 ではなく「パスワードが違う」が返った |
| 監査ログの送信元 | Caddy ではなく実際の端末（192.168.10.203）。わざと送った偽の `X-Forwarded-For` は無視された |

#### 実際に起きたこと

| 症状 | 原因と対処 |
| --- | --- |
| レコードを作った直後に、ルーターや 1.1.1.1 が「名前が無い」と返す（Google は SERVFAIL） | Cloudflare の中で反映が終わる前に問い合わせた。1分ほどで全部引けるようになった。権威サーバー（`daisy.ns.cloudflare.com`）に直接聞くと、作った時点で答えている |
| ルーターは答えるのに、あるホストだけ名前を引けない（`docs.apextox.dpdns.org` で起きた） | そのホストの systemd-resolved が、反映前の「名前が無い」を最大30分覚えていた。`sudo resolvectl flush-caches` で直った。`tls_proxy` の HTTPS 確認がこれで失敗することがある |
| Tailscale の DNS（100.100.100.100）がどの名前にも SERVFAIL を返す | Tailscale 側の DNS 設定の問題で、この名前に限らない。LAN の中では使わないので影響しない。外出先から使うときの課題（サブネットルートも未設定） |

### 3-10. インスタンス（Phase 2）

**API から VM が作れます。** 2026-09-10 に実機で、作成 → SSH でログイン → 削除 → 残骸なしまで確認しました。

| 操作 | 呼び方 |
| --- | --- |
| 共有イメージの一覧 | `GET /v1/images` |
| 雛形の一覧 | `GET /v1/instance-types`（`flavors.yaml` と同じ名前）。**選ばなくてもよい** |
| 作成 | `POST /v1/instances`（`image_id` と、`vcpus`＋`memory_mib`。任意で `memory_min_mib`・`ballooning`・`root_disk_gib`・`user_data`・`client_token`・`tags`。`instance_type` を使えば値が埋まる） |
| 一覧・1台 | `GET /v1/instances`、`GET /v1/instances/{id}`。**一覧はクラウドの全VM**（所有者名・イメージ名つき） |
| 大きさの変更 | `PATCH /v1/instances/{id}`（`cloud-admins` だけ） |
| 電源 | `POST /v1/instances/{id}/start`・`/stop`・`/reboot` |
| 削除 | `DELETE /v1/instances/{id}` |

**大きさは自由に決められます。**決まったサイズの一覧から選ぶ必要はありません。

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"image_id":"img-debian13","vcpus":6,"memory_mib":20480,"ballooning":false,"root_disk_gib":120,"tags":{"Name":"game"}}' \
  https://cloud.apextox.dpdns.org/v1/instances
```

- `instance_type` は**任意の近道**です。指定すると `flavors.yaml` の値が入り、そこから好きな項目だけ上書きできます。1つでも上書きするとその型名は外れます（一覧では「カスタム」）。
- `ballooning: false` は**固定メモリ**です（Proxmox の `balloon=0`）。ゲームVMのように実際に使い切る相手には、返ってこないメモリを空きに数えないぶん、こちらが正直です。
- `ballooning: true`（既定）のとき `memory_min_mib` が回収の下限で、省略すると**上限の 1/4**（最低 512MiB）になります。
- vCPU はノードのスレッド数（16）を超えられません。メモリとディスクは上限（`/v1/limits`）と実際の空きが決めます。

**管理者は後から変えられます。**vCPU・メモリ・バルーニングは停止中だけ、ディスクは稼働中でも拡大のみです。

```bash
curl -X PATCH -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"vcpus":8,"memory_mib":16384,"ballooning":true}' \
  https://cloud.apextox.dpdns.org/v1/instances/i-0123456789abcdef0
```

**ディスクは縮められません。**縮小はゲストのファイルシステムに知らせずに末尾を捨てる操作なので、断ります。

#### 実機での確認（2026-09-11）

| 確認 | 結果 |
| --- | --- |
| 型名なしで作成（2vCPU・3072MiB・バルーニングなし） | そのまま通った。`instance_type` は付かず、`memory_min_mib` は 0 |
| Proxmox の実物 | `cores=2`、`memory=3072`、**`balloon=0`**（バルーニング無効） |
| 一覧 | クラウドの全VMが出て、**所有者名とイメージ名**が付く |
| 稼働中に `memory_mib` を変更 | **409**（次回起動までは反映されないので断る） |
| 稼働中にディスクを 25GiB へ | 200。実物が `size=25G` になった |
| ディスクを 10GiB へ縮小 | **400**（拒否） |
| 停止後に 4vCPU・6144MiB・バルーニング有効へ | 200。床は上限の 1/4 の **1536MiB** に再計算 |
| Proxmox の実物 | `cores=4`、`memory=6144`、`balloon=1536` |
| 削除 | `terminated`、VM の残骸なし |
| 監査ログ | `ModifyInstance` が成功・`IncorrectInstanceState`・`InvalidParameterValue` の3通りとも残った |

作成の例（アクセスキーは Terraform・CLI と同じもの）:

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"image_id":"img-debian13","instance_type":"small","root_disk_gib":20,"tags":{"Name":"web"}}' \
  https://cloud.apextox.dpdns.org/v1/instances
```

**返事は即座に返り、状態は `pending` です。** 作成は裏で進むので、`GET /v1/instances/{id}` が `running` になるのを待ちます。失敗したときは `terminated` になり、`state_reason` に理由が入ります。

裏で進む順番は次のとおりで、**途中で落ちても同じところから再開します**（できたものを記録してから次へ進むため）。

1. NetBox の IP Range から住所を採番する（`description` は instance ID）
2. seed ISO を作って `cloud-images` へ上げる
3. VM を作る（イメージからディスクを作り、seed ISO を CD-ROM で付ける）
4. ディスクを指定の大きさへ広げる
5. 起動する

削除は逆順で、VM・ディスク・seed ISO・NetBox の IP をすべて解放してから `terminated` になります。**作成に失敗した場合も同じ経路で片付きます。**

上限の既定値は `platform/terraform/cloud.yaml`、**変更は管理者が画面から**行います。既定は1アカウント 8台・32vCPU・32GiB・ルートディスク計 1000GiB、クラウド全体のメモリ枠 32GiB、ノードに 4GiB 残す、ディスク実使用率 85% です。**停止中のインスタンスも数えます**（起動すれば同じだけ使うため）。詳しくは [3-11](#3-11) を参照してください。

#### 安全のための決めごと

- **他人の VM には触りません。** 作った VM の description に instance ID を書き、それが無い VMID は隔離して二度と払い出しません（手で作った VM が同じ番号に居た場合を実機で確認済み）。
- **差分リコンサイラは何も消しません。** ゲスト側の shutdown や GUI での操作には追従しますが、「VM が見えない」ときは記録だけです。ACL の事故でも同じ見え方になるためで、全台が同時に見えないときは何もしません。
- **監査ログに残ります。** 作成・削除・電源操作は、誰がどのキーで行ったかが `GET /v1/audit-events` に出ます。

#### 実機での確認（2026-09-10）

| 確認 | 結果 |
| --- | --- |
| `POST /v1/instances` | 202、`pending`。数十秒で `running` |
| NetBox | `192.168.10.100/24` を採番、DNS 名は Name タグから、`description` は instance ID |
| Proxmox の VM | VMID 5000、10GiB のディスク、seed ISO の CD-ROM、指定した MAC、バルーニング 2048/512、タグ `shakecloud` |
| **seed ISO が効いたか** | **SSH でログインできた。**ホスト名・IP・既定経路が指定どおりで、`cloud-init status` は `done` |
| `DELETE /v1/instances/{id}` | 202、`shutting-down` → `terminated` |
| 後片付け | VM・ディスク・seed ISO・NetBox の IP すべて残骸なし |

この一連は `tools/verify-instances.py` として残してあるので、いつでも同じ確認ができます（残骸があれば失敗します）。

<a id="3-11"></a>
### 3-11. 容量の確認と、上限の変更

**上限は管理者が実行中に変えられます。**ポータルの「上限」か `PUT /v1/limits` です。`cloud.yaml` は**既定値**で、管理者が変えた項目だけが管理DBに入ります（同じ事実を2か所に持たないため）。空欄にすれば既定値へ戻ります。

| 操作 | 呼び方 |
| --- | --- |
| いまの容量（CPU・メモリ・ストレージ・配った合計） | `GET /v1/capacity`、ポータルの「容量」 |
| 上限を読む（実効値・既定値・管理者が変えた分） | `GET /v1/limits` |
| 上限を変える（`cloud-admins` だけ） | `PUT /v1/limits` |

```bash
curl -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" https://cloud.apextox.dpdns.org/v1/capacity
```

`PUT` は**全体を置き換えます。**送らなかった項目は既定値へ戻るので、「昔いじった上限が残っていた」が起きません。`{}` を送れば全部が既定値へ戻ります。

```bash
curl -X PUT -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"account_quota":{"memory_mib":0},"capacity":{"memory_budget_mib":49152}}' \
  https://cloud.apextox.dpdns.org/v1/limits
```

**0 は無制限です。**台数・vCPU・メモリ・ディスク合計と、クラウド全体のメモリ枠に使えます。

#### 何がホストを守っているか

無制限にできるのは**方針の枠**だけで、実際の容量を見る検査は残ります。ここを理解しないまま 0 にするとホストごと倒せます。

| 検査 | 既定 | 0 にすると |
| --- | --- | --- |
| `node_memory_reserve_mib` | 4GiB | ノードに何も残さない。**ただし「要求ぶんが実際に空いている」検査は消えません** |
| `vm_disk_max_used_percent` | 85% | ディスクの使用率を見なくなる。シンプロビジョニングなので、ゲストからは空いて見えたまま書き込みが失敗します |
| `memory_budget_mib` | 32GiB | クラウドが配る上限の合計に制限が無くなる（物理は上の2つが見る） |

#### 16GiB のVMを作る

`2xlarge`（8vCPU・16GiB、バルーニングの下限 4GiB）を追加しました。既定の上限のままで作れます。

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"image_id":"img-debian13","instance_type":"2xlarge","root_disk_gib":100,"tags":{"Name":"game"}}' \
  https://cloud.apextox.dpdns.org/v1/instances
```

**上限の合計と実際の空きは一致しません。**バルーニングを前提にしているので、上限の合計は物理メモリを超えられます。超えたぶんは「ゲストが使っていなければ返る」という前提に乗っているだけで、ゲームVMのように実際に使う相手からは返りません。「容量」の画面が**両方**を並べて出すのはそのためです。考え方は[配備台帳の実測](../architecture/operations.md#measured-budget)にあります。

#### 実機での確認（2026-09-10）

| 確認 | 結果 |
| --- | --- |
| `GET /v1/capacity` | ホスト 61095 MiB・8コア/16スレッド・ストレージ2つを返した。管理者にはアカウント別も付く |
| 上限の初期状態 | 実効値＝既定値、上書きは空（`{}`） |
| `PUT /v1/limits`（台数だけ 3 に） | 実効値が 3 になり、**保存されたのは `account_quota.instances` だけ**。他の項目は既定値のまま。変更者と時刻が記録された |
| `PUT /v1/limits {}` | すべて既定値へ戻り、上書きが消えた |
| `GET /v1/instance-types` | `2xlarge` = 8vCPU・16384 MiB・下限 4096 MiB |
| **16GiB の作成** | `pending` → `running`。NetBox が `192.168.10.100/24` を採番 |
| Proxmox の VM | VMID 5000、`memory=16384`、**`balloon=4096`**、`cores=8` |
| 「容量」の集計 | 配ったメモリが 16384 MiB に増えた |
| 削除 | `terminated`。VM の残骸なし |
| 監査ログ | `UpdateLimits`・`RunInstances`・`TerminateInstance` が残った |

<a id="3-12"></a>
### 3-12. イメージのアップロードと SSH鍵

| 操作 | 呼び方 |
| --- | --- |
| イメージの一覧（共有＋全員のアップロード） | `GET /v1/images` |
| アップロード | `POST /v1/images`（`multipart/form-data`、`name` と `file`） |
| 削除 | `DELETE /v1/images/{image_id}` |
| SSH鍵の登録・一覧・削除 | `POST`/`GET`/`DELETE /v1/key-pairs` |
| 作成時に鍵を入れる | `POST /v1/instances` の `key_name` |

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -F 'name=ubuntu 24.04' -F 'file=@noble.qcow2' https://cloud.apextox.dpdns.org/v1/images
```

**`name` を `file` より先に送ってください。**素通しで流すので、ファイルの名前をファイルより後には受け取れません。

#### なぜ直接アップロードなのか（実測）

設計当初は「URL を渡して Proxmox に取りに行かせる」（`download-url`）方が軽いと見えましたが、**`cloudapi@pve` では 403** でした。絞ったトークンには許されていません。一方 `upload` は `content=import` を受け付けます（どちらも 2026-09-11 に実測）。したがって **API を通した直接アップロードが唯一の道**です。

そのうえで3つの制約が実装を決めました。**最初に書いた「素通しで流す」設計は実機で成立しませんでした。**

- **Proxmox はチャンク転送を 501 で拒否します**（`chunked transfer encoding not supported`、2026-09-11 実測）。つまり**本文の長さを先に宣言しなければ受け取ってもらえません**。長さは本文の終わりまで分からないので、「一切溜めずに流す」ことは**できません**。
- したがって cloud-01 の**実ディスク**（`/srv/cloud-stack/storage/uploads`、コンテナ内は `/var/lib/shakecloud/uploads`）へ一旦書き出し、大きさを確定させてから Proxmox へ流します。**`/tmp` は RAM（tmpfs）なので使えません**（cloud-01 の RAM は 2GiB、ディスクの空きは約31GiB）。multipart の枠は自前で組み立てて長さを正確に計算し、**中身はストリームで送ります**（枠だけがメモリに載ります）。
- **サーバの読み取り期限は 30秒**です。アップロードのときだけ**この1リクエストの期限を外します**（他のリクエストは今までどおり守られます）。なお `statusRecorder` に `Unwrap()` が無いと期限を外せません（`feature not supported` になる）。

**上限の既定を 12GiB にしてあるのはこのためです。**置き場（Proxmox のルートFS）と cloud-01 のディスクの**両方**に同じ大きさが必要で、cloud-01 の空きは約31GiB しかありません。

**中身の検査は Proxmox が qemu-img で行います。**壊れたファイルや対応外の形式はタスクが失敗し、**何も残りません**（実測で確認）。大きさは `max_image_gib`（既定 12GiB、管理者が変更可、0 は無制限）と、置き場に残す空き（`image_store_min_free_mib`）で決まります。置き場は Proxmox のルートFS（約94GiB）で、ISO やバックアップと同じ領域を分け合います。

**共有イメージは API から消せません。**Terraform の宣言物なので、消すならコードを直します。利用者のイメージは所有者と管理者が消せます。**そのイメージから既に作った VM は無関係です**（作成時にディスクへ複製済み）。ただし**作成中の VM がある間は**断ります。

#### SSH鍵

**公開鍵だけを保存します。**秘密鍵を貼った場合はそう指摘して弾きます。フィンガープリントは `ssh-keygen -lf` と同じ `SHA256:…` 形式なので、手元の鍵と見比べられます。

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' -d "{\"key_name\":\"laptop\",\"public_key\":\"$(cat ~/.ssh/id_ed25519.pub)\"}" https://cloud.apextox.dpdns.org/v1/key-pairs
```

**鍵は `user-data` ではなく `meta-data` の `public-keys` で渡します。**`user-data` は自由書式で、シェルスクリプトを書く人もいます。そこへ鍵を混ぜ込むのは他人の文書を書き換える操作なので、cloud-init 自身が持つ経路を使います。

**鍵の本文は作成を受け付けた時点でインスタンスへ複製します。**直後に鍵ペアを消されても、入れない VM は生まれません。逆に後から鍵ペアを消しても**既存の VM は動き続けます**（鍵はその VM の seed イメージの中にあります）。

#### 実機での確認（2026-09-11）

`qemu-img` で作った本物の qcow2（196,616 バイト）を使いました。

| 確認 | 結果 |
| --- | --- |
| アップロード | 201。`cloud-images:import/img-….qcow2` として実在し、形式は store が返した `qcow2` |
| 一覧 | 共有イメージは `public` のまま、アップロード分は所有者名つきで並ぶ |
| ディスクイメージでないファイル | **400** |
| ファイルを付けない要求 | **400** |
| 共有イメージの削除 | **409**（Terraform の宣言物なので API からは消せない） |
| 鍵の登録 | 201。フィンガープリントが **`ssh-keygen -lf` と完全一致** |
| 同じ名前で2回 | **409** |
| 秘密鍵を貼る | **400** |
| `key_name` を付けて作成 → SSH | **ログインできた。**`user_data` は一切送っていないので、`meta-data` の `public-keys` が効いた証拠 |
| 鍵ペアを消してから再ログイン | **入れた**（鍵は seed イメージの中にある） |
| イメージの削除 | 204。置き場は元の1件（共有イメージ）だけに戻った |
| 監査ログ | `ImportImage`・`DeleteImage`・`ImportKeyPair`・`DeleteKeyPair` が成功・失敗とも残った |

**空の qcow2 は起動しないので、「アップロードしたイメージから起動する」ところまでは実機で確かめていません。**API がそのイメージの実体を VM 作成時に渡すことは単体テストで検査しています（`import-from=` が作成パラメータに入ること）。

<a id="3-13"></a>
### 3-13. Webコンソール

ポータルのインスタンス一覧で、**稼働中の自分のVM**（管理者は全VM）に「コンソール」ボタンが出ます。押すと別タブで noVNC の画面が開きます。上部に Ctrl+Alt+Del・全画面・画面に合わせる・切断のボタンがあります。

API から開く場合:

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" https://cloud.apextox.dpdns.org/v1/instances/i-0123456789abcdef0/console
```

返ってくる `url` を、**同じアカウントでログインしたブラウザ**で開きます。URL は5分有効で、別のアカウントでは使えません。

#### 仕組みと、そうした理由

**3段階に分けています。**2つの制約が逆を向いているためです。

1. `POST …/console` は**開けるかどうかの判定だけ**をして URL を返します（所有者か管理者か、稼働中か）。Proxmox にはまだ何も頼みません。
2. **ページを開いた瞬間に** Proxmox へ VNC のチケットと使い捨てパスワードを頼みます。Proxmox の VNC プロキシは起動してから**数秒しか接続を待たない**ので、接続の直前まで遅らせています。そのため**ページを再読み込みすれば新しいチケットで繋ぎ直せます**。
3. ページの WebSocket は **API が中継します**。ブラウザは WebSocket に `Authorization` ヘッダを付けられませんが、Proxmox の `vncwebsocket` はそれを要求するためです。API が自分の `cloudapi@pve` トークンで Proxmox に接続し、あとは**中身を解釈せずバイト列をそのまま双方向にコピー**します（WebSocket のライブラリは使っていません）。

**noVNC 1.7.0 を同梱しています**（`cloud/api/internal/server/web/static/novnc/`）。npm の sha512 と照合した tarball から無改変で取り、ライセンス（MPL-2.0）も同梱しました。CDN は使いません。更新手順は同じ場所の `PROVENANCE.md` にあります。

#### 守っていること

- **他サイトからは開けません。**Cookie で認証された WebSocket は、Origin がこのサイトでなければ断ります。`http.CrossOriginProtection` は POST などしか見ないので、GET で始まる WebSocket はここで別に守る必要があります。
- **1回のページ表示で張れる WebSocket は1本だけ**です。URL を誰かに見られても、横から同じ画面に入れません。
- **URL のトークンはログに出しません**（`/console/{token}` と記録します）。API のメモリ上もハッシュで持ちます。
- パスワードを含むページは**キャッシュさせません**（`Cache-Control: no-store`）。
- 開いた記録と接続した記録が、どちらも**監査ログに残ります**（`CreateConsoleSession`、`ConnectConsole`）。

#### 実機での確認（2026-09-11）

ブラウザを使わず、生の TLS ソケットで noVNC と同じ手順を踏みました（ページと WebSocket はアクセスキーでも認証できるため）。

| 確認 | 結果 |
| --- | --- |
| 起動中に `POST …/console` | **409**（まだ VM が無い） |
| 稼働後に `POST …/console` | 201、`/console/…` の URL |
| `console.js`・noVNC の `rfb.js`・`pako` | どれも 200 で `text/javascript` として配信 |
| ページ | 200。専用の CSP（`img-src 'self' data: blob:`）と `Cache-Control: no-store`、WebSocket のパスと使い捨てパスワードを含む |
| **API を通した WebSocket** | 101（accept キーも正しい）。**最初のフレームは VM の VNC サーバからの `RFB 003.008`**（マスク無しのバイナリ）。ブラウザ側 → API の中継 → Proxmox の `vncwebsocket` → VM の VNC、の全経路が実物で繋がった |
| 同じページ表示で2本目 | **404** |
| ページを再読み込みして接続 | 101 と `RFB 003.008`（再接続できる） |
| ログインせずにページを開く | **401** |
| 存在しない URL の WebSocket | **404** |
| API のログ | **トークンは出ていない**。接続と切断は記録されている |
| 監査ログ | `CreateConsoleSession`（成功と `IncorrectInstanceState`）、`ConnectConsole` |

**画面そのもの（noVNC がブラウザで絵を描くところ）は、この確認では見ていません。**ポータルの「コンソール」から開いて確かめてください。サーバ側は、テンプレートの項目がハンドラと一致することと、ページにインラインのスクリプトやスタイルが無いこと（CSP で弾かれるため）を Go のテストで検査しています。

<a id="3-14"></a>
### 3-14. ボリュームとセキュリティグループ（Phase 4）

**2026-09-11 に実機で確認済みです。** 実装の範囲は次のとおりです。

| 操作 | 呼び方 |
| --- | --- |
| ボリュームの作成・一覧・拡張・削除 | `POST`/`GET`/`PATCH`/`DELETE /v1/volumes` |
| ボリュームのアタッチ・デタッチ | `POST /v1/volumes/{id}/attach`、`POST /v1/volumes/{id}/detach` |
| セキュリティグループの作成・ルール追加・削除 | `POST`/`GET`/`DELETE /v1/security-groups`、`POST /v1/security-groups/{id}/{ingress,egress}`、`DELETE /v1/security-groups/{id}/rules/{rule_id}` |
| インスタンスへの SG 適用 | `PUT /v1/instances/{id}/security-groups` |

設計上のポイント:

- **追加ボリュームは Proxmox の `move_disk` で差し替えます。** Proxmox のディスクは必ずどれかの VM の持ち物なので、デタッチ時には専用の「起動しないホルダーVM」（VMID 5997）へ移動します。
- **セキュリティグループは VM 単位のファイアウォールルールに展開します。** Proxmox のクラスター全体ファイアウォールグループは `cloudapi@pve` に権限がないため、各 VM の `/nodes/<node>/qemu/<vmid>/firewall/rules` へ書き込みます。ルール変更時は対象 VM 全台のルールを全書き換えします。
- **データセンターのファイアウォール有効化は Terraform で安全に自動化しています。** `platform/terraform/00-bootstrap/firewall.tf` は、ノードのファイアウォールは無効のまま、データセンターのファイアウォールだけを有効・既定ポリシー ACCEPT にします。これによりホスト自身への通信は今までどおり通り、VM 単位の `firewall=1` な VM のみが絞られます。さらに `nf_conntrack_allow_invalid=1` を設定し、ファイアウォール有効化による RST  drop（接続タイムアウト化）を防ぎます。

#### 実機で確認したこと（2026-09-11、PVE 9.2.2）

`cloudapi@pve` トークンとブートストラップ管理キーで、次をすべて実機で確認しました。

1. **`firewall.tf` は適用済みで安定している。**`tools/tf 00-bootstrap plan -detailed-exitcode` が **No changes（終了コード 0）**。実機はノードFW無効、DC FW有効・既定 ACCEPT、`nf_conntrack_allow_invalid=1` で、宣言と一致しています。
2. **新プローブ2つが PASS。**`volume_reassign`（`move_disk` の往復と強制破棄）、`vm_firewall`（ルール順序・IPセット・オプション書き込み）。既存4つと合わせて **6/6 PASS**。
3. **ボリュームの縦串。** API で作成（`creating`→`available`）→ 稼働中インスタンスへアタッチ（`virtio1`、`in-use`）→ ゲスト内に `/dev/disk/by-id/virtio-vol65ff58d26f4697fed` が 1GiB で出現 → 1→2GiB に拡張（ゲストにも反映）→ デタッチ（`available`、デバイス消滅）→ 削除（`deleted`）。ホスト側にディスクもホルダー上の `unusedN` も残りませんでした。
4. **セキュリティグループの遮断と許容。** SSH（tcp/22、LAN のみ）だけを許可した SG を適用し、**SSH は通り、許可していない tcp/8000 はタイムアウト、ICMP も drop**。8000 を許可するルールを足すと 200 になり、そのルールを消すと再び遮断。`firewall_state` は各変更後に `in-sync` になりました。
5. **DC FW 有効化で既存VMに影響なし。** identity・cloud-01・services-01・game1 へ SSH/HTTPS で到達でき、`https://cloud.apextox.dpdns.org/healthz` は 200、NetBox と Authentik は 302。基底VMはすべて NIC `firewall=0`、game1 は `firewall=1` だが VM の `enable` が無いため、どちらも絞られません（この確認の後、game1 は 3-15 で引き取り、既定SGが `enable=1` になった）。

再実行するときは §4 のプローブと §9 のインスタンス検証に加え、`tools/verify-volumes.py` を使ってください。このスクリプトは、使い捨てインスタンスを作り、**実際にポートが遮断・許可されるか**（ルールの見た目ではなく）まで見てから、ボリュームの attach/detach と後片付けを確認します。判定は `tests/test_verify_volumes.py` が実機なしで検査します。

```bash
export SHAKECLOUD_ACCESS_KEY=$(ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.205 sudo cat /opt/cloud-stack/secrets/bootstrap_admin_key)
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-volumes.py'
```

**はまりどころ（2026-09-11 に修正）**: Proxmox は VM の `firewall/options` を書かないと、実行中VMの live ruleset を再構築しません。最初のSG適用で `enable=1`・`policy_in=DROP` になった後はルールだけ変えても options の値は変わらないので、`setFilteredOptions` が PUT を省くと**ホストは前の（緩い）ルールのまま**になります。API の `firewall_state` は `in-sync` でも、許可していないポートが開いたままです。修正は options を**毎回書く**こと（`compute/firewall.go`）。だからこのスクリプトは「設定が正しいか」ではなく「本当に遮断されるか」を見ます。

<a id="3-15"></a>
### 3-15. 既存VMの引き取り（Phase 5）

`POST /v1/instances/adopt`（**cloud-admins のみ**）で、既にあるVMを管理下へ登録します。

**プールへ入れる操作はAPIの外です。** `cloudapi@pve` は既に `cloud` プールに居るVMしか見えず、外のVMをプールへ入れる権限を持ちません。管理者が先に移します（Proxmox の画面、`qm set <vmid> --pool cloud`、または Terraform）。

```bash
# 既存VMを cloud プールへ入れる（管理者。APIトークンではできない）
ssh root@192.168.10.126 qm set 100 --pool cloud
```

```bash
# 引き取る。owner は12桁のアカウントID（ポータルの「容量」や /v1/caller-identity で見える）
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"vmid":100,"account_id":"123456789012","private_ip_address":"192.168.10.130"}' \
  https://cloud.apextox.dpdns.org/v1/instances/adopt
```

読み取るものと、断る条件:

| 項目 | どこから |
| --- | --- |
| vCPU・メモリ・バルーニングの下限 | Proxmox の VM 設定（`cores`・`memory`・`balloon`） |
| MACアドレス | `net0` |
| ルートディスク | ディスクの volid からストレージの実サイズを測る。読めないときだけ `root_disk_gib` を明示 |
| 名前 | `name`（リクエスト → VM設定 → `tags.Name` の順） |
| 状態 | `running` か `stopped` だけ。`paused` などは断る |

断るのは、**プールに無いVMID**（404。先に移す）、**既に引き取り済み／生存中のVMID**（409）、**予約VMID（ホルダー5997・プローブ5998/5999）**、**未登録のアカウント**、**MACが無い**、**クォータ超過**です。引き取ったインスタンスは `adopted=true` で記録し、以後は電源・コンソール・タグ・SGが普通に効きます。ソースイメージ・user-data・seed ISO は持ちません。

`adopted` のインスタンスは `owns()` が無条件で持ち主とみなします。APIが作ったVMは description に instance ID を書きますが、引き取ったVMにはそれが無いためです。

**2026-09-11 に実機で確認済み**: 使い捨てVM(5900)で、Proxmox で直接作ったVM（ディスク無し・`root_disk_gib` 指定）を adopt → `GET` で `adopted=true`、重複 adopt は 409 `InvalidParameterValue`、terminate でVMが消えて残骸なし、までを確認。さらに **game1（VMID 100）を実際に引き取りました**: プールへ移す操作は API ではなく root トークンで `PUT /pools/cloud`（vms=100）を実行し、所有者 `shunyazhiyuan97`（`account_id` `154909253172`）と `private_ip_address` `192.168.10.127` を指定して adopt。`state=running`・`adopted=true`・既定SGが `in-sync` になり、**game1 は稼働を続け ping も通る**ことを確認しました。`.127` は NetBox に予約登録し、新規VMに払い出されないようにしています。管理DBのアカウントは、Authentik の `sub`（`0a39d4ca-870f-4c52-963b-8ff0c0ec2660`）に合わせて先に作りました（本人が未ログインでも引き取れるように）。

## 4. 実機プローブ

**設計の前提がこの Proxmox の版で成立するかを機械判定します。**結果が違えば設計を変えるので、実装より先に走らせてください。PVEを上げたあとにも走らせます。

```bash
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-cloud.py'
```

AWX から回す場合は同じことを Job Template で:

```bash
.venv/bin/ansible-playbook -i localhost, platform/ansible/verify-cloud.yml
```

**`cloudapi@pve` のトークンで実行します。**`root@pam` は全部通ってしまい、絞ったアカウントに何ができるかを何も教えません。スクリプトは `root@pam` を渡されたら実行を拒否します。

読み取りと、`cloud` プール内の使い捨てVM（VMID 5998・5999）の作成・削除だけを行い、最後に片付けます。判定は自動で、1つでも落ちれば終了コードが非ゼロになるので、無人実行のゲートに使えます。

**2026-09-10 に PVE 9.2.2 で最初の4つ、2026-09-11 に Phase 4 の2つ（`volume_reassign`・`vm_firewall`）を足した6つとも PASS**、つまり設計の前提はすべて成立しました。

| プローブ | 確かめること | 結果 | 落ちたときに変わること |
| --- | --- | --- | --- |
| `node_status` | 絞ったトークンでノードの空きRAMが読めるか | **PASS** | アドミッション制御が実容量を見られない。`/nodes/<node>` の `CloudApiNodeAudit` を見直す |
| `image_lifecycle` | ISOを上げて、**消せる**か | **PASS** | インスタンスごとの seed ISO が消えず溜まる。管理者側の定期削除へ切り替える |
| `pool_boundary` | `cloud` は通り、`platform` は 403 か | **PASS** | 所有境界が効いていない。**利用者へ公開してはいけない** |
| `console_auth` | `vncwebsocket` がAPIトークンを受けるか | **PASS** | Webコンソールがチケット認証を要求する。`cloudapi@pve` にパスワードを与える |
| `volume_reassign` | デタッチしたディスクを holder VM と他 VM 間で `move_disk` できるか | **PASS**（2026-09-11） | Detach/Attach が成立しない。権限または `move_disk` の扱いを見直す |
| `vm_firewall` | VM のファイアウォールルールを書き、追加順序が想定どおりか | **PASS**（2026-09-11） | セキュリティグループのルールが逆向きに適用される。`firewall.tf` や書き込み順序を見直す |

意味するところ:

- **seed ISO 方式が使える。** 上げたISOを消せるので、インスタンスごとの seed ISO が溜まりません。管理者側の定期削除という代替案は不要になりました。
- **所有境界がACLで効いている。** `cloud` プールへの作成は通り、`platform` プールへの作成は 403 でした。運用規約ではなく権限の形で保証されていることの実測です。
- **Webコンソールに追加の資格情報が要らない。** `cloudapi@pve` にパスワードを与える必要はありません。ここが一番読めない箇所だったので、設計が1つ単純になりました。

プローブは使い捨てVM（5998・5999）と一時ISOを作って**必ず片付けます**。実行後に残骸が無いことも確認済みです。

判定そのもの（403をPASSと読まない、`platform` が200を返したのを「境界は無事」と読まない、など）は `tests/test_verify_cloud.py` が実機なしで検査しています。プローブが嘘をつかないことはCIで担保され、プローブが問う先だけが実機に残ります。

## 5. 元に戻す方法

`00-bootstrap` の適用を戻す場合、`cloudapi@pve` のユーザー・トークン・ACL・`cloud-images` ストレージはすべて Terraform が消せます。**ただしストレージを消しても `/srv/cloud-images` の中身は残ります。**利用者のイメージが入っていないか確認してから消してください。

NetBoxの `cloudapi` アイデンティティは Ansible では消せません。不要になったら NetBox の管理画面からユーザーとトークンを無効化してください。既存のアイデンティティを黙って書き換えない方針のため、seed スクリプトは削除を行いません。

## 6. 実行の委譲（CI/CD）

**現状は「管理PCから人が `tools/tf` を叩く」です。**これを自動実行へ移す場合、次の3つは設計上避けられません。

### `00-bootstrap` は本質的に特権

このモジュールはロール・ユーザー・ACL・ストレージを作ります。**それができるアカウントは、自分自身に任意の権限を付与できます。**したがって「`root@pam` をやめて専用のサービスアカウントにする」は、特権の**移動**であって**縮小**ではありません。移す価値（実行記録が残る、個人の端末に依存しない）はありますが、置き場所の安全性は `root@pam` と同じ基準で考える必要があります。

一方 `10-platform` は `terraform@pve`（`/pool/{platform,dev,lab}` と `/storage` だけ）で動きます。**こちらは委譲しても特権が増えません。**分けて扱うのが素直です。

### ネットワークが届かない

Proxmox は `192.168.10.126`、NATの内側で、外から届かせる方法はまだありません（[ネットワーク・公開範囲・SSO](../architecture/network-auth.md)）。**GitHubのホスト型ランナーからは到達できません。**したがって `plan` / `apply` を自動実行するには、LAN内で動く実行主体が要ります。

| 案 | 状態 |
| --- | --- |
| セルフホストのGitHub Actionsランナー | `cloud-01` に同居できる。ただし cloud-01 自体が未作成 |
| AWX | [配備台帳](../architecture/operations.md)で既に「Ansibleの実行基盤」として計画済み。ただしKubernetes前提で、クラスタが未構築 |
| `cloud-01` 上のpull型エージェント | 一番軽い。`git pull` して `tools/tf plan` を定期実行し、適用は承認制にする |

### 最初の実行主体は人が作る

どの案でも、**その実行主体を最初に作る操作は root で人がやります。**「自分が作る先に自分を置けない」という、`state-store` のstateをローカルに置いているのと同じ構造です。これは怠慢ではなく順序の問題で、`README.md` の「残る手作業は**それ自体が最初の資格情報を生む操作**だけ」という方針そのものです。

### age鍵を個人から外す

`.sops.yaml` は**カンマ区切りで複数の受信者**を取れるようにしてあります。ただし今すぐ足すものはありません。

- **2人目の鍵**は、その人が自分で作って公開鍵を渡すものです。他人の身元を代わりに作ることはできません。
- **無人実行用の鍵**は、その秘密鍵を置く場所（`cloud-01`）がまだ無いので、いま作っても保管先がありません。作るのは cloud-01 ができてからです。

**いま効くのは1つだけです。** 現在 `platform/sops/` の中身を復号できる鍵は1本しかなく、**それを失うと全ての秘密値が復元できません。**リポジトリの外・別の機器へバックアップしてください。

```bash
age-keygen -y ~/.config/sops/age/keys.txt
```

これで公開鍵（`age1...`）が確認できます。秘密鍵そのもの（`keys.txt`）が復元対象です。

受信者を足す段になったら、`.sops.yaml` を更新したあと**必ず再暗号化します**。

```bash
sops updatekeys platform/sops/*.sops.yaml
```

**足しただけでは既存ファイルは復号できません。**`.sops.yaml` には居るのに読めない状態が続きます。`tests/test_sops_config.py` がこのずれをCIで検出します。
