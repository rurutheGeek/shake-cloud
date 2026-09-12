# サービスの置き場所とクラウドVMでの作り方

更新日: 2026-09-12。状態: **方針と手順。新しいサービスはこの形で足す。**

## 方針

**これからのホームラボのサービスは、原則としてクラウドVM（`cloud` プール、VMID 5000–5999）に作ります。** サービスのコードは Git に置き、VM はクラウドAPI（Terraform Provider）で作り、中身は Compose か Kubernetes へ配ります。

例外は**基盤そのもの**です。identity（認証）、cloud-01（クラウドAPI と管理DB）、services-01（NetBox とドキュメント）、storage-s3（Garage）、Kubernetes の各ノードは `platform` プールの基盤VMで、Terraform `10-platform` が作ります。**基盤をクラウドAPIで作ると、「APIを載せる前にAPIが要る」循環になります。** 所有境界は[IaCの所有境界](../architecture/iac.md)を正とします。

**Kubernetes に載せられるものは Kubernetes のままにします。** 常時動く小さなアプリ、DB、関数は Flux（`platform/flux/apps/`）で配ります。VM が要るもの（GPU、独自カーネル、大きなディスク、GUI）をクラウドVMにします。

## リポジトリのどこに置くか

| 置き場所 | 何を置くか | 例 |
| --- | --- | --- |
| `platform/terraform/services/<name>/` | サービスのVM・ディスク・セキュリティグループの宣言（shakecloud Provider）。**サービスごとに1ディレクトリ・1 state** | 新規 |
| `stacks/<name>/` | VM の中で動かすソフト（Compose、`manage.py`、`.env.example`） | `stacks/identity/` |
| `platform/ansible/roles/<name>/` と `platform/ansible/<name>.yml` | VM の中の構成を冪等に適用する場合（任意） | `roles/garage/` |
| `platform/flux/apps/<name>.yaml` | Kubernetes に載せる場合 | `awx.yaml` |
| `platform/terraform/dns.yaml` | LAN の中で名前を付ける場合。`20-dns` が Cloudflare へ書く | `awx`、`cloud` |
| `docs/operations/<name>.md` | 管理者向けの構築・運用 | [identity.md](identity.md) |
| `docs/services/<name>.md` | 利用者向けの使い方 | [usage.md](../services/usage.md) |

### 開発コードはどこに書くか

| 作るもの | 置き場所 | 例 |
| --- | --- | --- |
| VM 1台に載るサービスのコード | **`stacks/<name>/`** | `stacks/identity/`（Compose + `manage.py` + `.env.example` + テスト） |
| 複数コンポーネントの大きなソフト | **トップレベルの専用ディレクトリ** | `cloud/`（API・CLI・Provider・client を1つに） |
| Kubernetes に載せるアプリ | ソースは `stacks/<name>/` か専用ディレクトリ。配備は `platform/flux/apps/<name>.yaml` | [Flux にアプリを足す](flux-apps.md) |
| 使い捨て・補助スクリプト | **`tools/`** | `tools/tf`、`tools/k8s` |
| 設定値の宣言 | `platform/terraform/*.yaml` | `hosts.yaml`、`network.yaml` |

迷ったら「**VM 1台に載る1サービス → `stacks/<name>/`**」「**複数コンポーネント → トップレベル**」で判断します。`stacks/identity/` と同じ形（`init` / `lock` / `up` / `status`）にそろえると、配備と再実行が同じ手順になります。

`hosts.yaml` と `10-platform` は**基盤VM専用**です。サービス用のVMをここへ足さないでください。VMID とプールの境界が崩れ、クラウドAPIの到達範囲（`/pool/cloud` のみ）から外れて管理できなくなります。

## クラウドVMにサービスを作る手順

### 0. 前提

- cloud-01 が動いている（`https://cloud.apextox.dpdns.org/healthz` が 200）。
- アクセスキーをポータルで発行済み。ポータル → アクセスキー、または CLI の `shakecloud access-key create`。
- Provider の dev override を設定済み（[shakecloud Terraform Provider](terraform-provider.md)）。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'
```

### 1. 置き場所を作る

```bash
mkdir -p platform/terraform/services/<name>
```

ひな形の説明は `platform/terraform/services/README.md` にあります。

### 2. VM とリソースを書く

`platform/terraform/services/<name>/main.tf` の例です。SSH とサービスポートを LAN へ開け、SSH鍵を入れ、データディスクを付けた Debian VM を1台作ります。

```hcl
terraform {
  required_providers {
    shakecloud = { source = "ruruthegeek/shakecloud" }
  }
}

provider "shakecloud" {}

resource "shakecloud_key_pair" "service" {
  key_name   = "<name>"
  public_key = file("~/.ssh/id_ed25519.pub")
}

resource "shakecloud_security_group" "service" {
  group_name  = "<name>"
  description = "<name> service"
}

