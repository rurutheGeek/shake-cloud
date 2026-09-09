# platform/terraform

Proxmox VE と NetBox を宣言的に扱う。所有境界の設計は
[docs/architecture/iac.md](../../docs/architecture/iac.md)、実行手順は
[docs/operations/terraform.md](../../docs/operations/terraform.md) を参照する。

| ルートモジュール | 役割 | 実行に使う資格情報 | 状態 |
| --- | --- | --- | --- |
| `state-store/` | 他のモジュールが使う state 置き場（R2バケット）。**stateはローカル**（循環を避けるため） | Cloudflare APIトークン | 実装済み |
| `00-bootstrap/` | プール、ロール、ユーザー、ACL、cloud imageの取得、開発VMのAPIトークン | `root@pam`（`platform/sops/proxmox-root.sops.yaml`） | 実装済み |
| `05-seed/` | NetBoxを載せる最初の1台。**NetBoxを使わず静的IP**で作る | `terraform@pve` | 実装済み・適用済み |
| `10-platform/` | NetBoxの台帳とProxmoxのVM | `terraform@pve` と NetBox書き込みトークン | 実装済み・実機未適用 |
| `modules/managed-host/` | NetBoxのVM＋採番とProxmoxのVMを1組で作る | — | 実装済み |

宣言はYAMLに置く。`.tf` は機構だけを持つ。

| ファイル | 内容 |
| --- | --- |
| `pools.yaml` | プールとVMID範囲。`00-bootstrap` と `10-platform` の両方が読む |
| `flavors.yaml` | VMのサイズ。名前は将来のクラウドAPIと共用 |
| `tags.yaml` | NetBoxタグとAnsibleグループの対応 |
| `hosts.yaml` | ホストの宣言。**正本** |

整合は `tests/test_platform_inventory.py` が検査する。

秘密値は SOPS 経由の環境変数で渡す。tfvars にも HCL にも書かない。

```bash
sops exec-env platform/sops/proxmox-root.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap plan'
```

`.terraform.lock.hcl` は provider の版を固定するため追跡する。
`terraform.tfstate` と `*.tfvars` は `.gitignore` 対象で、**state には
秘密値が平文で入る**。取り扱いは上記の運用手順に従う。
