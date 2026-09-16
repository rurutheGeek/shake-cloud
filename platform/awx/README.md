# platform/awx

AWX 24.6.1 は **kubeadm の Kubernetes へ Flux で配備済み**です（2026-09-12）。
入口は `https://awx.apextox.dpdns.org`、使い方と管理者の入口は
[docs/operations/kubernetes.md](../../docs/operations/kubernetes.md) と
[docs/operations/awx.md](../../docs/operations/awx.md) を参照してください。
**このディレクトリの設定例（EE・Project・Job Template 登録）はまだ実 API へ適用していません。**

| ファイル | 内容 |
| --- | --- |
| `execution-environment.yml` | Python 3.11 と NetBox の Python 依存を含むカスタム EE の定義 |
| `configure.yml` | EE・Project・Credential Type/Credential・Inventory Source・Job Template を登録する |
| `controller.example.yml` | Git URL・ブランチ・EE イメージの設定例 |
| `job-vars.example.yml` | HTTPS 公開時の Extra Variables 例 |

## 適用するときの手順

1. AWX へ管理者でログインする（本体は配備済み。[AWXの使い方](../../docs/operations/awx.md)）。
2. `execution-environment.yml` を使って EE をビルドし、利用するレジストリへ push する。例: このディレクトリで `ansible-builder build -f execution-environment.yml -t ghcr.io/YOUR_ORG/media-stack-ee:1`。その後 Docker/Podman で push する。
3. AWX で「Media hosts SSH」という Machine Credential を作成する。SSH 鍵、接続ユーザー、sudo 設定を登録する。必要なら Git 用 Source Control Credential も作成する。
4. `controller.example.yml` を `controller.yml` へコピーし、Git URL、ブランチ、EE イメージ（digest 推奨）を設定する。
5. `CONTROLLER_HOST`、`CONTROLLER_OAUTH_TOKEN`、`NETBOX_API`、`NETBOX_TOKEN` を管理端末の環境変数に設定し、`ansible-playbook awx/configure.yml -e @awx/controller.yml` をリポジトリ直下で実行する。
6. NetBox 同期結果を確認し「Deploy portable services」を起動する。対象は Limit で指定する。

`configure.yml` は EE、Project、NetBox 専用 Credential Type/Credential、SCM Inventory Source、Job Template を登録します。配備ジョブ自体は起動しません。NetBox のトークンは Inventory 同期にだけ渡し、アプリ配備ジョブへは渡しません。SSH ホスト鍵は通常の Ansible 検証を維持します。AWX の Machine Credential で既知ホストの管理方針を整備してください。

**この設定例は未適用のため実 API での確認は未実施です。** AWX 本体の DB・Secret・PVC のバックアップは、アプリ用バックアップとは別に構成する必要があります。
