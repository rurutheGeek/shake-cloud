# shakecloud Terraform Provider

更新日: 2026-09-12。状態: **実装済み・実機で確認済み**（`cloud/provider`、SDKは `terraform-plugin-framework`）。

**自作クラウドAPIを Terraform から扱う Provider です。** 語彙と状態遷移は EC2 に揃えていますが、**ワイヤ互換ではありません**（SigV4 でも本物の `hashicorp/aws` でもありません）。`aws_instance` を書ける人がそのまま書けることを狙っています。

## 1. ビルドとインストール

まだ Terraform Registry には公開していないので、**dev override** で手元のバイナリを指します。

```bash
cd cloud/provider
go build -o ~/.terraform.d/plugins/terraform-provider-shakecloud .
```

`~/.terraformrc`（または `TF_CLI_CONFIG_FILE` が指すファイル）:

```hcl
provider_installation {
  dev_overrides {
    "registry.terraform.io/ruruthegeek/shakecloud" = "/home/<you>/.terraform.d/plugins"
  }
  direct {}
}
```

`dev_overrides` のときは `terraform init` が Provider を取得しません（`terraform apply` をそのまま実行できます）。`terraform init` を走らせると警告が出ますが無害です。

## 2. 認証

アクセスキーは**ポータルで発行**します。環境変数から読みます。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'
export SHAKECLOUD_ENDPOINT='https://cloud.apextox.dpdns.org'   # 既定と同じなら不要
```

```hcl
terraform {
  required_providers {
    shakecloud = {
      source = "ruruthegeek/shakecloud"
    }
  }
}

provider "shakecloud" {
  # endpoint と access_key は省略すると上の環境変数を使います。
}
```

## 3. 使えるもの

| リソース | AWSの対応物 | 何をする |
| --- | --- | --- |
| `shakecloud_instance` | `aws_instance` | VMの作成・電源・サイズ変更・削除。`tags.Name` がゲストのホスト名 |
| `shakecloud_volume` | `aws_ebs_volume` | 追加ディスク。拡張はできるが縮小は不可 |
| `shakecloud_volume_attachment` | `aws_volume_attachment` | ボリュームをインスタンスへ接続 |
| `shakecloud_security_group` | `aws_security_group` | ルールの入れ物 |
| `shakecloud_security_group_rule` | `aws_security_group_rule` | 受信/送信ルールを1つずつ |
| `shakecloud_key_pair` | `aws_key_pair` | SSH公開鍵の登録 |
| `shakecloud_image` | `aws_ami`（自作） | ローカルのディスクイメージをアップロード。`.qcow2`/`.raw`/`.img`/`.vmdk`、既定12GiBまで |
| `shakecloud_database` | `aws_db_instance` | PostgreSQL（CloudNativePG）。`name`・`storage_gib` で作る。資格情報は state に置かない |
| `shakecloud_bucket` | `aws_s3_bucket` | S3バケット（Garage）。オブジェクト本体はAPIを通らない |

データソース:

| データソース | 何が分かるか |
| --- | --- |
| `shakecloud_caller_identity` | キーの持ち主（`account_id`・`username`・`is_admin`） |

**サイズは自由入力です。** `instance_type` は値を埋めるだけの近道で、`vcpus`・`memory_mib`・`memory_min_mib`・`ballooning`・`root_disk_gib` を直接指定できます。指定した値はAPIが決めた実値で読み戻されます。

## 4. 例

```hcl
provider "shakecloud" {}

data "shakecloud_caller_identity" "me" {}

resource "shakecloud_key_pair" "me" {
  key_name   = "me"
  public_key = file("~/.ssh/id_ed25519.pub")
}

resource "shakecloud_security_group" "ssh" {
  group_name  = "ssh"
  description = "allow SSH from the LAN"
}

resource "shakecloud_security_group_rule" "ssh" {
  group_id  = shakecloud_security_group.ssh.id
  direction = "ingress"
  protocol  = "tcp"
  from_port = 22
  to_port   = 22
  cidr      = "192.168.10.0/24"
}

