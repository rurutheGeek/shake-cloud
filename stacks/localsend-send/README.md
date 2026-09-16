# LocalSend送信API（media-01）

Nextcloudの「LocalSendで送る」アクション（`stacks/media/nextcloud/apps/shake_localsend/`）
からのHTTP POSTを受け、同じLANにいる端末のLocalSendアプリへファイルを送るAPIです。
標準ライブラリだけで動きます。

media-01の受信機（`stacks/media/localsend/`）は受信専用なので、こちらが送信側です。

## 構成

| ファイル | 内容 |
| --- | --- |
| `localsend_send.py` | HTTPS/HTTPサーバー本体。LocalSend protocol v2の`prepare-upload`→`upload`を実行する |
| `localsend-send.service.j2` | systemdユニット。`media-localsend.yml` が `/etc/systemd/system/localsend-send.service` へ描画する |

## 受け口

- `GET /devices` — LAN上のLocalSend端末を探して一覧を返す（要 `Authorization: Bearer <token>`）
- `POST /send` — 本文がファイル本体。ヘッダで送り先を指定する（要トークン）
  - `X-Send-To`: 送り先のfingerprint（`/devices` の値）
  - `X-Send-Filename`: URLエンコード済みのファイル名
  - `X-Send-User`: 任意。ファイル名の前に付ける送信者名
- `POST /api/localsend/v2/register` — 端末からの探索応答を受ける（トークン不要。端末一覧の記録用）
- `GET /healthz` — 200

設定はsystemdのEnvironmentFile（`/opt/localsend-send/localsend-send.env`・0400）で渡します。
`LOCALSEND_SEND_TOKEN` と `LOCALSEND_SEND_FINGERPRINT` は `platform/sops/localsend-send.sops.yaml` が正本です。

## 仕組み

1. `224.0.0.167:53317` とブロードキャストへ自分の情報をアナウンスする
2. 応答（UDPまたはHTTPの `register`）から端末のfingerprint・アドレス・ポートを記録する
3. 選ばれた端末へ `prepare-upload`（メタデータ）→ `upload`（本体）を送る。端末側のLocalSendに受信確認が出る

端末側はLocalSendアプリを開いて受信できる状態にしてください。自己署名証明書は
LocalSend同様に検証しません（相手も自己署名のため）。

## 配備と確認

`platform/ansible/media-localsend.yml` が受信機と一緒に配備します。

```bash
# ヘルスチェック
curl -s http://127.0.0.1:53200/healthz

# 端末一覧（トークンはSOPSから）
sops exec-env platform/sops/localsend-send.sops.yaml \
  'curl -s -H "Authorization: Bearer $LOCALSEND_SEND_TOKEN" http://192.168.10.101:53200/devices'
```

使う側は[Nextcloudの使い方（利用者向け）](../../docs/services/nextcloud-guide.md)を参照してください。
