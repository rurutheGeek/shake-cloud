# 運用ドキュメント

このディレクトリは、設定変数の一覧ではなく「何をしたいときに、どこを変更し、何が起きるか」を説明するための日本語ドキュメントです。**どのサービスがどこにあるかは、まず[接続先一覧](operations/urls.md)を見てください。**

## 新しい基盤（Proxmox・Kubernetes・クラウド・identity）

| 目的 | 文書 |
| --- | --- |
| どこに何があるか知る | [接続先一覧（URL・アドレス）](operations/urls.md) |
| サービスを載せるVMをクラウドに作る | [サービスの置き場所とクラウドVMでの作り方](operations/services.md) |
| 共通アカウントを運用する（招待・復旧・パスキー） | [認証基盤（identity・Authentik）](operations/identity.md) |
| クラウドを使う（ポータル・CLI・Terraform） | [クラウドの使い方](services/cloud.md)・[CLI](operations/cli.md)・[Terraform Provider](operations/terraform-provider.md) |
| クラウドAPI を配備・運用する | [クラウドAPIの構築](operations/cloud.md) |
| Kubernetes を運用する | [Kubernetes クラスタ](operations/kubernetes.md)・[Flux にアプリを足す](operations/flux-apps.md) |
| AWX を使う | [AWX の使い方](operations/awx.md) |
| NetBox（台帳）を使う | [NetBox の使い方](operations/netbox.md) |
| S3 互換ストレージを使う | [Garage（S3互換ストレージ）](operations/garage.md) |
| Windows の VM を作る | [Windows 11 ProのVMを作る](operations/windows.md) |
| VLAN 分離へ切り替える | [VLAN 分離への切替](operations/vlan.md) |
| 電源を安全に切る・UPS を入れる | [電源とUPS](operations/power.md) |

## メディア系（旧スタック）

- [共通ログイン（旧メディア）](services/sso.md)（**新しい認証基盤とは別物**）
- [Nextcloudと追加アプリ](services/nextcloud.md)
- [Vaultwarden](services/vaultwarden.md)
- [ハブ運用](operations/hub.md)
- [Nextcloud権限変更](operations/nextcloud-permissions.md)
- [音楽の取り込み](services/music.md)
- [Homarrハブ](services/homarr.md)
- [日本語表示](services/language.md)
- [ディスク増設](operations/disk.md)

## 作業別

- [秘密値の管理（SOPS + age）](operations/secrets.md)
- [Terraformの実行](operations/terraform.md)
- [SMTPとメール送信](operations/smtp.md)
- [初回セットアップの順番](operations/bootstrap.md)
- [クラウド開発の引き継ぎとTODO](operations/handover.md)（**進捗の正本**）

## 基盤

Proxmox VE 上への展開は[IaCの所有境界](architecture/iac.md)と[Proxmox導入後の手順](architecture/bring-up.md)を先に読みます。誰が何を作るか（Terraform / Ansible / Flux / クラウドAPI）と、VMIDとプールの分割が書いてあります。

## まず理解すること

- Composeはサービス本体、管理画面はアプリ内の状態、Ansibleは配備と初期設定を主に管理します。
- Proxmox上のVMとNetBoxの台帳はTerraformが作ります。ゲストOSの中はAnsibleです。境界は[IaCの所有境界](architecture/iac.md)を正とします。
- **これからのサービスは原則クラウドVM（`cloud` プール、VMID 5000–5999）に作ります。** 基盤そのものだけが `platform` プールの基盤VMです（[サービスの置き場所](operations/services.md)）。
- **コードで管理できるものはすべてコードにします。** 手順書に一度きりのGUI操作を書いて済ませません。残っている手作業は[初回セットアップの順番](operations/bootstrap.md)に理由付きで列挙してあります。
- 秘密値はこのドキュメントへ書かず、`.env`または`secrets/`などGit管理外へ置きます。
- 変更前にバックアップを取得し、変更後にログイン・閲覧・再生・同期を確認します。

## ドキュメントの書き方

新しいページは次の順で書きます。

1. 何ができるか
2. どの利用者に影響するか
3. 設定場所
4. 具体的な入力例
5. 変更後の確認方法
6. 元に戻す方法と注意点
