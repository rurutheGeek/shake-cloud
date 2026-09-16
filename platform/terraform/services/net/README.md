# net-01 のVM宣言

状態: **2026-09-14 作成**。Tailscale の subnet router 専用VM（`cloud` プール）。
LAN の管理経路を K11 の外に残す計画（[N02](../../../../docs/development/N02-tailscale.md)）の
VM 版で、ラズパイを導入しない間の復旧経路。ゲーム・メディアとは役割を混ぜない。

ラズパイとの違いは**ホスト障害に巻き込まれること**。Proxmox ホスト（K11）が
落ちればこの VM も落ちるので、復旧経路としては VM 単位の故障までしか
カバーしない。真のアウトオブバンドが必要になったら、既存ルーターの VPN 機能
か別ハードを検討する（[VPN比較](../../../../docs/architecture/vpn.md)）。

## この state が作るもの

| リソース | 内容 |
| --- | --- |
| `shakecloud_key_pair.net` | `ssh_public_key_path` の公開鍵を cloud API へ登録 |
| `shakecloud_security_group.net` | LAN から 22/tcp だけ許可 |
| `shakecloud_instance.net` | `img-debian13` から 1vCPU／512MiB／OS10GiB。`tags.Name` が `net-01` |

cloud-init はユーザー・qemu-guest-agent・SSH・IPv6無効化だけを行う。
Tailscale の導入と tailnet への登録は `platform/ansible/net.yml` が行う。
**認証キーは state に残る `user_data` へ入れない。**

## 実行

```bash
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'

tools/tf services/net init   # リポジトリのルートで実行
tools/tf services/net plan
tools/tf services/net apply
```

state のキーは `shake-cloud/services/net/terraform.tfstate`。`init` はキー無しでも
通るが、`plan`・`apply` は `SHAKECLOUD_ACCESS_KEY`（`platform/sops/services.sops.yaml`）
が無ければ止まる。

## 検証

```bash
terraform -chdir=platform/terraform/services/net fmt -check
terraform -chdir=platform/terraform/services/net validate   # dev override が必要
```
