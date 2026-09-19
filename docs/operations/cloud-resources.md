---
title: ボリューム・S3・DB・関数
updated: 2026-09-19
section: 運用手順
audience: 管理者
tags:
  - ops
  - cloud
---

# ボリューム・S3・DB・関数

> **更新日** 2026-09-19 ・ **区分** 運用手順 ・ **読む人** 管理者

[クラウドAPI本体とインスタンス](cloud-api.md)の続きです。インスタンスに足すリソースと、クラウドの残り3機能（S3・database・function）を配備します。

検査は[実機プローブと切り戻し](cloud-verify.md)です。


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

再実行するときは[実機プローブ](cloud-verify.md)と[インスタンス検証](verify.md)に加え、`tools/verify-volumes.py` を使ってください。このスクリプトは、使い捨てインスタンスを作り、**実際にポートが遮断・許可されるか**（ルールの見た目ではなく）まで見てから、ボリュームの attach/detach と後片付けを確認します。判定は `tests/test_verify_volumes.py` が実機なしで検査します。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_...'   # ポータルで発行したアクセスキー（ブートストラップ管理キーは無効化済み）
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-volumes.py'
```

**はまりどころ（2026-09-11 に修正）**: Proxmox は VM の `firewall/options` を書かないと、実行中VMの live ruleset を再構築しません。最初のSG適用で `enable=1`・`policy_in=DROP` になった後はルールだけ変えても options の値は変わらないので、`setFilteredOptions` が PUT を省くと**ホストは前の（緩い）ルールのまま**になります。API の `firewall_state` は `in-sync` でも、許可していないポートが開いたままです。修正は options を**毎回書く**こと（`compute/firewall.go`）。だからこのスクリプトは「設定が正しいか」ではなく「本当に遮断されるか」を見ます。

<a id="3-15"></a>
### 3-15. 既存VMの引き取り（Phase 5）

`POST /v1/instances/adopt`（**admins のみ**）で、既にあるVMを管理下へ登録します。

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

<a id="3-16"></a>
### 3-16. バケットと S3 キー（Phase 7）

Garage の S3 バケットとアクセスキーを、クラウドAPIがアカウント単位で管理します。**オブジェクトの本体はAPIを通りません。** 署名（SigV4）で利用者と S3 が直接やり取りし、APIは「誰のバケットか」「どの鍵に何を許すか」だけを持ちます。

| 操作 | 呼び方 |
| --- | --- |
| バケットの作成・一覧・削除 | `POST`/`GET /v1/buckets`、`GET`/`DELETE /v1/buckets/{name}` |
| S3キーの作成・一覧・削除 | `POST`/`GET /v1/s3-keys`、`DELETE /v1/s3-keys/{key_id}` |
| 鍵に権限を付与・剥奪 | `PUT`/`DELETE /v1/buckets/{name}/keys/{key_id}` |

設計上のポイント:

- **Garage の管理API（v2、`:3903`）を叩きます。** クラウドAPIは用途を絞った管理トークンを使います（`CreateBucket`・`CreateKey`・`AllowBucketKey` など10個だけ）。正本は `platform/sops/cloudapi.sops.yaml` の `GARAGE_ADMIN_TOKEN` で、`cloud_api` ロールが `cloud-01` の `secrets/garage_admin_token` へ写します。
- **鍵の秘密値は保存しません。** Garage が作成時に一度だけ返すもので、APIはその応答で返して捨てます。DBには鍵IDと名前だけを持ちます。
- **バケット名はクラウド全体で一意**（Garage の global alias）。S3 の規則（3–63文字、小文字・数字・`.`・`-`）で検証します。
- **応答の `s3_endpoint`・`s3_region`** が、利用者がクライアントへ設定する値です（いまは `http://192.168.10.206:3900`、`garage`）。

```bash
# バケットと鍵を作り、鍵に権限を付ける
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"bucket_name":"photos"}' https://cloud.apextox.dpdns.org/v1/buckets
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"laptop"}' https://cloud.apextox.dpdns.org/v1/s3-keys   # secret_access_key はここで一度だけ
curl -X PUT -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"read":true,"write":true,"owner":true}' \
  https://cloud.apextox.dpdns.org/v1/buckets/photos/keys/<key_id>
```

CLI は `shakecloud bucket ...` と `shakecloud s3-key ...`（[shakecloud CLI](cli.md)）。

#### 実機で確認したこと（2026-09-11）

