# platform/terraform/services

**ホームラボのサービスを載せるクラウドVMの宣言を置く場所です。** 1サービスにつき
1ディレクトリ・1 state（例: `play/`、`photos/`）。ここは基盤VM用ではありません。
基盤VMは `platform/terraform/hosts.yaml` と `10-platform` が持ちます。

サービスのVM・ディスク・セキュリティグループは、自作クラウドAPIの
`shakecloud` Provider（dev override）で作ります。

- 方針と手順: [docs/operations/services.md](../../../docs/operations/services.md)
- Providerの使い方: [docs/operations/terraform-provider.md](../../../docs/operations/terraform-provider.md)
- 所有境界: [docs/architecture/iac.md](../../../docs/architecture/iac.md)

`terraform.tfstate` と `*.tfvars` はコミットしません。**state には秘密値が
平文で入り得ます。**

現在の開発入口は[media](media/README.md)、作業仕様は[I02](../../../docs/development/I02-media-vm.md)です。media-01 の Terraform 一式は実装済みで、`terraform validate` まで確認しています（**未apply**）。
