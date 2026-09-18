# print-api（services-01）

Nextcloudの「印刷」アクション（[`stacks/media/nextcloud/apps/shake_print/`](../media/nextcloud/apps/shake_print)）
からのHTTP POSTを受け、services-01のCUPSキュー `ts8430` へ流す小さなAPIです。
標準ライブラリだけで動きます。

## 構成

| ファイル | 内容 |
| --- | --- |
| `print_api.py` | HTTPサーバー本体。`POST /print` で本文を一時ファイルへ落とし、`lp -d <queue>` を実行する |
| `print-api.service.j2` | systemdユニット。CUPSロールが `/etc/systemd/system/print-api.service` へ描画する |

## 受け口

- `POST /print` — 本文がドキュメント本体。
  - `Authorization: Bearer <token>`（必須。トークンは `platform/sops/print-api.sops.yaml`）
  - `X-Print-Filename`（URLエンコード済みのファイル名。拡張子で形式を判定）
  - `X-Print-Copies`（1〜99。既定1）／`X-Print-Color`（`color` / `monochrome`。既定color）
- `GET /healthz` — 200を返すだけ（`cups.yml` の確認と監視用）
- 対応形式: PDF・PNG・JPEG・テキスト。最大50MiB（`PRINT_API_MAX_BYTES`）
- 送信元は既定で media-01（`192.168.10.101`）だけ。それ以外はトークンが正しくても401

設定はsystemdのEnvironmentFile（`/opt/print-api/print-api.env`・0400）で渡します。
キーは `PRINT_API_TOKEN` / `PRINT_API_BIND` / `PRINT_API_PORT` / `PRINT_API_ALLOWED` /
`PRINT_API_MAX_BYTES` / `PRINT_QUEUE` です。

## 配備と確認

`platform/ansible/roles/cups` がコピーとユニット設置を行います（`platform/ansible/cups.yml`）。

```bash
# 単体テスト（認証・形式・コマンド組み立て）
python3 -m unittest tests.test_print_app

# 手元からの疎通（トークンはSOPSから）
sops exec-env platform/sops/print-api.sops.yaml \
  'curl -s -o /dev/null -w "%{http_code}\n" http://192.168.10.200:6320/healthz'
```

印刷そのものの使い方は[プリンター](../../docs/services/printer.md)を参照してください。