- API でバケット `fixture-test` と鍵を作成 → 権限を付与 → **CLI で発行した鍵**を使い、awscli で `PUT`・`LIST`・`GET`・削除がすべて成功、削除後に一覧が空。テスト用のバケット・鍵は削除済み。
- `GET /v1/buckets` はアカウントのバケットだけを返し、他アカウントの鍵を付与しようとすると `NoSuchKey` で断る（単体テストで担保）。

**はまりどころ**: 権限付与（`PUT .../keys/{key_id}`）の応答に鍵一覧を含めるため、`SetBucketPermission`／`RevokeBucketPermission` は監査コールバックより**先に**一覧を読んでから返します。順序を逆にすると応答の `keys` が空になります。

<a id="3-17"></a>
### 3-17. 利用者の招待（identity サービスの仕事）

**利用者の招待は、クラウドAPIでもポータルでもありません。** 認証基盤（identity サービスの Authentik）の管理者の仕事です。クラウドは、招待で作られた利用者が `users` に入っていることを前提に動きます。クラウド側に「招待」という資源は持たせません（役割の混同を避けるため）。

招待は **Authentik の招待専用エンロールフロー** `cloud-invitation-enrollment` で行い、`stacks/identity/invitations.py` が管理します。**手順（`configure`/`invite`/`list`/`revoke`、1回限り・24時間、Gmail でのメール送信、`runtime/invitations/` への保存、実機確認）は[認証基盤（identity・Authentik）の「利用者の招待」](identity.md#利用者の招待管理者)にまとめました。** パスワード・パスキーの復旧も同じページにあります。

<a id="3-18"></a>
### 3-18. 管理DBのバックアップ

`cloud/manage.py backup` が管理DB（PostgreSQL）を **ライブのまま** `pg_dump -Fc` で取り、配備ファイル（`compose.yaml`・`.env`・`secrets/` など）と一緒に1世代ぶんのディレクトリへ保存します。ダンプ中も API は止まりません。

**定期実行**は cloud-01 の systemd timer `cloud-backup.timer` が行います。`cloud_api` ロールが配備し、既定で毎日 **03:40**（`Persistent=true`、最大30分のばらつき）に走ります。

| 項目 | 値 |
| --- | --- |
| 保存先 | `/var/backups/cloud-api/`（既定。`cloud_api_backup_dir`） |
| 保持 | 最新 **14** 世代。古いものは成功後に削除（`--keep`、既定 `cloud_api_backup_keep`） |
| 失敗時 | `.incomplete` のまま残し、**世代を消さない**（唯一の正常コピーを失わないため） |

手で取る:

```bash
sudo sh -c 'cd /opt/cloud-stack && python3 manage.py backup --destination /var/backups/cloud-api --keep 14'
```

戻す（`shakecloud.dump` は `pg_restore` の custom 形式）:

```bash
sudo sh -c 'cd /opt/cloud-stack && cat /var/backups/cloud-api/<stamp>/shakecloud.dump | \
  docker compose -f compose.yaml exec -T postgres pg_restore -U shakecloud -d shakecloud --clean --if-exists'
```

各世代には `shakecloud.dump` のほか `deployment.tar`（`compose.yaml`・`compose.lock.yaml`・`.env`・`secrets/`・`manage.py`）が入ります。**同じホストのディスクなので、これだけではディスク故障に耐えられません。** Garage（`storage-s3`）や別ディスクへの外部コピーは別途で、Garage は単一ノードなので唯一の控えにはしません。

### 3-19. Windows 11 Pro のゲスト

イメージに `os: windows` を宣言すると、API はそのイメージから **UEFI（OVMF）・TPM 2.0・q35** の VM を作り、初回設定を **cloudbase-init の NoCloud**（network config v1）へ渡します。ポータルではイメージ選択時に SSH鍵の欄が消え、初回はコンソールでセットアップする案内が出ます。ディスク・NIC・seed ISO の形は Linux と同じで、イメージ側に virtio ドライバと cloudbase-init が必要です。

管理者が Proxmox の `local:iso` に置いたファイルは、**自動で `GET /v1/isos` へ「共有」として出ます**（宣言不要。読み取り専用ACL `CloudApiSharedISO`＝`Datastore.Audit` だけで、複製もしません）。ポータルからアップロードしたISOは `cloud-images` に入り、同じ一覧に並びます。どちらも全員共有で、アップロードしたものは誰でも削除できます。イメージを使わず、**ISOをインストールメディアとして起動する経路**もあります。`POST /v1/isos` で `.iso` をアップロード（`os: windows` でWindows 11のハードウェア）、`RunInstances` に `install_iso_id`（と任意の `driver_iso_id`）を渡すと、空のルートディスク＋CD-ROMで起動し、コンソールでインストールします。ポータルの「ISO」画面と作成方法「ISOからインストール」がこの経路です。ISOは使用中インスタンスがあると削除できません。

Windows のインストールメディアとプロダクトキーは自動取得できないため、**メディアの用意だけが人の手作業**です。ISO方式の使い方と、ゴールデンイメージを共有イメージにする方式は [Windows 11 ProのVMを作る](windows.md) にあります。
### 3-20. データベース（CloudNativePG）

管理クラウドの「DBアプライアンス」です。`POST /v1/databases` が Kubernetes の `databases` namespace に CloudNativePG の `Cluster` を1つ作ります。実体と配置は [Kubernetes クラスタ](kubernetes.md) を参照。

```bash
BASE=https://cloud.apextox.dpdns.org
# 作成（storage_gib は 1〜50）
curl -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"name":"shop","storage_gib":5}' $BASE/v1/databases
# 一覧・詳細
curl -H "Authorization: Bearer $KEY" $BASE/v1/databases
curl -H "Authorization: Bearer $KEY" $BASE/v1/databases/db-...
# 接続情報（CNPG が作った Secret を読む。owner か cloud-admin だけ）
curl -H "Authorization: Bearer $KEY" $BASE/v1/databases/db-.../credentials
# 削除（Cluster ごと消える）
curl -X DELETE -H "Authorization: Bearer $KEY" $BASE/v1/databases/db-...
```

- 1アカウント **5個**まで。名前は 2〜30 文字の小文字英数字とハイフン（先頭は英字）。
- 接続先は `db-<id>-rw.databases.svc:5432`。アプリの資格情報は `/credentials` で取ります（クラウド側には保存しません）。
- Kubernetes を操作するトークンは Flux が作る ServiceAccount **`databases/cloud-api`**（CNPG Cluster と Secret だけ触れる最小 RBAC）。正本は `platform/sops/k8s.sops.yaml` で、cloud_api ロールが cloud-01 の `secrets/k8s_ca`・`secrets/k8s_token` へ写します。
- 実機確認（2026-09-12）: POST で `db-...` が作られ、`Setting up primary` → `Cluster in healthy state` に遷移、`/credentials` が app の資格情報を返し、DELETE で Cluster も消えることを確認しました。
- **ポータル**の「データベース」画面から、作成・一覧・接続情報の表示・削除ができます。

### 3-21. 関数（Knative）

管理クラウドの「サーバレス実行」です。`POST /v1/functions` が Kubernetes の `functions` namespace に Knative Service を1つ作ります。実体と配置は [Kubernetes クラスタ](kubernetes.md) を参照。

```bash
BASE=https://cloud.apextox.dpdns.org
# 作成（image は OCI イメージ参照）
curl -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"name":"greeter","image":"gcr.io/knative-samples/helloworld-go"}' $BASE/v1/functions
# 一覧・詳細
curl -H "Authorization: Bearer $KEY" $BASE/v1/functions
curl -H "Authorization: Bearer $KEY" $BASE/v1/functions/fn-...
# 削除（Knative Service ごと消える）
curl -X DELETE -H "Authorization: Bearer $KEY" $BASE/v1/functions/fn-...
```

- 1アカウント **10個**まで。名前は 2〜30 文字の小文字英数字とハイフン（先頭は英字）。
- 呼び出し URL は `<name>.functions.k8s.apextox.dpdns.org`（関数は `functions` namespace に作られます）。**HTTPS で叩けます。** Knative の `config-network.external-domain-tls` と `config-certmanager`（`issuerRef: letsencrypt-dns`）が、**namespace ごとにワイルドカード証明書 `*.functions.k8s.apextox.dpdns.org` を1枚だけ**発行します（DNS-01、関数が何個でも証明書は1枚）。使わないときは 0 レプリカまで縮退します。
- Kubernetes を操作するトークンは database と同じ ServiceAccount `databases/cloud-api`（`functions` namespace の Knative Service だけ触れる）。
- 実機確認（2026-09-12）: POST で `fn-...` が作られ、`Provisioning` → `Ready`（URL 発行）に遷移、Kourier 経由で `Hello World!` が返り、DELETE で Service も消えることを確認しました。
- **ポータル**の「関数」画面から、作成・一覧・削除ができます。
