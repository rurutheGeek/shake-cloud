---
title: クラウドの使い方（ポータル・CLI・Terraform）
updated: 2026-09-23
section: 利用ガイド
audience: 利用者
tags:
  - guide
  - cloud
---

# クラウドの使い方（ポータル・CLI・Terraform）

> **更新日** 2026-09-23 ・ **区分** 利用ガイド ・ **読む人** 利用者

**状態**: 4機能（VM・S3・database・function）実装済み・実機確認済み。

クラウドは Proxmox の上に次を払い出す仕組みです。入口は**ポータル（ブラウザ）・CLI・Terraform Provider**の3つで、裏の API は同じです。このほか、AIエージェントから参照だけを許す**読み取り専用のMCPサーバ**（[管理者向け手順](../operations/mcp.md)）があります。

| 機能 | 何が作れる |
| --- | --- |
| インスタンス | VM。電源の入切、ブラウザからのコンソール、サイズ変更、削除 |
| ボリューム | インスタンスに足す追加ディスク。拡大はできるが縮小はできない |
| セキュリティグループ | インスタンスの受信・送信ルール |
| バケット | S3互換のバケットとアクセスキー（Garage） |
| データベース | PostgreSQL（CloudNativePG） |
| 関数 | HTTPで呼ぶサーバレス実行（Knative） |

## はじめに

1. **アカウント:** 共通ログイン（[はじめる](identity.md)）の招待で作ります。所属は既定で `users`、管理者は `admins`。招待は管理者が発行します。
2. **ログイン:** <https://cloud.apextox.dpdns.org> → 「Authentik でログイン」。
3. **アクセスキー:** CLI・Terraform にはポータルの**アクセスキー**画面で発行します。**秘密値は作成時に一度だけ表示**されるので、なくしたら作り直します。ブラウザ操作は SSO のままでキーは不要です。発行時に**権限**を選べます。**読み取り専用**は参照（一覧・詳細・容量・履歴）だけを許し、作成・電源・削除などの書き込みは 403 で拒否します。AI エージェントや閲覧用の自動化には読み取り専用を渡してください。

## ポータルでできること

<https://cloud.apextox.dpdns.org>

| 画面 | 内容 |
| --- | --- |
| インスタンス | 作成・電源（起動/停止/再起動）・コンソール・サイズ変更・削除。**一覧は全員に見え、操作は所有者と管理者だけ** |
| ボリューム | 追加ディスクの作成・接続・拡張・削除 |
| セキュリティグループ | ルールの作成。既定SGが付きます |
| イメージ / ISO | 共有イメージの一覧、ISO のアップロード（Windows 用も） |
| SSH鍵 | 公開鍵の登録 |
| アクセスキー | CLI・Terraform 用のキーを発行・失効。権限（読み書き／読み取り専用）を選ぶ |
| バケット / S3キー | バケットの作成、用途別キーの発行とバケット許可 |
| データベース | PostgreSQL の作成、接続情報（資格情報）の表示 |
| 関数 | コンテナイメージから関数を作成、URL の発行 |
| 容量 / 上限 | 空き容量の確認、上限の変更（`admins`） |
| 履歴 | 監査ログ（操作の記録） |

作成・削除は**非同期**です。ポータルの状態表示が `running` / `Ready` になるまで待ちます。

## CLI でできること

```bash
cd cloud/cli && go build -o ~/.local/bin/shakecloud .
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'   # ポータルで発行
shakecloud caller-identity
shakecloud instances list
shakecloud buckets list
shakecloud databases list
shakecloud functions list
```

全体は[shakecloud CLI](../operations/cli.md)を参照してください。

## Terraform（Provider `shakecloud`）でできること

Registry には公開していないので **dev override** でローカルビルドを使います。10リソース（`instance`・`volume`・`volume_attachment`・`security_group`・`security_group_rule`・`key_pair`・`image`・`bucket`・`database`・`function`）とデータソース `caller_identity` があります。

```hcl
resource "shakecloud_instance" "dev" {
  image_id           = "img-debian13"
  instance_type      = "small"
  key_name           = shakecloud_key_pair.me.key_name
  security_group_ids = [shakecloud_security_group.ssh.id]
  tags               = { Name = "dev" }
}
```

詳しくは[shakecloud Terraform Provider](../operations/terraform-provider.md)と、**サービスを載せるVMの置き場所**を示した[サービスの置き場所とクラウドVMでの作り方](../operations/services.md)を参照してください。

**S3キーとDB資格情報は Provider では作りません。** どちらも作成時に一度だけ返る秘密値で、state に置くと漏れるためです。ポータルか CLI で発行します。

## 権限

| グループ | できること |
| --- | --- |
| `users` | 自分のリソースを作る・見る・消す。VM 一覧は全員見える |
| `admins` | 全アカウントのリソース、サイズ変更、上限の変更、既存VMの引き取り |

グループは共通ログインの管理者が付けます（[認証基盤](../operations/identity.md#利用者の招待管理者)）。

### アクセスキーの権限

アクセスキーには**読み書き**（既定）と**読み取り専用**があります。読み取り専用は参照系の操作だけを呼べ、書き込みを呼ぶと 403 `AccessDenied` になり監査ログに残ります。権限は発行時に決まり、あとから変えられません。用途を分けて発行してください（例: Terraform は読み書き、AI エージェントは読み取り専用）。`shakecloud access-key ls` で各キーの権限を確認できます。

## 困ったとき

- **ポータルが 502/503:** クラウドAPI か管理DB が落ちている、または機能が未設定（例: Garage や Kubernetes の URL が空ならバケット/DB/関数の画面が 503）。`/healthz` を確認します。
- **VM の状態が進まない:** 履歴に理由が出ます。容量不足・Proxmox のエラーなど。管理者は cloud-01 の API ログを見ます。
- **操作の記録:** ポータルの履歴、または `GET /v1/audit-events`（[クラウドAPIの構築](../operations/cloud.md)）。

## 関連

- [サービスの置き場所とクラウドVMでの作り方](../operations/services.md)
- [クラウドAPIの構築](../operations/cloud.md)（管理者向け）
- [shakecloud CLI](../operations/cli.md)
- [shakecloud Terraform Provider](../operations/terraform-provider.md)
- [接続先一覧](../reference/urls.md)
