# 運用ドキュメント

このディレクトリは、設定変数の一覧ではなく「何をしたいときに、どこを変更し、何が起きるか」を説明するための日本語ドキュメントです。

## サービス別

- [Nextcloudと追加アプリ](services/nextcloud.md)
- [Vaultwarden](services/vaultwarden.md)
- [SSOの設計](services/sso.md)

## 作業別

- [秘密値の管理（SOPS + age）](operations/secrets.md)
- [Terraformの実行](operations/terraform.md)
- [SMTPとメール送信](operations/smtp.md)

## 基盤

Proxmox VE 上への展開は[IaCの所有境界](architecture/iac.md)と[Proxmox導入後の手順](architecture/bring-up.md)を先に読みます。誰が何を作るか（Terraform / Ansible / Flux / 将来のクラウドAPI）と、VMIDとプールの分割が書いてあります。

## まず理解すること

- Composeはサービス本体、管理画面はアプリ内の状態、Ansibleは配備と初期設定を主に管理します。
- Proxmox上のVMとNetBoxの台帳はTerraformが作ります。ゲストOSの中はAnsibleです。境界は[IaCの所有境界](architecture/iac.md)を正とします。
- Nextcloudのユーザー・グループ権限は、KavitaやNavidromeへ自動では伝わりません。
- 秘密値はこのドキュメントへ書かず、`.env`または`secrets/`などGit管理外へ置きます。
- 変更前にバックアップを取得し、変更後にログイン・閲覧・再生・同期を確認します。

## 現在の構成でできること

| 目的 | 主な手段 | まだ追加が必要なもの |
| --- | --- | --- |
| 一つの入口からサービスを開く | Homarrなどのポータル | ポータル用ComposeサービスとCaddyのホスト名 |
| 一つのアカウントでログインする | AuthentikなどのOIDCプロバイダー | IdP、各アプリのOIDC設定、ユーザー移行 |
| PDFを家族・技術書などに分けて公開する | NextcloudのグループとKavitaのライブラリ | 両サービスで個別に権限設定 |
| 招待・確認メールを送る | 外部SMTPリレーまたはローカルsendmail | SMTPサービスとDNS・送信者設定 |
| 配備先を増やす | NetBoxの対象追加とAnsible | ホストごとの接続・容量・バックアップ設計 |
| VMを増やす | `platform/terraform/hosts.yaml` への追記とTerraform | 実機のストレージ名・bridge名・IP枠の確定（棚卸し） |
| 開発用のVMを渡す | Proxmoxのプールとロール、[開発VMの使い方](services/devvm.md) | 宅外から使うためのVPN |

## ドキュメントの書き方

新しいページは次の順で書きます。

1. 何ができるか
2. どの利用者に影響するか
3. 設定場所
4. 具体的な入力例
5. 変更後の確認方法
6. 元に戻す方法と注意点
