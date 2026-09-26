# eufy leo_rtc ネイティブクライアント

eufyCam S4（T8172）のような **単体バッテリーカメラ**のライブ映像を、スマホアプリと同じ
ネイティブ leo_rtc 経路で扱うためのリバースエンジニアリング実装です。計画・根拠・到達点の
正本は [H05 Eufy leo_rtc クライアント](../../docs/development/H05-eufy-leo-rtc.md)、
ライブ不可の経緯は [H04 EufyCam連携の検証](../../docs/development/H04-eufy.md) です。

状態: **wake と機器 candidate の受信まで実機で確認（2026-09-23）。** `priv1`（scall）に
86 バイトの `sdp_info` を載せて送ると、待機中の S4 が `100` → `200` を返し、機器の
`addr`/`port` と TURN 資格を返す。さらに機器は難読化なし・ヘッダ 0x3b の `info`（type 4）で
ICE candidate（host/srflx/relay）を送り、アプリと同じ info 200 echo で ACK できる
（`ack_info`・`collect_candidates`）。ICE（libjuice）＋KCP の確立と H.264 の受信は未実装。

## 何をするか

`libmega_media_sdk.so`（APK `com.oceanwing.battery.cam` 6.0.90）の解析結果を Python へ
移植したシグナリングクライアントです。UDP の独自バイナリ（`rtc_protocol`）で
discover → login → call を行い、RSA+AES でセッション鍵を共有します。

- 対象: 単体運用の eufy バッテリーカメラ（`p2p_conn` が空で `signaling_servers` を持つ機種）
- 非対象: HomeBase 配下のカメラ、旧 ThroughTek P2P 機（既存 `eufy-security-ws` の担当）
- ライブ映像のイベント・Push・スナップショットは既存の `eufy-security-ws` を維持します。
  このスタックは置き換えではなく、ライブ映像だけを補う開発中の実装です。

## 安全上の約束

- **Eufy アカウントでログインしません。** シグナリングのログインは機器の
  `p2p_did`（DID）と `p2p_license`（LICENSE）だけで成立します。同じアカウントで
  別クライアントがログインすると `eufy-security-ws` の v6 push トークンが失効する
  ため（[H04](../../docs/development/H04-eufy.md)）、この経路を使います。
- DID・LICENSE・ACCOUNT は `.env`（0600）か環境変数だけに置き、Git・ログ・文書へ
  残しません。`.env.example` は空の雛形です。
- 実機のカメラを起こすとバッテリーを消費します。検証は必要な時間だけにし、
  終了時に `hangup` を送ります。
- 既存の Eufy アプリ・録画・カメラ設定は変更しません。

## 構成

| ファイル | 内容 |
| --- | --- |
| `leo_rtc/protocol.py` | 0x3c ヘッダ、CRC16/XMODEM、難読化エンベロープ、call body |
| `leo_rtc/crypto.py` | 鍵導出、AES-ECB、RSA ログイン応答 |
| `leo_rtc/sdpinfo.py` | 86 バイトの `sdp_info`（ICE ufrag/pwd、メディア鍵・IV） |
| `leo_rtc/media.py` | 機器側 SDP テンプレートと SDES-SRTP 鍵（解析結果） |
| `leo_rtc/client.py` | discover / login / call / info / hangup、info ACK、candidate 収集 |
| `leo_rtc/__main__.py` | 開発用 CLI（`discover`・`wake`・`listen`） |
| `tests/test_eufy_leo_rtc.py` | オフラインの単体テスト（フレーミング・鍵導出・境界） |

## 使い方（dev-b）

DID・LICENSE は機器のクラウド応答（`p2p_did`・`p2p_license`）から取得し、
`stacks/eufy-leo-rtc/.env`（0600）へ置きます。**値は Git へ入れません。**

```bash
cd stacks/eufy-leo-rtc
python3 -m leo_rtc discover          # サーバ一覧とログイン確認
python3 -m leo_rtc wake --wait 45    # priv1 scall で wake、応答を表示
```

`wake` が `code=200` と `addr`/`port`・`turn` を含む JSON を表示すれば wake 成功です。
カメラが眠ったまま・拒否した場合は `no 200 answer` で終了します。

## Eufy アプリの logcat 取り方（ハンドシェイク確定用）

推測を消すため、実機スマホの Eufy アプリがライブ表示中に出すネイティブログを
取ります。dev-b に `adb` を入れてあり（`~/.local/platform-tools/adb`）、同じ LAN なら
**無線デバッグ**で PC なしで取得できます。

1. スマホ: 設定 → 開発者向けオプション → 「ワイヤレスデバッグ」を ON。
2. スマホ: 「ペア設定コードによるデバイスのペア設定」を開き、**IP:ポートと6桁コード**を確認。
3. dev-b:
   ```bash
   ADB=~/.local/platform-tools/adb
   $ADB pair <スマホIP>:<ペアポート>     # 6桁コードを入力
   $ADB connect <スマホIP>:<デバッグポート>  # ワイヤレスデバッグ画面のIP:ポート
   $ADB devices
   $ADB logcat -c
   $ADB logcat -v time > /tmp/eufy-live.log
   ```
4. スマホ: Eufy アプリで該当カメラのライブ映像を開き、10〜15秒待って閉じる。
5. dev-b: Ctrl+C で停止し、次で絞り込む:
   ```bash
   grep -E 'WebRTC APP|EVENT:SetSDP|sdp\[|ice_ufrag|ice_pwd|file_agent|datachannel|NEWSDK|leo_rtc|WakeUpType|boot_action|NewSetRemoteSDP|ice-u|ice-p' /tmp/eufy-live.log
   ```

見たい行: `boot_action`/`wakeup_type` の実際値、アプリのローカル SDP（`EVENT:SetSDP ... sdp[...]`）、
機器 SDP の `ice-u`/`ice-p`、`file_agent_start` の `ice_ufrag`/`ice_pwd`/`kcp_type`、
`datachannel_*` の確立ログ。**取れたファイルは Git へ入れないでください**（DID・鍵を含む可能性）。

注意: アプリの利用で `eufy-security-ws` の v6 push トークンが回ることがあります。通知が
止まったら [H04](../../docs/development/H04-eufy.md) の `manage.py reset-mega-session` で復旧します。

## 検証

リポジトリのルートで実行します。

```bash
python3 -m unittest discover -s tests -p 'test_eufy_leo_rtc.py'
```

実機へ接続するのは `python3 -m leo_rtc ...` を実行したときだけです。通常のテストは
ソケットを開きません。

## 次の作業

1. 収集した candidate を libjuice（または `node-datachannel`）へ渡し、`sdp_info` の共有
   ICE 資格で connectivity check を通す（candidate 番号ごとの ACK も実機で詰める）。
2. KCP/DTLS 越しのペイロードを `sdp_info` の `crypto_key`/`crypto_iv`（AES-GCM）で復号し、
   H.264/H.265 を再構成して ffmpeg へ渡す。
3. 受信した映像を RTSP か HA のカメラへ橋渡しする（[H05](../../docs/development/H05-eufy-leo-rtc.md) の完了条件）。
