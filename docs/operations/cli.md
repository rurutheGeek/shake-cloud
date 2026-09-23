---
title: shakecloud CLI
updated: 2026-09-23
section: 運用手順
audience: 管理者
tags:
  - ops
  - cloud
---

# shakecloud CLI

> **更新日** 2026-09-23 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 実装済み・実機で確認済み（`cloud/cli`、クライアントは `cloud/client`）。

**クラウドAPIをコマンドから叩く道具です。** Terraform と同じ API・同じアクセスキーを使います。ポータルに入らない機械操作（スクリプト、CI、手元の確認）向けです。

## 1. 準備

アクセスキーは**ポータルで発行**します（`https://cloud.apextox.dpdns.org` → ログイン →「アクセスキー」→ 発行。表示は一度だけ）。発行時に**権限**（読み書き／読み取り専用）を選びます。読み取り専用は参照系だけを呼べ、書き込みは 403 `AccessDenied` になります。AIエージェントなどに渡すキーは読み取り専用にしてください。ブートストラップ管理キーは 2026-09-11 に無効化済みです。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'
# 別のデプロイに向けるときだけ
# export SHAKECLOUD_ENDPOINT='https://cloud.example.net'
```

キーは環境変数から読みます。コマンドライン引数には取りません（シェルの履歴に残さないため）。

## 2. ビルド

```bash
cd cloud/cli
go build -o ~/.local/bin/shakecloud .
```

`cloud/cli` は `cloud/client` を `replace` で参照します。どちらも標準ライブラリだけで、外部依存はありません。Go の版は `cloud/api/go.mod` に合わせます（1.27.1）。

## 3. 使い方

```
shakecloud [--endpoint URL] [--json] <command> [args]
```

`--json` は機械可読の生JSONを出します。付けなければ表や整形済みのテキストです。

| コマンド | 何をする |
| --- | --- |
| `identity` | このキーの持ち主（アカウントID・管理者か） |
| `capacity` | ノードの空き、ストレージ、配布済み合計、アカウント別 |
| `limits` | いま効いている上限と、管理者の上書き |
| `events [--account ID] [--name OP] [--max N]` | 操作履歴（監査ログ） |
| `instance ls [--account ID]` | インスタンス一覧（全アカウント） |
| `instance show ID` | 1台の詳細 |
| `instance run --image IMG [--type T \| --vcpus N --memory MIB] [--disk GiB] [--key NAME] [--sg ID]... [--name NAME] [--user-data FILE] [--wait]` | 作成 |
| `instance start\|stop\|reboot ID [--wait]` | 電源 |
| `instance rm ID [--wait]` | 削除（Terminate） |
| `instance console ID` | 短命のコンソールURLを表示（開くと noVNC） |
| `instance sg ID GROUP...` | セキュリティグループを差し替え |
| `instance modify ID [--vcpus N] [--memory MIB] [--min-memory MIB] [--balloon=true\|false] [--disk GiB]` | 大きさの変更（管理者） |
| `instance types` | サイズの雛形 |
| `instance adopt --vmid N --account ID [--name NAME] [--ip ADDR] [--disk GiB]` | 既存VMの引き取り（管理者） |
| `volume ls` / `volume create --size GiB [--name NAME]` / `volume rm ID` | ボリューム |
| `volume resize ID GiB` / `volume attach ID --instance IID [--device virtioN]` / `volume detach ID` | 拡張・接続・切断 |
| `sg ls` / `sg show ID` / `sg create --name NAME` / `sg rm ID` | セキュリティグループ |
| `sg add ID --direction ingress\|egress --protocol PROTO --cidr CIDR [--from N --to N]` / `sg revoke ID RULE_ID` | ルール |
| `image ls` / `image upload --name NAME FILE` / `image rm ID` | イメージ |
| `key ls` / `key import --name NAME (--public-key KEY \| FILE)` / `key rm NAME` | SSH鍵 |
| `access-key ls` / `access-key rm ID` | アクセスキーの一覧（権限 `SCOPE` 付き）と失効（発行はポータルだけ） |
| `bucket ls` / `bucket create NAME` / `bucket show NAME` / `bucket rm NAME` | S3バケット |
| `bucket allow [--read] [--write] [--owner] NAME KEY_ID` / `bucket revoke NAME KEY_ID` | S3キーの権限 |
| `s3-key ls` / `s3-key create NAME` / `s3-key rm KEY_ID` | S3アクセスキー（秘密値は作成時だけ） |
| `database ls` / `database create [--storage-gib N] NAME` / `database show ID` / `database rm ID` / `database credentials ID` | PostgreSQL（CloudNativePG） |
| `function ls` / `function create --image IMAGE NAME` / `function show ID` / `function rm ID` | サーバレス関数（Knative） |

例:

```bash
shakecloud instance ls
shakecloud instance run --image img-debian13 --type small --name web \
  --key laptop --sg sg-0123456789abcdef0 --wait
shakecloud instance console i-0123456789abcdef0
shakecloud volume create --size 20 --name data
shakecloud volume attach vol-0123456789abcdef0 --instance i-0123456789abcdef0
shakecloud sg add sg-0123456789abcdef0 --direction ingress --protocol tcp --from 443 --to 443 --cidr 192.168.10.0/24
```

S3バケットとキー:

```bash
shakecloud bucket create photos
shakecloud s3-key create laptop          # secret はここで一度だけ表示される
shakecloud bucket allow --read --write --owner photos <key_id>
shakecloud bucket show photos
shakecloud bucket rm photos

shakecloud database create --storage-gib 5 shop
shakecloud database ls
shakecloud database credentials db-...   # 接続情報（保存はしない）
shakecloud database rm db-...

shakecloud function create --image gcr.io/knative-samples/helloworld-go greeter
shakecloud function ls
shakecloud function show fn-...
shakecloud function rm fn-...
```

## 4. 実装の形

- `cloud/client` … APIの型付きクライアント。`Authorization: Bearer sca_...`。エラーは `*client.APIError`（`code`・`message`・`request_id`）として返します。Terraform Provider もこれを使っています。
- `cloud/cli` … コマンド。`flag`（標準ライブラリ）でサブコマンドを捌き、表は `text/tabwriter` で出します。設定ファイルは持ちません。

**他社CLIとのワイヤ互換はありません。** 語彙と状態遷移を一般的なクラウドの仮想マシンAPIに揃えた自作APIです（[最小クラウドとProvider](../architecture/cloud.md)）。

## 5. 確認のしかた

```bash
cd cloud/client && go vet ./... && go test ./...
cd cloud/cli && go vet ./... && go test ./...
```

`tools/verify-cloud.py` や `tools/verify-instances.py` はポータルで発行したアクセスキーでも動きます（`SHAKECLOUD_ACCESS_KEY` を設定）。
