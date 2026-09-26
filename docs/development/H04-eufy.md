---
title: H04 EufyCam連携の検証
updated: 2026-09-23
section: 開発計画
audience: 開発者
tags:
  - plan
  - home-assistant
---

# H04 EufyCam連携の検証

> **更新日** 2026-09-23 ・ **区分** 開発計画 ・ **読む人** 開発者

これは開発計画であり配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的・現状

**状態**: 人物・動体イベントは稼働、ライブ映像は不可。`eufy-security-ws` 3.1.0（独立Compose、hostネットワークで `172.31.254.1:3000` のみbind・LAN非公開）＋HA統合 `eufy_security` v8.2.4（host `172.31.254.1:3000`）を配備済み（資格情報は `platform/sops/eufy-security.sops.yaml`）。eufyCam S4（T8172）とSmartTrack（T87B0）でログイン・デバイス一覧・Pushまで動作。ライブ映像はS4の新WebRTC（leo_rtc）方式のため現行の公開ソフトでは不可で、後継 `mega-yfue/eufy-sdk` でのRTSPブリッジを検討中。人物・動体イベントは2026-09-23にHAまで届くことを実機で確認（イベント画像は確認中）

[家電の構成案](../architecture/operations.md#home-devices)ではAnker EufyCam S4と記載される。実機は **eufyCam S4（T8172、fw 1.1.1.2、HomeBaseなしの単体、IP 192.168.10.4）** と **SmartTrack（T87B0）** の2台で確認した。RTSP/NASは使えない前提とし、一般的なEufyのNAS対応をS4の保証にしない。

2026-09-12の調査（一次資料）: eufyCam S4は **HomeBaseなしの単体動作**（ルーターへ直接Wi-Fi接続）に対応し、32GB内蔵＋microSDで録画する。HomeBase S380を足すと24/7録画・Snapshot・BionicMind等が増えるが、HomeBase 2／mini／ProfessionalとApple HomeKitは非対応。

**HAへの連携はRTSPではなく `eufy-security-ws`（bropat、3.1.0）を中継に使う。** [対応機器一覧](https://github.com/bropat/eufy-security-client/blob/master/docs/supported_devices.md)に **eufyCam S4 (T8172) が対応済み**（確認FW 1.0.6.5）と記載がある。WSサーバはクラウドへログインしてP2Pで機器へ接続し、HA側はカスタム統合 [`fuatakgun/eufy_security`](https://github.com/fuatakgun/eufy_security)（v8.2.4）がWSへつないでイベント・スナップショット・ライブ映像を扱う（S4のライブ映像は後述の理由で不可）。RTSP/NASはS4では使えない前提とし、これに依存しない。

注意: `eufy-security-client`／`eufy-security-ws` は**deprecated**で、開発は [mega-yfue/eufy-sdk](https://github.com/mega-yfue/eufy-sdk)（2FA対応、P2P・イベント・ライブ配信）へ移行中。ライブ映像は同SDKのブリッジ（P2P・RTSP publish）で実現できないか検討・追跡するが、現行版はS4のleo_rtcに未対応（後述）。新しいHA統合も開発中のため、いまは実績のあるWSを使い、新統合の安定後に乗り換えを再判断する。ログインは `TRUSTED_DEVICE_NAME` の端末をEufyアプリで信頼し、セッションを `/data` に保存する。資格情報・2FAコードは `platform/sops/eufy-security.sops.yaml` だけに置き、Git・ログ・この文書へ残さない。

配備先・開発範囲: **services-01。`eufy-security-ws` はHAとは別Compose（プロジェクト `services-eufy-security-ws`、状態 `/srv/services/eufy-security-ws/data`、資格情報はSOPS）で動かし、hostネットワークで `172.31.254.1:3000` のみをbindしてLANへは公開しない。HA側は `eufy_security` 統合から host `172.31.254.1`・ポート `3000` へ接続する。HA側の統合は設定と手順だけを管理する。既存Eufyアプリ/録画先は維持**。

## 実装手順

1. 型番・HomeBase・FW、イベント/静止画/ライブ映像の希望を記録し、対象機種の一次資料で確認する。
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

- `stacks/eufy-security-ws/`（Compose・`manage.py`・`.env.example`・テスト）と `platform/ansible/eufy-security-ws.yml` を追加。services-01へ配備し、`/opt/services/eufy-security-ws`・`/srv/services/eufy-security-ws/data` と `.env`（0600）を作成済み。WSは `bropat/eufy-security-ws:3.1.0`、hostネットワークで `172.31.254.1:3000` のみbind。
- HA側は `home-assistant.yml` が `eufy_security` v8.2.4（digest固定）を `custom_components/` へ配備済み。Eufyの資格情報は `platform/sops/eufy-security.sops.yaml` に投入し、WSはhealthy。S4（T8172）とSmartTrack（T87B0）でログイン・デバイス一覧・Pushまで動作し、イベント取り込みは確認中。

## ライブ映像の結論（2026-09-13。リバースエンジニアリング）

**イベント・push・スナップショットは現行の `eufy-security-ws` + `eufy_security` 統合で扱い、これを維持する（人物・動体イベントは2026-09-23に確認済み、スナップショットは確認中）。ライブ映像だけは現行の公開ソフトウェアでは実現できないと実機で確認した。** 理由を根拠つきで残す（次に触る人が同じ調査を繰り返さないため）。

一次資料は dev-b から取得した機器の生データ。S4（`T8172P102603060C`、fw `1.1.1.2`、IP `192.168.10.4`、battery、`p2p_did REUPRAA-000134070-D6CBHYKRDK`）はクラウド応答で `p2p_conn`/`app_conn` が空、`signaling_servers=["https://webrtc-signal-eu.eufylife.com","https://75.2.46.73"]`、`webrtc_sdk_version=6.1.3`。つまり旧来の ThroughTek PPCS ではなく **新しい leo_rtc（WebRTC）バックエンド**専用。

### 検証した経路と失敗理由

1. **推奨ルート（`mega-yfue/eufy-sdk` の `camera().live()`）は不可**。dev-b で単体検証（Node 24・SDK 0.1.1をビルド）。ログイン・デバイス一覧・codec/capability取得までは成功するが、`live()` は `P2P session did not connect` で失敗。SDKログは `sendLookups: NO cloud lookup sent (dskKey=true cloudAddresses=0)` を繰り返す。SDKは旧 P2P（`p2p_conn` 由来のクラウド lookup ＋ LAN 32108 ブロードキャスト）しか持たず、**leo_rtc を実装していない**。クラウドが lookup アドレスを返さない S4 では原理的に届かない。SDK の RTSP publish（`rtsp().publish()`）も leo_rtc 機に非対応。
2. **Web ポータルの WebRTC シグナリングは、待機中のバッテリーカメラを起こせない**。公式 Web（`mysecurity.eufylife.com` / `security.eufy.com`）の JS を復号して手順を復元し、保存セッションのトークンで実機に対して再実行した:
   `GET https://security-smart-eu.eufylife.com/v1/smart/nvr/ws/sign`（`Model-Type: WEB` のみ許可。`Web-Country: JP`, `GToken=md5(user_id)`）→ `wss://security-smart-eu.eufylife.com/v1/rtc/ws/join?reqtype=nvr`（`sign` をサブプロトコルに base64url で載せる）→ `action:1` auth → `action:3 scall` を送信すると **クラウドは `status:100` と TURN 資格（coturn、realm `anker.com`、UDP 3478）を返す**が、その後カメラは SDP offer を出さず **`status:408`（無応答）で終わる**。FCM push＋MQTT を張った完全なアプリ presence を同時に持たせても 408。`Model-Type: PHONE` にすると scall 自体が無応答（Web ゲートウェイはスマホ型セッションを扱わない）。→ **この Web ゲートウェイ経路はスマホと別系統で、常時接続の機器（HomeBase/NVR）向け。バッテリーカメラの wake を行わない。**
3. **スマホ実機が使う経路はネイティブ leo_rtc**。APK（`com.oceanwing.battery.cam` 6.0.90）の `libmega_media_sdk.so` を解析（Ghidra）。ライブは `webrtc/rtc_signal_*`（`ClientLogin`/`ClientDiscover`/`ClientWakeup`/`ClientSendCall`）が機器の `signaling_servers`（`webrtc-signal-eu.eufylife.com` / `75.2.46.73`）へ独自バイナリ（UDP/TCP、`rtc_protocol.c`）で接続し、`rtc_crypto.c`（ECC＋AES-GCM）で暗号化、DTLS/SCTP のデータチャネルで H.264 を運ぶ。**カメラの wake はこのネイティブ経路でのみ起きる**。dev-b から `75.2.46.73:443/TCP` は到達不可（フィルタ/タイムアウト）、UDP は coturn 3478 のみ応答。

### 帰結（実装判断）

- ライブ映像の完成には、上記スマホネイティブ leo_rtc プロトコル（`rtc_signal`＋独自暗号＋DTLS/SCTP＋H.264 再構成）を**フル実装する必要がある**。これは元計画の「代替：最終手段のフルRE」に当たり、工数大。既存の公開実装（`mega-yfue/eufy-sdk`、`bropat/eufy-security-ws`、`caplaz` フォーク、`genomez` フォーク）はいずれも**単体バッテリーカメラのこの経路を実装していない**（`genomez` は常時接続の HomeBase Professional S1／T9000 の Web ゲートウェイ WebRTC のみ）。
- 従って**現時点でライブ用の stack は作らない**（動かないものを「利用可能」と案内しない、というリポジトリ方針に従う）。イベント・push・スナップショットは配備済みの `eufy-security-ws` で維持する。
- 解析成果（復号したポータル手順、`libmega_media_sdk` の関数対応、scall/TURN の実測ログ）はフルRE着手時の出発点として本節に要約した。生成物は作業機の一時領域にあり、Git には置かない（秘密値・APK を含むため）。

### 追試: keesmod/eufy-mega-client 0.18.0（2026-09-23）

HomeBase 3 系カメラ向けの新しい独立クライアント [keesmod/eufy-mega-client](https://github.com/keesmod/eufy-mega-client)（`1792bbc`）を dev-b でビルドし、同じアカウントで試した（独自セッション・Node 24）。

- ログイン: 追加認証なしで `connected`。
- `discoverDevices()`: S4 を `T8172`・fw `1.1.1.2`・battery 61・`availability: online` として認識する。ただし関係は `unsupported` / `invalid_device_relationship`（親が自分自身＝単体運用）。単体運用のカメラは対象外。
- `snapshot()`・`startLive()`: どちらも `invalid_device_relationship` で拒否。
- `startEvents()`: push 接続は成立したが、3分間の受信は0件（その間に動体があったかは未確認）。
- 結論: このクライアントも現時点では単体 S4 のライブ・スナップショットに対応しない。単体カメラ対応の調査 [#36](https://github.com/keesmod/eufy-mega-client/issues/36) は2026-09-16に閉じ、残りの認証・映像経路は [#142](https://github.com/keesmod/eufy-mega-client/issues/142) で追跡されている（単体カメラ所有者からの伏字済み機器情報と接続手順の証拠を求めている）。進展したら再試験する。
- 通知の追試は不向き: 0.18.0 は受信した Push を「HomeBase 3 配下のカメラ」かで絞る（`client.ts` の `known`・`device-transport.ts` の `acceptPush`）。単体 S4 の通知は届いても捨てられる。加えて同じアカウントで別クライアントがログインすると、WS の v6 トークンが無効になる疑いがある（次節）。

### 通知が届かなかった原因と復旧（2026-09-23）

WSは9/14から10日間、動体・人物の通知を1件も受け取っていなかった（FCMのデータメッセージ受信0件）。原因はWSの2系統ある通知登録のうち、S4が使うv6（eufy_mega）側の失敗。

- 旧来側（`v1/apppush/register_push_token`）は毎回成功。v6側（`app-push-eu-pr.eufy.com /app/push/register_push_token`）は9/13までは成功していたが、9/14以降は毎回 `401 token not exist`。
- 9/13に作業機（dev-b）から同じアカウントで検証用のログインを繰り返した直後から失敗しており、サーバ側でWS保存のv6トークンが無効化されたと推定。`eufy-security-client` 4.1.0 の `MegaTransition` はトークンの期限（ローカル値）しか見ず、401で再ログインしないため、期限（10/12）まで失敗し続ける。
- 復旧: `persistent.json` の `megaApi` だけを退避・削除して再起動（旧来セッションは維持）。v6へ追加認証なしで再ログインし、`v6 push: FCM token registered on the eufy_mega backend` を確認。手順は `manage.py reset-mega-session` として追加した（[README](https://github.com/rurutheGeek/shake-cloud/blob/main/stacks/eufy-security-ws/README.md)）。
- 結果（2026-09-23 21:56〜21:58 JST、カメラ前を歩いて確認）: WSが人物検知のPush（`type 89` / `event_type 3102`「Someone has been spotted」）を受信し、HAの `binary_sensor.rihinku_person_detected`・`motion_detected` が3回とも約12秒オンになって戻った（`sensor.rihinku_person_name` は `Unknown Person`）。確認の直前に所有者がEufyアプリを初期化しており、アプリ側の状態も通知が届かなかった一因だった可能性がある（v6登録の失敗はそれ以前からログで確認済み。アプリ側の寄与は切り分けていない）。
- 再起動: Ansibleで再配備（コンテナ作り直し）した後も、保存したv6セッションでPush登録が成功し、HAは約4秒で再接続した。
- 教訓: **WS稼働中に同じアカウントで他のクライアントをログインさせない**。検証が必要なら別アカウント（Eufyアプリの共有ユーザー）を使う。
- 同時に、配備中の compose（ホストネットワーク・`172.31.254.1` bind・`STATION_IP_ADDRESSES`・`DEBUG`）と `manage.py reset-session` がリポジトリへ入っていなかったのを取り込んだ。`DEBUG=1` がトークン・鍵をログへ平文で出し、ログが無制限（331MB）だったため、既定をオフにしてログを10MB×3でローテーションする。

### 次に取り得る選択肢（優先順）

1. **現状維持＋スナップショット運用**（推奨・即時）。HA で動体/人物イベントと静止画を使う。ライブは「未対応」と案内する。
2. **フルRE でネイティブ leo_rtc クライアントを実装**（大工数）。`signaling_servers` への到達性（LAN 直・`75.2.46.73`）を先に確認し、`rtc_protocol`/`rtc_crypto`/DTLS-SCTP を移植。着手するなら別作業ID・別容量計画へ切り出す。
3. **上流の対応待ち**。`mega-yfue/eufy-sdk` に leo_rtc live／RTSPブリッジが入るか、`fuatakgun/eufy_security` が新バックエンドに対応したら再評価。Renovate/issue で追跡する。
4. **機器側の変更**（ユーザー判断）。HomeBase S380 を足すと 24/7 録画＋RTSP 系の別経路が開く可能性（要確認）。容量・保存先は[I01](I01-resources.md)で別計画。

## 実機の確認状況と残作業（イベント経路の運用）

1. `sops platform/sops/eufy-security.sops.yaml` に `EUFY_USERNAME`・`EUFY_PASSWORD`・`EUFY_COUNTRY`（必要なら `EUFY_TRUSTED_DEVICE_NAME`）を入れる。2FAがあれば初回ログの確認コードを `docker compose logs -f` で見て、信頼端末を承認する。**資格情報・2FAコードはGit/ログ/この文書へ残さない。**（投入済み。CAPTCHA対策として保存セッションを消さない。）
2. `.venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/eufy-security-ws.yml` で起動し、healthyを確認する（配備済み）。イメージは `compose.lock.yaml` でdigest固定。
3. **設定 → デバイスとサービス → 統合を追加 → Eufy Security** でホスト `172.31.254.1`・ポート `3000` を指定する（追加済み。S4・SmartTrackを認識し、ログイン・デバイス一覧・Pushを確認）。**人物・動体イベントは取り込み済み（上記）。スナップショットは確認中。ライブ映像は上記の理由で当面「未対応」とし、有効化を案内しない。**既存録画・カメラ設定は変更しない。
4. WS/HAの再起動と一時切断後の再接続を確認し、WS・統合のメモリを[I01](I01-resources.md)の実測に足す。ライブは選択肢2/3の進展があれば再判断する。
5. HomeBase S380の追加は今回の範囲外。追加する場合は24/7録画と容量・保存先を別計画（[I01](I01-resources.md)）で確認する。
