# eufy-security-wsの開発入口

状態: **2026-09-12にstackを追加。実機配備はEufyの資格情報（`platform/sops/eufy-security.sops.yaml`）を入れてから**。eufyCam S4（T8172）はHomeBaseなしの単体動作で、[eufy-security-clientの対応機器一覧](https://github.com/bropat/eufy-security-client/blob/master/docs/supported_devices.md)に載っている。

## 何をするか

HAコアにEufyの公式統合はない。EufyクラウドへログインしてP2Pで機器へつなぐ [eufy-security-ws](https://github.com/bropat/eufy-security-ws) を中継として動かし、HA側はカスタム統合 [`fuatakgun/eufy_security`](https://github.com/fuatakgun/eufy_security) からWebSocketで接続する。RTSP/NASは前提にしない。

配備先: **services-01**。プロジェクトは `/opt/services/eufy-security-ws`、状態は `/srv/services/eufy-security-ws/data`。ポートはLANへ公開せず、HAのComposeネットワーク（`services-home-assistant_homeassistant`）へ入れて `eufy-security-ws:3000` で届かせる。

## 資格情報

Eufyアカウント（メール・パスワード・国コード）は `platform/sops/eufy-security.sops.yaml` に置き、配備時にAnsibleが復号して `/opt/services/eufy-security-ws/.env`（0600）へ写す。**Git・ログ・チャットへ出さない。**

```bash
sops platform/sops/eufy-security.sops.yaml
```

2FAを有効にしている場合、初回ログインはEufyアプリに出る確認コードが要る。`TRUSTED_DEVICE_NAME` の端末が信頼されると `/data` のセッションに保存され、以後は無人で起動する。コードは `docker compose logs -f` で確認する。

## 配備

HAのネットワークが先に必要なので、`home-assistant.yml` の後に流す。

```bash
.venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/eufy-security-ws.yml
```

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.200 \
  'sudo docker logs --tail 50 services-eufy-security-ws-eufy-security-ws-1'
```

## HA側

HAのカスタム統合 `eufy_security`（v8.2.4、digest固定）は `home-assistant.yml` が `custom_components/` へ入れる。オーナー作成後、**設定 → デバイスとサービス → 統合を追加 → Eufy Security** で、ホスト `eufy-security-ws`・ポート `3000` を指定する。まずイベントとスナップショットを読み取りで確認し、ライブ映像は別途試す。既存のEufyアプリと録画は変更しない。

## 注意

- `bropat/eufy-security-ws` と `eufy-security-client` はdeprecatedで、後継は [mega-yfue/eufy-sdk](https://github.com/mega-yfue/eufy-sdk)。新しいHA統合が安定したら乗り換えを再判断する。イメージは `compose.lock.yaml` でdigest固定し、更新はRenovateで確認する。
- コンテナの状態（セッション・トークン）は `/srv/services/eufy-security-ws/data` にあり、バックアップ対象。資格情報はSOPSから復元する。
