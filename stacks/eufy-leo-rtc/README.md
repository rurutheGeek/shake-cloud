# eufy leo_rtc ネイティブクライアント

eufyCam S4（T8172）のような **単体バッテリーカメラ**のライブ映像を、スマホアプリと同じ
ネイティブ leo_rtc 経路で扱うためのリバースエンジニアリング実装です。計画・根拠・到達点の
正本は [H05 Eufy leo_rtc クライアント](../../docs/development/H05-eufy-leo-rtc.md)、
ライブ不可の経緯は [H04 EufyCam連携の検証](../../docs/development/H04-eufy.md) です。

状態: **実機でライブ映像・音声のデコードと配信に成功（2026-09-29）。**
`tools/leo_live.py` が wake〜ICE〜KCP〜メディア 1003〜受信を実行し、`vf_9061.bin`（映像）・
`vf_90e1.bin`（最終断片）・`vf_90ef.bin`（音声）を書き出します。映像は **P スライス＝平文 H.265、
I スライス（IDR）とパラメータセットは AES-128-GCM**（鍵 = セッションの `crypto_key`、IV =
`crypto_iv`）で、`leo_rtc/video.py` の `decrypt_idr`/`decrypt_parameter_nal` が復号します。
音声は別ストリーム（`90 ef`・ADTS AAC-LC 16kHz モノラル）で、同じ暗号を `leo_rtc/audio.py` が
復号します。各フレームの最終 FU 断片はマーカービット付き RTP（`90 e1`）で届き、再送に備えて
`(seq, ts)` の最近傍セットで重複除去します。
`tools/mjpeg_bridge.py` は捕捉を追記追従して MJPEG/RTSP に配信し（音声は `--audio-raw`）、
Mediamtx 経由で HA の generic camera / Frigate から参照できます。

- セッションは数十秒で切れることがあり（アプリは 0xce レポートで維持）、**wake
  リトライ**（映像が 25 秒来なければ新しい call を再送）と supervisor による自動再接続で補います。
  **周期的な media 1003 は送らない**（カメラがストリームを再開して参照が壊れます）。
- 残り: セッション寿命の延長（アプリは数分維持）・0xce レポートの自前生成・Mediamtx の配備。
- 上流（mega-yfue/eufy-sdk）への移植は fork のブランチで進行中（wire 層 12 モジュール＋
  `npm run verify` green。**許可が出るまで push しません**）。

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
| `leo_rtc/cs2.py` | CS2 P2P 独自ストリーム暗号（メディア層） |
| `leo_rtc/media_channel.py` | ANKExV4 メディアラッパー（keepalive/コマンドの組立・解析） |
| `leo_rtc/video.py` | RTP(PT97)/RFC7798 FU の再構成、IDR/パラメータの AES-GCM 復号、`(seq, ts)` 重複除去 |
| `leo_rtc/audio.py` | 音声 RTP(PT111) の ADTS AAC 復号（IDR と同じ鍵） |
| `leo_rtc/ice.py` | STUN 要求/応答（ICE の疎通確認） |
| `leo_rtc/kcp.py` | KCP チャネル（hello・ACK・push の再構成） |
| `leo_rtc/envelope.py` | XZYH＋AES-GCM のコマンド／メディア封筒 |
| `leo_rtc/report.py` | CS2 受信通知（DRWAck）の組立（RE 仕様） |
| `leo_rtc/__main__.py` | 開発用 CLI（`discover`・`wake`・`listen`） |
| `tests/test_eufy_leo_rtc.py` | オフラインの単体テスト（フレーミング・鍵導出・復号・境界） |
| `tools/leo_live.py` | 実機で wake〜受信を通し、`vf_*.bin`（映像/最終断片/音声）と `session_keys.json` を書く |
| `tools/live_supervisor.sh` | セッションを繰り返し、Mediamtx へ RTSP 配信する常駐ランナー |
| `tools/live_capture.py` | 旧: 映像 RTP を保存する開発用スクリプト |
| `tools/packets_to_annexb.py` | 保存したパケットを Annex B H.265 へ変換する（開発用） |
| `tools/mjpeg_bridge.py` | `vf_*.bin` を追記追従して MJPEG/RTSP 配信する（HA 橋渡し） |

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

ライブ映像の取得とデコード（開発用）:

```bash
cd stacks/eufy-leo-rtc
LEO_OUT=/tmp python3 tools/live_capture.py          # 映像 RTP を /tmp へ保存
python3 tools/packets_to_annexb.py /tmp/appstream.bin -o /tmp/live.h265
ffmpeg -i /tmp/live.h265 -fps_mode passthrough /tmp/live_%04d.png
```

## 配備（services-01・HA と同じホスト）

