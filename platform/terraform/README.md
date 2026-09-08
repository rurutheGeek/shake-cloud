# platform/terraform

Proxmox VE と NetBox を宣言的に扱う。所有境界の設計は
[docs/architecture/iac.md](../../docs/architecture/iac.md)、実行手順は
[docs/operations/terraform.md](../../docs/operations/terraform.md) を参照する。

| ルートモジュール | 役割 | 実行に使う資格情報 | 状態 |
| --- | --- | --- | --- |
| `00-bootstrap/` | プール、ロール、自動化ユーザー、ACL | `root@pam`（`platform/sops/proxmox-root.sops.yaml`） | 実装済み |
| `10-platform/` | NetBoxの台帳とProxmoxのVM | `terraform@pve`（`platform/sops/proxmox.sops.yaml`） | 未実装 |

秘密値は SOPS 経由の環境変数で渡す。tfvars にも HCL にも書かない。

```bash
sops exec-env platform/sops/proxmox-root.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap plan'
```

`.terraform.lock.hcl` は provider の版を固定するため追跡する。
`terraform.tfstate` と `*.tfvars` は `.gitignore` 対象で、**state には
秘密値が平文で入る**。取り扱いは上記の運用手順に従う。