resource "shakecloud_security_group_rule" "ssh" {
  group_id  = shakecloud_security_group.service.id
  direction = "ingress"
  protocol  = "tcp"
  from_port = 22
  to_port   = 22
  cidr      = "192.168.10.0/24"
}

resource "shakecloud_security_group_rule" "web" {
  group_id  = shakecloud_security_group.service.id
  direction = "ingress"
  protocol  = "tcp"
  from_port = 8080
  to_port   = 8080
  cidr      = "192.168.10.0/24"
}

resource "shakecloud_instance" "service" {
  image_id           = "img-debian13"
  instance_type      = "small"          # 近道。vcpus/memory_mib/root_disk_gib を直接書いてもよい
  root_disk_gib      = 20
  key_name           = shakecloud_key_pair.service.key_name
  security_group_ids = [shakecloud_security_group.service.id]
  user_data          = file("${path.module}/cloud-init.yaml")
  tags               = { Name = "<name>" }   # これがゲストのホスト名になる
}

resource "shakecloud_volume" "data" {
  size_gib = 20
  tags     = { Name = "<name>-data" }
}

resource "shakecloud_volume_attachment" "data" {
  volume_id   = shakecloud_volume.data.id
  instance_id = shakecloud_instance.service.id
}

output "address" {
  value = shakecloud_instance.service.private_ip_address
}
```

必要ならバケット・DB・関数も同じモジュールに足せます。例は[shakecloud Terraform Provider](terraform-provider.md)にあります。

```hcl
resource "shakecloud_bucket" "assets" { bucket_name = "<name>-assets" }

resource "shakecloud_database" "app" {
  name        = "<name>"
  storage_gib = 5
}

resource "shakecloud_function" "hook" {
  name  = "<name>-hook"
  image = "ghcr.io/example/<name>-hook:1.0.0"
}
```

### 3. 適用する

```bash
terraform -chdir=platform/terraform/services/<name> init
terraform -chdir=platform/terraform/services/<name> apply
```

- **作成と削除はワーカーが終わるまで待ちます。** `apply` が返った時点で VM は `running` です。
- **state はサービスごとに分けます。** 他のモジュールと共有しません。
- 消すときは `terraform destroy`。VM と IP は API の管理下で片付きます。
- state の置き場（各作業機か、R2/Garage へ寄せるか）は未決です。**秘密値は state に平文で入り得ます**（[Terraformの実行](terraform.md)）。

### 4. ソフトを配備する

`user_data`（cloud-init）で、ユーザー・パッケージ・Docker など最小限を最初に整えます。ソフト本体は `stacks/<name>/` に置き、VM へコピーして Compose で起動します。`stacks/identity/manage.py` と同じ「init / lock / up / status」の形にすると再実行が楽です。

```bash
scp -r stacks/<name> debian@<address>:/tmp/
ssh debian@<address> 'sudo install -d -m 750 /opt/<name> \
  && sudo cp -a /tmp/<name>/. /opt/<name>/ \
  && cd /opt/<name> && sudo python3 manage.py init && sudo python3 manage.py up'
```

秘密は `.env`（VM 上 0600）へ、または SOPS から写します。**Git へ入れません。**

### 5. 名前を付ける（任意）

`*.apextox.dpdns.org` の名前は `platform/terraform/dns.yaml` に書き、`20-dns` を適用します。ただし Caddy が中継するのは基盤VM上の `tls_proxy` です。クラウドVMへ名前を付ける場合は、その IP へ A レコードを向け、TLS は VM 上で終端します。**現時点でクラウドVMへの DNS 自動登録はありません。**

### 6. ドキュメントを足す

`docs/operations/<name>.md`（管理者）と `docs/services/<name>.md`（利用者）を書き、`mkdocs.yml` のナビへ入れます。URL は[接続先一覧](urls.md)へ追記します。

## 決まりごと

- **state はサービスごとに分ける。** 共有すると、片方の削除がもう片方の現状把握を壊します。
- **秘密値を Provider で作らない。** S3キーとDB資格情報は作成時に一度だけ返る値で、state に置くと漏れます。ポータルか CLI で発行します（`shakecloud s3-key create`・`shakecloud database credentials`）。
- **サイズは自由入力。** `instance_type` は値を埋める近道です。`vcpus`・`memory_mib`・`memory_min_mib`・`ballooning`・`root_disk_gib` を直接書けます。
- **`tags.Name` がゲストのホスト名。** 変えると VM は作り直されます。
- **削除は `terraform destroy`。** 基盤VM（`hosts.yaml`）とサービスVM（`cloud` プール）を混ぜません。

## まだ無いもの

- クラウドVMを Ansible の動的インベントリに載せる仕組み。API は NetBox に**IPアドレス**を登録しますが、デバイス/VM としては登録しないため、Ansible から自動では見えません。今は cloud-init と手動の SSH で配ります。
- クラウドVMへの DNS 自動登録。
- サービス用 state の共有の置き場（R2/Garage）。
