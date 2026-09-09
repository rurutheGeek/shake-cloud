# Terraformの実行手順

更新日: 2026-09-09。状態: **00-bootstrapのみ実装済み。実機での適用は未実施**。

所有境界の設計は[IaCの所有境界](../architecture/iac.md)を参照してください。ここでは実行方法とstateの扱いを書きます。

## 1. 何ができるか

Proxmoxのプール・ロール・自動化ユーザー・ACLを宣言的に作ります。GUIで作った権限設定と違い、差分がGitに残り、再実行しても同じ状態になります。

これはVMを作る段階ではありません。VMの作成は `10-platform`（未実装）です。

## 2. どの利用者に影響するか

管理者だけです。ここで作る `dev-a@pve` / `dev-b@pve` は開発VMの利用者アカウントですが、**パスワードはTerraformで管理しません**。作成後に本人がGUIまたは `pveum passwd dev-a@pve` で設定します。stateへ秘密値を増やさないためです。

## 3. 設定場所

| 対象 | 場所 |
| --- | --- |
| ルートモジュール | `platform/terraform/00-bootstrap/` |
| プールとVMID範囲 | `pools.tf` |
| ロールの権限 | `variables.tf`。PVEの版に合わせて上書きできる |
| 接続情報 | `platform/sops/proxmox-root.sops.yaml`（暗号化） |
| state | S3互換ストレージの `shake-cloud/00-bootstrap/terraform.tfstate` |
| stateの保管先と資格情報 | `platform/sops/s3.sops.yaml`（暗号化） |

## 4. 具体的な入力例

準備は3つです。実機の値は[Proxmox導入後の手順](../architecture/bring-up.md)の棚卸しから取ります。

**手動で1回だけ**、PVEのGUI（データセンター → 権限 → APIトークン）で `root@pam` のトークンを作ります。「特権の分離」のチェックを外します。これがこの構成で唯一の手作業です。ここで作る `terraform@pve` は自分自身を作れないため、1段だけ上位の資格情報が要ります。

```bash
cp platform/sops/proxmox-root.sops.yaml.example platform/sops/proxmox-root.sops.yaml
# エンドポイントとトークンを実値へ編集
sops --encrypt --in-place platform/sops/proxmox-root.sops.yaml
```

適用します。先に `plan` で作られるものを確認します。

```bash
sops exec-env platform/sops/proxmox-root.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap init'

sops exec-env platform/sops/proxmox-root.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap plan'

sops exec-env platform/sops/proxmox-root.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap apply'
```

自動化トークンの秘密値を取り出し、そのままSOPSへ入れます。

```bash
cp platform/sops/proxmox.sops.yaml.example platform/sops/proxmox.sops.yaml
terraform -chdir=platform/terraform/00-bootstrap output -raw automation_token_value
# 出力は user@realm!id=uuid の完全な形。PROXMOX_VE_API_TOKEN へそのまま入れる。
# automation_token_id を接頭辞として足すと二重になり、API が 401 を返す。
sops --encrypt --in-place platform/sops/proxmox.sops.yaml
```

以降の `10-platform` は `proxmox.sops.yaml` を使い、rootトークンは使いません。

### stateを外部のS3互換ストレージへ置く（初回のみ）

K11は単一SSDです。そこにstateを置くと、ディスク1枚の故障で「Terraformが現状を把握できない」状態になり、手で作り直すことになります。K11が停止中でもstateを読めるべきでもあります。そこでK11の外にあるS3互換ストレージへ置きます。

**特定の事業者に縛られない形にしています。** `backend "s3"` に書くのはS3の標準的な設定だけで、`AWS_*` はAWS SDK・Terraform・aws-cli・rclone・mcが共通で読む名前です。現在の実体はCloudflare R2ですが、[cloud.md](../architecture/cloud.md)が計画しているGarageや、MinIO・SeaweedFSへ移すときも、変えるのは `AWS_ENDPOINT_URL_S3` と `TF_STATE_BUCKET` だけです。

