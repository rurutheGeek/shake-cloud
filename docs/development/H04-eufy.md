# H04 EufyCam連携の検証

更新日: 2026-09-12。これは開発計画であり配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

状態: **機種はeufyCam S4（T8172）・HomeBaseなし（カメラ単体）と確認。方式は `eufy-security-ws` + HAカスタム統合（RTSPは前提にしない）。stackを実装して配備し、Eufyの資格情報待ち**。

[家電の構成案](../architecture/operations.md#home-devices)ではAnker EufyCam S4と記載されるが、正確なHomeBase・FW・RTSP項目は未確認。一般的なEufyのNAS対応をS4の保証にしない。

2026-09-12の調査（一次資料）: eufyCam S4は **HomeBaseなしの単体動作**（ルーターへ直接Wi-Fi接続）に対応し、32GB内蔵＋microSDで録画する。HomeBase S380を足すと24/7録画・Snapshot・BionicMind等が増えるが、HomeBase 2／mini／ProfessionalとApple HomeKitは非対応。

**HAへの連携はRTSPではなく `eufy-security-ws`（bropat）を中継に使う。** [対応機器一覧](https://github.com/bropat/eufy-security-client/blob/master/docs/supported_devices.md)に **eufyCam S4 (T8172) が対応済み**（確認FW 1.0.6.5）と記載がある。WSサーバはクラウドへログインしてP2Pで機器へ接続し、HA側はカスタム統合 [`fuatakgun/eufy_security`](https://github.com/fuatakgun/eufy_security) がWSへつないでイベント・スナップショット・ライブ映像を扱う。RTSP/NASの有無に依存しない。

注意: `eufy-security-client`／`eufy-security-ws` は**deprecated**で、開発は [mega-yfue/eufy-sdk](https://github.com/mega-yfue/eufy-sdk)（2FA対応、P2P・イベント・ライブ配信）へ移行中。新しいHA統合も開発中のため、いまは実績のあるWSを使い、新統合の安定後に乗り換えを再判断する。ログインは `TRUSTED_DEVICE_NAME` の端末をEufyアプリで信頼し、セッションを `/data` に保存する。資格情報・2FAコードは `platform/sops/eufy-security.sops.yaml` だけに置く。

配備先・開発範囲: **services-01。`eufy-security-ws` はHAとは別Compose（プロジェクト `services-eufy-security-ws`、状態 `/srv/services/eufy-security-ws/data`、資格情報はSOPS）で動かし、HAのComposeネットワークへ入れて `eufy-security-ws:3000` で届かせる（LANへは公開しない）。HA側の統合は設定と手順だけを管理する。既存Eufyアプリ/録画先は維持**。

## 実装手順

1. 型番・HomeBase・FW・アプリ内のNAS/RTSP設定、イベント/静止画/ライブ映像の希望を記録し、対象機種の一次資料で確認する。
2. 対応が確認できた機能から読み取りで試す。公式統合がない場合は追加連携/中継の互換性・認証・更新・メモリを調べ、採用判断を記録してから配備する。
3. 映像表示とイベントを別々に検証し、必要なLAN到達とHA設定だけを追加する。既存録画を変更せず、常時録画・映像AIを追加する場合は別の容量計画/作業IDへ分ける。

## 依存と並列作業

- 開発開始: 調査項目の整理はH01と並列。固有検証には実機の型番/設定とアクセスが必要。
- 配備・切替: [H01](H01-home-assistant.md)、機種対応確認、[I01](I01-resources.md)で追加サービス負荷確認。必要な通信変更は[N03](N03-vlan.md)と調整。
- 競合調整: H01の共通設定・ネットワークを調整する。既存録画とカメラ設定の変更は所有者と調整し、HAの履歴領域を録画庫に流用しない。

## 検証・完了条件

- イベント・静止画・ライブ映像の各可否、遅延、再接続を記録する。未対応機能を利用可能と案内しない。
- 映像と資格情報が許可外へ公開されず、既存アプリと録画が継続する。
- HA/中継の再起動と設定復元後に確認済み機能が戻る。未対応なら調査結果と再開条件を残して保留する。

## 実機の結果（2026-09-12）

- `stacks/eufy-security-ws/`（Compose・`manage.py`・`.env.example`・テスト）と `platform/ansible/eufy-security-ws.yml` を追加。services-01へ配備し、`/opt/services/eufy-security-ws`・`/srv/services/eufy-security-ws/data` と `.env`（0600）を作成済み。
- HA側は `home-assistant.yml` が `eufy_security` v8.2.4（digest固定）を `custom_components/` へ配備済み。Eufyの資格情報が未記入のため、WSコンテナの起動だけをスキップする（Ansibleが次の手順を表示）。

## 次の確認（実機）

1. `sops platform/sops/eufy-security.sops.yaml` に `EUFY_USERNAME`・`EUFY_PASSWORD`・`EUFY_COUNTRY`（必要なら `EUFY_TRUSTED_DEVICE_NAME`）を入れる。2FAがあれば初回ログの確認コードを `docker compose logs -f` で見て、信頼端末を承認する。**資格情報・2FAコードはGit/ログ/この文書へ残さない。**
2. `.venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/eufy-security-ws.yml` で起動し、healthyを確認する。イメージは `compose.lock.yaml` でdigest固定。
3. HAのオーナー作成後、**設定 → デバイスとサービス → 統合を追加 → Eufy Security** でホスト `eufy-security-ws`・ポート `3000` を指定する。まずイベントとスナップショットを読み取りで確認し、ライブ映像は後から試す。既存録画・カメラ設定は変更しない。
4. WS/HAの再起動と一時切断後の再接続を確認し、WS・統合のメモリを[I01](I01-resources.md)の実測に足す。新SDK（`mega-yfue/eufy-sdk`）ベースのHA統合が安定したら乗り換えを再判断する。
5. HomeBase S380の追加は今回の範囲外。追加する場合は24/7録画と容量・保存先を別計画（[I01](I01-resources.md)）で確認する。