HA と同じ LAN に居ればよいので、常駐は services-01 の独立 Compose で動かす
（android-01 VM は開発・アプリ捕捉の作業台で、常駐先ではない）。

```bash
.venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/eufy-leo-rtc.yml
```

- `mediamtx`（RTSP。`172.31.254.1:8554` だけに開く＝HA の docker ゲートウェイ）と
  `leo-live`（クライアント＋スーパーバイザ）の 2 コンテナ。両方 `network_mode: host`。
- 秘密値は `platform/sops/eufy-security.sops.yaml`（EUFY_SN/DID/LICENSE/ACCOUNT/CONTACT）
  が正本で、Ansible が `/opt/services/eufy-leo-rtc/.env` へ流す。
- 状態（捕捉・鍵・スナップショット・sessions.csv）は
  `/srv/services/eufy-leo-rtc/state`。`manage.py status|logs|restart|down` で操作。
- HA のカメラ: `rtsp://172.31.254.1:8554/eufy`（映像のみ）＋
  `http://172.31.254.1:8888/snapshot.jpg`（カードの絵）。録画用は `eufy_av`（映像＋音声）。

## Home Assistant への配信

カメラはバッテリー機で、1 回の wake で数十秒〜数分だけ映像を流します。常駐
ランナーがセッションを繰り返し、Mediamtx 経由で RTSP を出します。

```bash
# Android 実機/VM（カメラと同じ LAN）で
python3 tools/leo_live.py                      # 1 セッション（vf_*.bin を書く）
# 常駐（Mediamtx は別途 :8554 で起動しておく）
LEO_OUT=/var/tmp/live bash tools/live_supervisor.sh
```

- `eufy`（映像のみ）: Home Assistant 用。HA のスナップショット（go2rtc の
  MJPEG）は音声トラックがあると失敗するため、HA へは映像だけを出す。
- `eufy_av`（映像＋音声）: 録画・NAS 用。`LEO_RTSP_AV=` を空にすると出さない。
- `snapshot.jpg`（毎秒 1 枚）を `python3 -m http.server` で配る: HA の
  `still_image_url` 用（`LEO_MJPEG_PORT`、既定 8888。`--snapshot` は ffmpeg の
  `mpjpeg` が 1 接続で終わるため使わない）。
- セッション後の待ちは `LEO_IDLE_WAIT`（既定 120 秒）。失敗が続くと倍々で最大 5 分。
- HA のストリームワーカーが RTSP を読みに来たら（`demand`）`LEO_DEMAND_WAIT`
  （既定 45 秒）で回す。実測: 2〜5 秒で再 wake すると 1 回の映像が短くなる
  （中央値 491 パケット）。120 秒空けると 5204。
- ブリッジは `session_keys.json` を読み、セッションが変わると鍵を読み直す。
- **ffmpeg に `-fflags nobuffer` を付けない**（H.265 の参照が壊れ、緑や欠けた
  フレームになる。実測で復号エラーが消えた）。書き出しは `-y` 必須。
- 先頭 IDR より前のスライスは捨てる（参照が無く復号できないため）。IDR が
  来るまで映像は出ないので、HA 側は数十秒待つことがある。

HA 側は Generic Camera（UI 専用）として登録する:

```bash
# services-01（HA ホスト）で
sudo python3 /opt/services/home-assistant/manage.py ensure-camera \
  --name 'eufyCam S4 (leo_rtc)' --stream rtsp://<leo_rtc ホスト>:8554/eufy \
  --still http://<leo_rtc ホスト>:8888/snapshot.jpg
```

- ライブ表示は HA の Generic Camera（go2rtc/WebRTC・HLS）が `eufy` を読む。
- カードの絵は `--still` の JPEG を使う（映像からの生成は go2rtc の MJPEG が
  音声で失敗するため）。

- セッションは数十秒で切れることがあり、切れている間 HA は「ストリームなし」
  になる。スーパーバイザが間隔を空けて起こし直す（失敗が続くと間隔を延ばす）。

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

1. 開始〜映像受信のフロー（ICE/KCP/メディア 1003）を作業機の一時スクリプトから
   `leo_rtc/` へ反映し、`wake` の後に映像を Annex B（または mp4）で書き出せるようにする。
2. パラメータセット（VPS/SPS/PPS）の配布経路を特定して自動取得にする
   （現在はアプリのメモリから取得した実測値を `video.py` に定数として保持）。
3. 欠落対策（約3重複の活用・受信バッファ拡大）で画質を安定させ、RTSP か HA のカメラへ橋渡しする。

試行錯誤の履歴は増やさず、結果は [H05](../../docs/development/H05-eufy-leo-rtc.md) の
「試したことと結果」に追記します。
