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

現在のユニットは [media](media/README.md)（media-01。**apply済み・実機確認済み**。I02）と `monitor/`（monitor-01。監視スタック。M01）、`net/`（net-01。Tailscale subnet router。N02）です。media-01 の Terraform 一式は `terraform validate` に加えて、実機へ apply して再 plan が No changes になることまで確認しています。監視スタックの仕様は [M01](../../../docs/development/M01-monitoring.md) を参照してください。
