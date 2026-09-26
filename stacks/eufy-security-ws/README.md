# eufy-security-wsの開発入口

状態: **services-01へ配備済み（2026-09-12）。Eufyの資格情報（`platform/sops/eufy-security.sops.yaml`）は投入済みで、eufyCam S4（T8172）・SmartTrack（T87B0）のログイン・デバイス一覧・Pushまで動作。S4の人物・動体イベントがHAまで届くことを2026-09-23に確認（イベント画像は確認中）。ライブ映像はS4の新WebRTC方式のため、現行の公開ソフトでは不可（2026-09-13に実機で確定）**。eufyCam S4（T8172）はHomeBaseなしの単体動作で、[eufy-security-clientの対応機器一覧](https://github.com/bropat/eufy-security-client/blob/master/docs/supported_devices.md)に載っている。

## 何をするか

HAコアにEufyの公式統合はない。EufyクラウドへログインしてP2Pで機器へつなぐ [eufy-security-ws](https://github.com/bropat/eufy-security-ws) を中継として動かし、HA側はカスタム統合 [`fuatakgun/eufy_security`](https://github.com/fuatakgun/eufy_security) からWebSocketで接続する。RTSP/NASは前提にしない。

配備先: **services-01**。プロジェクトは `/opt/services/eufy-security-ws`、状態は `/srv/services/eufy-security-ws/data`。P2PがホストのLAN NICを使う必要があるためホストネットワークで動かし、起動時に待受をHAのComposeネットワーク（`services-home-assistant_homeassistant`）のゲートウェイ `172.31.254.1:3000` だけへ差し替える（LANへは公開しない）。

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

HAのカスタム統合 `eufy_security`（v8.2.4、digest固定）は `home-assistant.yml` が `custom_components/` へ入れる。HAの「設定 → デバイスとサービス → 統合を追加 → Eufy Security」で、ホスト `172.31.254.1`・ポート `3000` を指定する（追加済み。S4・SmartTrackを認識）。人物・動体イベントは確認済み、スナップショットは確認中で、**ライブ映像はS4（T8172）の新WebRTC方式のため現行の公開ソフトでは不可**（[H04](../../docs/development/H04-eufy.md)）。既存のEufyアプリと録画は変更しない。

## 動体・人物の通知が届かないとき

S4はPushを新しいv6（eufy_mega）側で送る。WSが保存したv6トークンがサーバ側で無効になると（同じアカウントで検証用クライアントがログインした直後から始まったため、それが原因と推定）、起動のたびに `v6 push: register_push_token returned a non-zero code`（`code: 401`・`token not exist`）が出て通知が一切届かなくなる（2026-09-14〜09-23に発生）。クライアントはこの401で再ログインしないため、v6のセッションだけを消して再起動する。旧来のセッションは残るのでCAPTCHAは出にくい。

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.200 \
  'sudo python3 /opt/services/eufy-security-ws/manage.py reset-mega-session'
```

起動ログに `v6 push: FCM token registered on the eufy_mega backend` が出れば復旧。`EUFY_DEBUG=1` はトークンや鍵をログへ平文で出すので、調査の間だけ使う（Ansibleは既定で空に戻す。ログは10MB×3でローテーション）。

## 注意

- `bropat/eufy-security-ws` と `eufy-security-client` はdeprecatedで、後継は [mega-yfue/eufy-sdk](https://github.com/mega-yfue/eufy-sdk)。新しいHA統合が安定したら乗り換えを再判断する。イメージは `compose.lock.yaml` でdigest固定し、更新はRenovateで確認する。
- コンテナの状態（セッション・トークン）は `/srv/services/eufy-security-ws/data` にあり、バックアップ対象。資格情報はSOPSから復元する。