権限は**対象バケットのオブジェクト読み書きだけ**に絞ります。アカウント全体の管理権限は要りません。

```bash
cp platform/sops/s3.sops.yaml.example platform/sops/s3.sops.yaml
# バケット名・エンドポイント・鍵を実値へ
sops --encrypt --in-place platform/sops/s3.sops.yaml
```

すでにローカルのstateがある場合は移行します。`tools/tf` がbucketを渡すので、`-migrate-state` を足すだけです。

```bash
tools/tf 00-bootstrap init -migrate-state
tools/tf 05-seed      init -migrate-state
tools/tf 10-platform  init -migrate-state
```

プロンプトに `yes` と答えると、ローカルの `terraform.tfstate` がR2へコピーされます。以降はR2上のstateが正です。移行後、手元に残った `terraform.tfstate` は削除して構いませんが、**移行が成功したことを `plan` で確かめてから**にします。

`use_lockfile = true` はTerraform 1.10以降のS3ネイティブなロックです。条件付き書き込み（If-None-Match）を使うため、DynamoDBのような事業者固有の仕組みは要りません。保管先が条件付き書き込みに対応していない場合はこの行を外します。

### 実行はラッパー経由で

`tools/tf` がSOPSから資格情報を環境変数として渡します。復号した値をファイルへ書き出しません。

```bash
tools/tf 00-bootstrap plan     # stateの保管先 ＋ Proxmox の root@pam
tools/tf 05-seed      apply    # stateの保管先 ＋ Proxmox の terraform@pve
tools/tf 10-platform  plan     # 上記 ＋ NetBox
```

`10-platform` はNetBoxへ到達する必要があります。NetBoxは `services-01` のlocalhostにしか出ていないので、SSHポート転送を張ってから実行します。

```bash
ssh -N -L 8001:127.0.0.1:8000 debian@<services-01のIP>
```

## 5. 変更後の確認方法

**2回目の `apply` で `No changes` になることが合格条件です。** 冪等でない場合、GUIでの手変更かProxmox側の既定値との差があります。

権限の分離も実際に確認します。`terraform@pve` のトークンで `cloud` プールのVMを作ろうとして拒否されること、`dev-a@pve` から相手のVMが見えないことを確かめます。設定しただけで到達できないとは扱いません。

```bash
terraform -chdir=platform/terraform/00-bootstrap plan   # No changes になること
terraform -chdir=platform/terraform/00-bootstrap output vmid_ranges
```

CIでは `terraform fmt -check` と `terraform validate` が走ります。実機への接続は行いません。

## 6. 元に戻す方法と注意点

- **stateには秘密値が平文で入ります。** `sensitive` 指定は表示を隠すだけで、暗号化ではありません。バケットを公開せず、アクセスキーを対象バケットの読み書きだけに絞ります。SOPSはstateを守りません。
- `terraform destroy` はプール・ロール・ユーザーを消します。**VMが所属しているプールを消す前に、VMの所属を確認してください。** プールの削除はVMを消しませんが、ACLが外れて到達できなくなります。
- **ロールの権限名はPVEの版に依存します。** 存在しない権限を1つでも含むと、ロールの作成が `HTTP 400 invalid privilege '...'` で失敗します。棚卸し（`survey-pve.yml`）が `pveum role list` を取得するので、そこで実機の名前を確認して `platform_admin_privileges` を上書きします。既定値は PVE 9.2 で確認済みです。実例として **`VM.Monitor` は PVE 9 で廃止**されており、bridge の割り当てには `SDN.Use`、guest agent 経由のIP取得には `VM.GuestAgent.Audit` が要ります。
- `apply` が権限エラーで止まる場合、必要なACLのパスが実機の版で異なる可能性があります。エラーに出たパスを `identities.tf` へ追加し、**広い範囲へ丸ごと許可しないでください**。
- stateを失うと、Terraformは既存オブジェクトを「無い」と判断して作り直そうとします。復旧には `terraform import` が要ります。stateもバックアップ対象です。