resource "shakecloud_instance" "dev" {
  image_id         = "img-debian13"
  instance_type    = "small"
  root_disk_gib    = 20
  key_name         = shakecloud_key_pair.me.key_name
  security_group_ids = [shakecloud_security_group.ssh.id]
  user_data        = file("cloud-init.yaml")
  tags             = { Name = "dev" }
}

resource "shakecloud_volume" "data" {
  size_gib = 20
  tags     = { Name = "data" }
}

resource "shakecloud_volume_attachment" "data" {
  volume_id   = shakecloud_volume.data.id
  instance_id = shakecloud_instance.dev.id
}

resource "shakecloud_bucket" "photos" {
  bucket_name = "photos"
}

resource "shakecloud_database" "shop" {
  name        = "shop"
  storage_gib = 5
}

# 自分のディスクイメージを上げて、そこから起動する。
resource "shakecloud_image" "custom" {
  name = "custom-debian"
  file = "images/custom.qcow2"   # .qcow2/.raw/.img/.vmdk、既定12GiBまで
}

resource "shakecloud_instance" "from_custom" {
  image_id         = shakecloud_image.custom.id
  instance_type    = "small"
  key_name         = shakecloud_key_pair.me.key_name
  security_group_ids = [shakecloud_security_group.ssh.id]
  tags             = { Name = "from-custom" }
}
```

`shakecloud_instance` の作成と削除は、ワーカーが終わるまで**待ちます**。`terraform apply` が終わった時点で `running`（または `terminated`）です。

**S3キーは Provider で作りません。** 作成時にだけ秘密値が返り、それを state に置くと漏れるためです。鍵はポータルか `shakecloud s3-key create` で発行し、バケットへの権限もそちらで付けます（`shakecloud bucket allow`）。Terraform はバケットそのものと、その `s3_endpoint`・`s3_region` を持ちます。

**データベースの資格情報も Provider で扱いません。** CloudNativePG が作る Kubernetes Secret にあり、`shakecloud database credentials` かポータルで読みます。Terraform は `database_id`・`host`・`port`・`status` などだけを持ちます。

## 5. 実装の約束

- **Create/Read/Update/Delete/Import を備えます。** `terraform import shakecloud_instance.dev i-...` のように取り込めます。`shakecloud_security_group_rule` だけは `GROUP_ID/RULE_ID` の形で取り込みます。`user_data` や `image.file` のような**作成時だけの入力は API から読めない**ので、import 後の plan では作り直しになります。
- **非同期を待ちます。** 作成・削除・アタッチはAPIのワーカーが後で行うので、Providerが状態を確認してから返します。
- **権限エラーを「削除済み」と誤認しません。** 403 はそのままエラーにし、404 のときだけ state から外します。
- **タグに更新APIはありません。** `tags` を変えるとリソースは作り直されます（`RequiresReplace`）。同じく `name` 相当は `tags.Name` です（`aws_instance` と同じ）。
- **イメージのファイルは作成時に送ります。** `file` はローカルのパスで、`name` と同じく変えると作り直しです（`RequiresReplace`）。アップロード済みのイメージだけを管理し、Terraform の `images.yaml` で宣言した共有イメージは API から削除できません（409。`import` で読むことはできます）。
- ルールは差分適用ではなく**入れ替え**です。APIが1つずつ追加・削除する形なので、`shakecloud_security_group_rule` を1ルール1リソースにしています。

## 6. 確認のしかた

```bash
cd cloud/provider && go vet ./... && go test ./...
```

実機での確認（2026-09-11）: dev override で `terraform apply` し、`shakecloud_key_pair`・`shakecloud_security_group`・`shakecloud_security_group_rule`・`shakecloud_volume`・`shakecloud_bucket` を作成、`data.shakecloud_caller_identity` を読み、再 plan が **No changes**、SG と バケットを `terraform import` して再 plan も **No changes**、最後に `terraform destroy` で残骸なし、を確認しました。

実機での確認（2026-09-12）: `shakecloud_image` を dev override で `apply` し、`img-...`（`format=raw`・`size_mib=1`・`state=available`）が作成され、再 plan が **No changes**、`terraform destroy` で消えることを確認しました。

実機での確認（2026-09-12）: `shakecloud_database` を apply し、`db-...`（CloudNativePG Cluster）が作成され、再 plan が **No changes**、`terraform destroy` で消えることを確認しました。
