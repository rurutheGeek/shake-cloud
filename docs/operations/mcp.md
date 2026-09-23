---
title: shakecloud MCPサーバ（読み取り専用）
updated: 2026-09-23
section: 運用手順
audience: 管理者
tags:
  - ops
  - cloud
---

# shakecloud MCPサーバ（読み取り専用）

> **更新日** 2026-09-23 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: `cloud/mcp` に実装済み（テスト付き）。dev-b でビルドし、opencode へ登録済み。**実機APIへの接続確認は読み取り専用キーの発行後**（キーの手順は「1. 準備」）。

クラウドAPIを [MCP（Model Context Protocol）](https://modelcontextprotocol.io/) のツールとしてAIエージェントへ渡すサーバです。**stdin/stdout で動くローカルプロセス**で、エージェントを動かす端末（dev-a・dev-b など）で起動し、APIへは HTTPS で接続します。サーバー側への配備は不要です。

**登録するのは読み取り専用ツールだけです。** 書き込み（作成・電源・削除など）はポータル・CLI・Terraform のままにしています。API側でも**読み取り専用アクセスキー**を使うので、万一ツールに欠陥があっても変更は 403 `AccessDenied` で止まります。**利用者向けの使い方（質問例・困ったとき）は[AIエージェントからクラウドを見る](../services/mcp.md)にあります。**

## 1. 準備

1. ポータルで**読み取り専用**のアクセスキーを発行します（<https://cloud.apextox.dpdns.org> → ログイン →「アクセスキー」→ 権限「読み取り専用」）。用途には `MCP` などと書きます。
2. ビルドします。Go の版は `cloud/mcp/go.mod`（1.27.1）に合わせます。

```bash
cd cloud/mcp
go build -o ~/.local/bin/shakecloud-mcp .
```

## 2. エージェントへの登録

環境変数は CLI と同じです。`SHAKECLOUD_ACCESS_KEY` は Git や設定ファイルへ直接書かず、秘密値の置き場から渡してください。

| 変数・引数 | 何を決める |
| --- | --- |
| `SHAKECLOUD_ACCESS_KEY` | アクセスキー（**必須**。読み取り専用を推奨） |
| `SHAKECLOUD_ENDPOINT` / `--endpoint URL` | APIの接続先。既定は `https://cloud.apextox.dpdns.org` |

MCPクライアントの設定例（書式はクライアントごとに違います）:

opencode（`~/.config/opencode/opencode.jsonc`）。鍵は設定に直書きせず、`{file:...}` で別ファイルから読みます（サーバー側が前後の空白・改行を除去します）:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "shakecloud": {
      "type": "local",
      "command": ["/home/<利用者>/.local/bin/shakecloud-mcp"],
      "enabled": true,
      "environment": { "SHAKECLOUD_ACCESS_KEY": "{file:shakecloud-mcp.key}" }
    }
  }
}
```

```bash
printf %s 'sca_...' > ~/.config/opencode/shakecloud-mcp.key
chmod 600 ~/.config/opencode/shakecloud-mcp.key
```

鍵を置いたら opencode を再起動します。サーバーの起動ログ（stderr）に「connected as …（key scope ReadOnly）」が出れば接続できています。

Claude Desktop など `mcpServers` 形式のクライアント:

```json
{
  "mcpServers": {
    "shakecloud": {
      "command": "/home/<利用者>/.local/bin/shakecloud-mcp",
      "env": { "SHAKECLOUD_ACCESS_KEY": "sca_..." }
    }
  }
}
```

起動時に接続先とキーの持ち主を**stderr**へ1行だけ出します（stdout はMCPの通信路なので使いません）。APIが一時的に落ちていても起動は続け、ツール呼び出し時にエラーを返します。ログに秘密値は出しません。

## 3. 使えるツール（22個）

APIの `x-shakecloud-scope: read` の操作のうち、資格情報が要るものを1対1で公開します。すべて `readOnlyHint` 付きです。

| カテゴリ | ツール |
| --- | --- |
| アカウント | `shakecloud_get_caller_identity`（キーの権限も返す）・`shakecloud_list_access_keys` |
| 監査 | `shakecloud_lookup_events`（`account_id`・`event_name`・`max_results` で絞る） |
| インスタンス | `shakecloud_describe_instances`・`shakecloud_describe_instance`・`shakecloud_describe_instance_types` |
| 容量・上限 | `shakecloud_describe_capacity`・`shakecloud_describe_limits` |
| イメージ・ISO・SSH鍵 | `shakecloud_describe_images`・`shakecloud_describe_isos`・`shakecloud_describe_key_pairs` |
| ボリューム | `shakecloud_describe_volumes`・`shakecloud_describe_volume` |
| セキュリティグループ | `shakecloud_describe_security_groups`・`shakecloud_describe_security_group` |
| S3 | `shakecloud_describe_buckets`・`shakecloud_describe_bucket`・`shakecloud_list_s3_keys` |
| database・function | `shakecloud_describe_databases`・`shakecloud_describe_database`・`shakecloud_describe_functions`・`shakecloud_describe_function` |

**意図的に出さないもの**:

- **`GetDatabaseCredentials`**（読み取りですがDBパスワードを返すため。会話へ秘密値を入れません）
- **すべての書き込み**（起動・停止・作成・削除・コンソール・limits変更など）。ポータル・CLI・Terraform を使ってください。

## 4. セキュリティと監査

- APIはLAN内のみです。MCPサーバはエージェントの端末からHTTPSで接続します。
- 監査ログには `user_agent` が `shakecloud-mcp/0.1.0` として残ります（CLI・Terraformと区別できます）。
- 読み取り専用キーの書き込みは 403 `AccessDenied` になり、監査ログに残ります（[クラウドAPI本体](cloud-api.md#アクセスキー)）。
- キーを失効させれば、次の呼び出しから 401 になります。

## 5. 確認のしかた

```bash
cd cloud/mcp && go vet ./... && go test ./...
```

テストは、①ツール一覧が `cloud/openapi/shakecloud.yaml` の読み取り操作と一致すること（書き込みツールの混入も検出）、②入力スキーマの必須項目、③偽APIに対する実呼び出し（`Authorization` ヘッダーとエラーの見え方）を確認します。DBは要りません。

## 関連

- [AIエージェントからクラウドを見る（MCP）](../services/mcp.md) — 利用者向けの質問例とトラブルシューティング
- [クラウドAPI本体とインスタンス](cloud-api.md)（アクセスキーの権限）
- [shakecloud CLI](cli.md)
- [shakecloud Terraform Provider](terraform-provider.md)
- [クラウドの使い方](../services/cloud.md)
