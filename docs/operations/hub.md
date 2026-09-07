# ハブの運用

## ドメインなしで接続

手元のPCで実行し、`ubuntu@SERVER` を実際の接続先に置き換えます。すでに同じポートを転送しているSSH接続は終了してから実行してください。

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 7575:127.0.0.1:7575 -L 8090:127.0.0.1:8090 \
  -L 8081:127.0.0.1:8081 -L 4533:127.0.0.1:4533 \
  -L 8243:127.0.0.1:8243 -L 8000:127.0.0.1:8000 \
  -L 8443:127.0.0.1:8443 -L 5443:127.0.0.1:5443 \
  -L 9443:127.0.0.1:9443 \
  ubuntu@SERVER
```

ハブは [localhost:7575](http://localhost:7575)、手順書は [localhost:8090](http://localhost:8090) です。Nextcloudは [nextcloud.localhost:8443](https://nextcloud.localhost:8443)、Kavitaは [kavita.localhost:5443](https://kavita.localhost:5443)、Vaultwardenは [vault.localhost:8243](https://vault.localhost:8243)、共通認証は [login.localhost:9443](https://login.localhost:9443) です。

## ローカルCAの信頼登録（利用端末ごとに初回）

Nextcloud・KavitaのOIDCとVaultwardenのWeb保管庫にはHTTPSが必要なため、CaddyのローカルCAを使います。

1. SSH転送で [CA証明書](http://localhost:8090/downloads/local-ca.crt) を取得します。サーバーの `docs/downloads/local-ca.crt` と同じ公開証明書です。
2. 自分のPCの信頼するルート証明書へ登録します。Windowsは「現在のユーザー → 信頼されたルート証明機関」、macOSはキーチェーンで証明書を信頼、Ubuntuは `/usr/local/share/ca-certificates/` へ配置後に `sudo update-ca-certificates` を実行します。Firefoxが独自の証明書ストアを使う場合はFirefox側にも登録します。
3. ブラウザーを再起動し、上のHTTPS URLで証明書エラーが出ないことを確認します。

証明書のSHA-256指紋はサーバーで `openssl x509 -in docs/downloads/local-ca.crt -noout -fingerprint -sha256` により確認できます。インポート対象は公開CA証明書だけです。`sso/storage` にあるCA秘密鍵は外部へ渡しません。

通常、ブラウザーは `.localhost` を手元のPCへ解決します。解決できない場合はPCのhostsへ `127.0.0.1 login.localhost nextcloud.localhost kavita.localhost vault.localhost` を追加してください。

この構成はSSHトンネル内で利用します。ドメイン取得後に外部公開する場合は、証明書、サービスURL、OIDCのissuerと厳密なredirect URI、信頼するプロキシ設定をまとめて変更します。

## コードから配備

基本スタック・NetBox・管理者の初期化後、次の順で実行します。

```bash
sudo .hub-venv/bin/python hub/manage.py up
sudo python3 music-tools/manage.py up
sudo .hub-venv/bin/python sso/manage.py
```

AnsibleではNetBoxインベントリを読み込み、`ansible/deploy.yml` → `ansible/hub.yml` → `ansible/music-tools.yml` → `ansible/sso.yml` の順です。Dockerは基本Playbookが導入します。`sso/manage.py` はNetBoxも存在する場合にOIDC設定を適用します。

`hub/apps.json` がサービスリンク、`docs/` が日本語手順の正本です。管理対象の設定は再配備でコードの内容へ戻します。

```bash
sudo .hub-venv/bin/python hub/configure-homarr.py
sudo .hub-venv/bin/python hub/manage.py build
```

## データと移設

原本は `.env` の `LIBRARY_ROOT`、アプリ状態は `STORAGE_ROOT` です。加えて `hub/storage`、`netbox/storage`、`music-tools/storage`、`sso/storage` を保存します。NetBoxの状態パスを変更している場合は `netbox/.env` の設定を使います。

移設ではサービスを停止して原本・各状態領域・秘密値を所有者/権限ごと移し、移設先の `.env` でパスを合わせます。CAを維持する場合は `sso/storage` も必要です。再生成した場合は利用端末で新しいCAを信頼し直します。

既存のバックアップコマンドは担当範囲が分かれています。

- `scripts/stack.py backup`：基本スタックの状態・原本・設定
- `hub/manage.py backup`：Homarr・Authentikの状態と秘密値
- `netbox/manage.py backup`：NetBoxの状態と秘密値
- `music-tools/storage`、`sso/storage`：対象Composeを停止して別途コピー

`hub/oidc-secrets.json`、各 `.env`、`secrets/`、生成済み `compose.integrations.yaml`・`compose.sso.yaml`、`runtime/access.json` も非公開バックアップへ含めます。GitHubは実データや秘密値のバックアップ先ではありません。復元訓練は移設先の隔離環境で別途実施してください。

AWXは保留中です。導入時はkubeadmのKubernetesを使います。
