AWX本体の構築は今回は対象外です。将来構築する場合は **kubeadmで作成したKubernetes** にAWX Operatorを配置します。K3s用の構築処理は含めません。

今は ../ansible/inventory.netbox.yml と ../ansible/deploy.yml をCLIから実行できます。後で同じGitリポジトリをAWX Projectに登録して利用します。

将来の移行手順:
1. kubeadm基盤とAWX Operator/AWXを構築し、AWXへ管理者でログイン。
2. execution-environment.ymlを使ってEEをビルドし、利用するレジストリへpush。例: このディレクトリで `ansible-builder build -f execution-environment.yml -t ghcr.io/YOUR_ORG/media-stack-ee:1`。その後Docker/Podmanでpush。Python 3.11を含むカスタムEEなので、NetBoxのPython依存もジョブ内で利用できます。
3. AWXで「Media hosts SSH」というMachine Credentialを作成。SSH鍵、接続ユーザー、sudo設定を登録。必要ならGit用Source Control Credentialも作成。
4. controller.example.ymlをcontroller.ymlへコピーしGit URL、ブランチ、EEイメージ（digest推奨）を設定。
5. CONTROLLER_HOST、CONTROLLER_OAUTH_TOKEN、NETBOX_API、NETBOX_TOKENを管理端末の環境変数に設定。`ansible-playbook awx/configure.yml -e @awx/controller.yml` をリポジトリ直下で実行。
6. NetBox同期結果を確認し「Deploy portable services」を起動。対象はLimitで指定。HTTPS公開時のExtra Variables例はjob-vars.example.yml。

configure.ymlはEE、Project、NetBox専用Credential Type/Credential、SCM Inventory Source、Job Templateを登録します。配備ジョブ自体は起動しません。NetBoxのトークンはInventory同期にだけ渡し、アプリ配備ジョブへは渡しません。SSHホスト鍵は通常のAnsible検証を維持します。AWXのMachine Credentialで既知ホストの管理方針を整備してください。

このAWX設定例は未稼働のため実APIでの確認は未実施です。AWX本体のDB・Secret・PVCのバックアップは、今回のアプリ用バックアップとは別に構成する必要があります。
