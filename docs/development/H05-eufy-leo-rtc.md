---
title: H05 Eufy leo_rtc ネイティブクライアント
updated: 2026-09-23
section: 開発計画
audience: 開発者
tags:
  - plan
  - home-assistant
  - reverse-engineering
---

# H05 Eufy leo_rtc ネイティブクライアント

> **更新日** 2026-09-23 ・ **区分** 開発計画 ・ **読む人** 開発者

これは開発計画であり配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。**H04 の「フルRE でネイティブ leo_rtc クライアントを実装」を別作業IDとして切り出したものです。** ライブ不可の根拠と失敗した経路は [H04](H04-eufy.md) が正本です。

## 目的・現状

**状態**: **wake と機器 ICE candidate の受信まで実機で確認（2026-09-23）。** 待機中の eufyCam S4（T8172）に対し、ネイティブ signaling の `priv1`（scall）で `100` → `200` を得て、機器の `addr`/`port` と TURN 資格が返るところまで動作しました。さらに機器は難読化なし・ヘッダ 0x3b の `info`（type 4）で **ICE candidate（host/srflx/relay）** を送り、アプリと同じ info 200 echo で ACK できます。実装は `stacks/eufy-leo-rtc/`（`leo_rtc` パッケージ＋開発CLI＋オフラインテスト）。**ICE（libjuice）＋KCP の確立と H.264/H.265 の受信が残り**、映像の HA 表示は未達です。

H04 の時点では `call` を送っても `480`（機器オフライン）でした。差分は次の4点で、`libmega_media_sdk.so` の解析から復元しました。

1. `priv1`/`priv_p2p` の JSON に **86 バイトの `sdp_info`**（ICE ufrag/pwd、メディア鍵・IV）を base64 で載せる（`WebrtcApp_SetCallSdp`、channel+0x75d8）。
2. call body の **+0x4b に `wakeup_type`** を入れる（`ProtocolSetCallBody2_reserved`。アプリはバッテリー機で 1 を使う）。
3. `priv_p2p` の JSON に **`boot_action`** を入れる（`ClientSendCall` case 6、`client+0x3bb`）。
4. ヘッダ **+0x12=1**（attach 暗号化）と **+0x0f** のネットワーク種別。

シグナリングのログインは機器の `p2p_did` と `p2p_license` だけで成立し、**Eufy アカウントのログインは不要**です。H04 の教訓（同一アカウントの別ログインで `eufy-security-ws` の v6 push トークンが失効する）を踏まえ、この経路はアカウントへ触れません。

## 配置と開発範囲

- **開発・検証は dev-b。** 常駐サービスは作りません。`stacks/eufy-leo-rtc/` の CLI を必要なときだけ実行します。
- 容量: **追加なし**（既存 dev-b の範囲。CPU・RAM・ディスクの新規予算は要求しません）。[I01](I01-resources.md) への追加実測も不要です。
- 資格情報: `EUFY_DID`・`EUFY_LICENSE`・`EUFY_ACCOUNT` は `stacks/eufy-leo-rtc/.env`（0600）か環境変数だけに置きます。**Git・ログ・チャットへ残しません。** `.env.example` は空の雛形です。常設運用にする場合は H04 と同じく `platform/sops/eufy-security.sops.yaml` へ追加し、`.env` へは配備時にだけ展開します。
- 既存の `eufy-security-ws`（イベント・Push・スナップショット）と Eufy アプリ・録画・カメラ設定は変更しません。
- RE の生成物（APK・Ghidra プロジェクト・ダンプ）は従来どおり作業機の一時領域に置き、Git へ入れません。

## 実装手順

1. `stacks/eufy-leo-rtc/` の `discover` でサーバ一覧とログインを確認する（`python3 -m leo_rtc discover`）。
2. `wake` で `priv1` scall を送り、`code=200` と `addr`/`port`・`turn` を確認する（`python3 -m leo_rtc wake --wait 45`）。
3. `priv1` の `100` で始まる機器の info（type 4・ヘッダ 0x3b）を復号し、candidate を ACK して集める（`ack_info`・`collect_candidates`）。
4. candidate を libjuice（または `node-datachannel`）へ渡し、共有 ICE 資格で connectivity check を通して KCP/DTLS を確立する。
5. ペイロードを `sdp_info` の `crypto_key`/`crypto_iv`（AES-GCM）で復号し、H.264/H.265 を受信・保存する。
6. 受信映像を RTSP か HA のカメラへ橋渡しし、遅延・再接続・バッテリー消費を測る。

## 依存と並列作業

- 開発開始: 実機の S4 と機器の `p2p_did`/`p2p_license`（クラウド応答）が必要。H04 の解析成果が出発点。
- 配備・切替: いまは無し（dev-b の開発のみ）。HA へ映像を出す段階で [H01](H01-home-assistant.md)・[N03](N03-vlan.md) と調整し、容量は [I01](I01-resources.md) で測る。
- 競合: `eufy-security-ws` は触らない。検証でアカウントログインをしない（共有ユーザーを使う場合も H04 の注意に従う）。

## 検証・完了条件

- wake は `code=200` の応答（`addr`・`port`・`turn`）で判定し、終了時に `hangup` を送る。バッテリーを無駄に消費しない。
- SDP/ICE・メディアが通ったら、遅延・解像度・再接続・バッテリー消費を記録する。未対応の機能を「利用可能」と案内しない。
- 資格情報と映像が許可外へ公開されない。既存アプリ・録画が継続する。
- `tests/test_eufy_leo_rtc.py` がフレーミング・鍵導出・境界・秘密値の非混入を検査する。実機へ接続するのは CLI 実行時だけ。

## 実機の結果（2026-09-23）

- `discover` → `login` → `priv1` scall（`boot_action=1`・`wakeup_type=1`・`sdp_info` 86B）で、待機中の S4 が **0.2 秒で `100`、約 4 秒で `200`** を返した。200 の attach には `addr`・`port`・`srfix`・`srflx`（クライアントの公開アドレス）・TURN 資格（`turn_addr`/`turn_user`/`turn_password`）が入っていた。
- `priv1` を送らない、または `sdp_info` が無い場合は `480` のまま（H04 の再現）。`priv_p2p` だけでは 200 にならない。
- ログインは機器の DID/license のみ。同じ端末から短時間に再ログインすると 401 が返ることがあり、CLI は挑戦を最大3回まで再試行する。
- カメラは wake 後 **LAN 上で ICMP に応答する**（実測 `192.168.10.98`、MAC `2c:8d:48:2c:5a:33`）。クラウド記録の `192.168.10.4` は古い値。wake 前は ARP も解決しない。

### 機器の info メッセージ（2026-09-23 判明）

`priv1` の `200` を受けると、機器は **type 4（info）** を繰り返し送ってくる。このメッセージは難読化エンベロープ無しで、**ヘッダが 0x3b バイト**（アプリは 0x3c）という差異がある。body の長さと `len(inner) - 0x3b` の一致で判別できる。body の attach（AES-ECB、鍵はセッション鍵）を復号すると、機器の ICE candidate が入っている:

```
{"file_candidate": "a=candidate:1 1 UDP 2122317823 192.168.10.98 50268 typ host", "file_candidate_num": 0}
{"file_candidate": "a=candidate:2 1 UDP 1686109951 106.72.178.128 4674 typ srflx raddr 0.0.0.0 rport 0", ...}
{"file_candidate": "a=candidate:3 1 UDP 8388095 <relay> 24114 typ relay raddr 0.0.0.0 rport 0", ...}
```

アプリは各 info リクエストへ **info 200**（type 4・resp=1・code=200）で応答し、body の先頭 0x4c バイト（uuid/contact）と復号済み attach をそのまま再暗号化して返す（`ClientHandleInfo`）。応答が無いと機器は candidate を約 100ms 間隔で再送し続ける。

### メディア経路（解析）

`WebrtcApp_Event_RtcTrying` は **priv1 の `100`（trying）で `file_agent_start`** を呼ぶ。file agent は `datachannel_manager_kcp.c` の実装で、**libjuice（ICE）＋ KCP**、TURN は 200 の資格、ICE ufrag/pwd は `sdp_info` の値を使う。SDP は固定テンプレートで **SDES-SRTP（鍵はバイナリ内にハードコード: `inline:FvLcvU2P3ZWmQxgPAgcDu7Zl9vftYElFOjEzhWs5`）**、映像は H.264（PT 99）／H.265（PT 97）＋ flexfec（125）、音声は opus（111）。つまり標準 WebRTC の DTLS ではなく、**事前共有した ICE 資格＋固定 SRTP 鍵**の独自スタック。フレーム暗号（`rtc_crypto_decrypt_video_frame`、AES-GCM）は `sdp_info` の `crypto_key`/`crypto_iv` を使う。

`stacks/eufy-leo-rtc/leo_rtc/media.py` に SDP テンプレートと SDES 鍵、`client.py` に info の復号・ACK（`ack_info`）・candidate 収集（`collect_candidates`）を実装済み。

### アプリ実機キャプチャ（2026-09-23、Waydroid VM `android-01`）

Eufy アプリ 6.0.90 を Waydroid（libndk・ARM 変換）で動かし、**共有端末**として共有されている S4（アプリ表示名「リビング」）のライブ画面を開いた。Frida はアプリのアンチデバッグ（attach で `signal 6`）で使えないため、**waydroid0 上の tcpdump** でアプリの通信を取得した。アプリ自身の再生は ARM 変換側の問題で「Connection failed」になったが、**ネットワーク上はカメラが映像を配信していた**。

- **シグナリング（mega サーバ `18.197.113.4:5062`）**: pcap の 1049 パケットを `leo_rtc.protocol.deobfuscate`＋`parse_header` で**全件 CRC 一致で復号**できた。内訳は call（code 0/100/200）・info（code 0/200/1485）・ack・report。`call`/`info` の attach は `encrypted=1` で、アプリがログイン時に生成したセッション鍵のため復号できない（アプリの `sdp_info` の平文は取れない）。
- **メディアは ICE ペア上の素の RTP**: カメラ `192.168.10.98` からアプリの ICE ポートへ **RTP PT97（H.265）** が 7917 パケット流れた（SSRC `0x0dc1a815`、RTP 拡張プロファイル `0xbede`・長さ 2）。ペイロードは NAL ヘッダ（VPS/SPS/PPS/FU/SEI）が見えるが、**本文はアプリの `sdp_info` 鍵で暗号化**されている（ffmpeg で復号不可を確認）。KCP はメディアではなくファイル/制御用とみられる。
- **ICE/TURN**: アプリはカメラ自身の **TURN サーバ（`192.168.10.98:3478`）** に allocate し、relay ポート（例 48211）で STUN binding/メディアを通した。公開 TURN（`75.2.46.73:3478`）も併用。STUN は libjuice（SOFTWARE `libcoreice`）。
- **制御**: カメラの制御ポート（例 `192.168.10.98:45255`）へ **`ANKExV4`** を含む 32 バイトのキープアライブを送り続ける（同一内容の繰り返し）。カメラのペイロード内に `Hello,Axera!`（Axera SoC の SEI）を確認。
- 取得物: pcap と H.265 Annex B 変換（復号は鍵待ち）は作業機の一時領域のみに置き、Git へ入れない。

## 残作業

1. **ICE の確立（2026-09-23 実機で成功）**: カメラは **`sdp_info` の ufrag/pwd をそのまま採用**し（`USERNAME` が `ufrag:ufrag`、MESSAGE-INTEGRITY も自前 pwd で一致）、クライアントが **自候補を info で送ると** binding request を送ってくる。実装上の必須事項:
   - 要求には **ベンダー属性 `0xC057`（値 `00 01 00 00`）** が必要（無いと 400 Bad Request）。
   - **`USE-CANDIDATE` を付けると 400**。付けない要求に `0x0101` 成功が返る（カメラ側が controlled で nominate する実装）。
   - 応答（`0x0101`）は XOR-MAPPED-ADDRESS＋MESSAGE-INTEGRITY＋FINGERPRINT で返す。動作確認済みの実装は作業機の一時スクリプトのみ。
2. **ストリーム開始コマンド（XZYH）**: ICE が通っても、コマンドを送るまでカメラは RTP を流さない（実測: 成功後 70 秒待っても RTP なし）。pcap から、アプリは **メディアの ICE 5-tuple 上**へ `XZYH` フレームを送っていることを確認した。
   - フレーム: `XZYH`(4) ＋ cmd(u16 LE) ＋ 長さ(u16 LE) ＋ `00 00` ＋ `0a 00 00 01 00 00`（12 バイトヘッダ）＋ ペイロード。ICE ペア上のパケットは先頭に 32 バイトのプレフィックス（後述の KCP と同じ）が付く。
   - **開始コマンドは cmd 0x0546・ペイロード 563 バイトで、ペイロードは暗号化**（エントロピー 7.57、可読文字なし＝`rtc_crypto_encrypt_cmd_data` 相当）。カメラは同じ cmd 0x0546 を 84 バイトで返し、中にクライアントのアドレス文字列（`...112`）が平文で入る。
   - 他の XZYH: 0x03ec（アプリ→カメラ、84 バイト）、0x0473（データチャネル hello、16 バイト）。
   - **KCP データチャネル**は別の ICE セッション（同じ `sdp_info` 資格・別ポート）で、UDP ペイロード先頭に **32 バイトのプレフィックス**（u32 conv＝KCP conv、u32 1、24 バイト 0）＋ KCP ヘッダ（conv/cmd/frg/wnd/ts/sn/una/len、LE）が続く。カメラは `00 01 00 00` のハートビート（"heartbeat"）を cmd 0x0001 で返す。
   - **暗号方式**: `rtc_crypto_encrypt_cmd_data`（119722 行）は **AES-128-GCM**（鍵 16 バイト＝**クライアントコンテキスト +0x34**、IV 12 バイト乱数、AAD `"eufy security"`、タグ 16 バイト）。出力は「16 バイトヘッダ＋タグ 16＋IV 12＋カウンタ 4＋暗号文」で、ヘッダの長さは暗号文長 + 0x20。
   - 鍵の候補は `WebrtcApp_SetCallSdp`（148104 行）が生成して `sdp_info` に入れる `crypto_key`（16 文字、`crypto_generate_str`）。`ClientHandleInfo` は相手の `crypto_key`/`crypto_iv` を info JSON から読んでコールバックへ渡す（＝相手方向の鍵は info で届く）。ログインの `generate_aes_key`（セッション鍵）とは別物。
   - **32 バイトの comm_head**: `9ecc 0098 <u32 SSRC> "ANKExV4\x12" 00000000 01ffffff 43 <counter> 0100`（アプリ側）。カメラ側は先頭 `80cc 0014`・チャネル名 `"AZWCxV4\x12"`・SSRC は RTP と同じ値。XZYH フレームはこの 32 バイトの後ろに置かれる。
   - **試行結果（未解決）**: `sdp_info.crypto_key` を鍵に 0x0546 を送る／pcap のアプリフレームをそのまま replay する／32B プレフィックスの長さを自フレーム用に直す、のいずれも**カメラ応答なし**。ICE は成立し、camera の check にも応答済み。カメラは 0x0546 を処理していない。
   - **KCP データチャネル（判明）**: 32 バイトのプレフィックスは `u32 conv（1=app→cam, 3=cam→app）＋u32 1＋24 バイト 0`。続く KCP ヘッダは conv(u32)・cmd(u8: 0x51 PUSH/0x52 ACK)・frg・wnd(u16)・ts(u32)・sn(u32)・una(u32)・len(u32)、ペイロードが len バイト。アプリの hello は `XZYH cmd 0x0473`（16 バイト）を **24 バイトの notify ヘッド**（`u16 type=9, u16 head_len=24, u32 payload_len, u32 channel=1, u32 ts, u32 1, u32 0`）付きで KCP PUSH（sn=0）に載せる。カメラは conv=3 の PUSH で `XZYH cmd 1`（"heartbeat"）を返す。
   - メディアの 5-tuple は **STUN／KCP／RTP(PT97)／RTCP(90ce/90ef/b0ce)／ANKExV4 付き XZYH** を多重化する。XZYH コマンドは KCP ペイロードでも ANKExV4 付きでも流れる。
   - **残る不明点**: (a) ANKExV4 プレフィックスの seq/flags/長さフィールドの意味（パック層のみ、`decomp*` に文字列なし）、(b) コマンド暗号鍵の設定元（クライアント ctx+0x34）、(c) アプリの 0x0546 平文は 531 バイト（自前 SDP は 1369 バイトで大きすぎる可能性）、(d) KCP hello を送ってもカメラが ACK を返さない理由（セッション状態・鍵）。
   - **外部 RE との整合（2026-09-23 発見）**: [HallyAus/Eufy-Home-Assistant](https://github.com/HallyAus/Eufy-Home-Assistant) が S4 世代（NVR T8N00）の WebRTC を RE し、`docs/PROTOCOL.md` で **XZYH 16 バイトヘッダ**（`command_id` u16＝**1350**、`param_len` u32、payload は JSON `{"account_id","cmd","payload"}`）と、コマンド一覧（**1103=getCameraParams / 1003=startStream / 1004=closeLive / 1139=heartbeat**、映像は command_id 1300 系で `[XZYH][22B media header][Annex-B H.265]`）を公開している。同世代でコマンド層は共通とみられる（NVR は DTLS/SCTP、本機は libjuice ICE＋KCP＋ANKExV4）。
   - **コマンド暗号鍵の入手経路（判明）**: `WebrtcApp_Event_LoginSuccess`（`decomp_all_r.c` 146591 行）が RTC ログイン成功時に **クライアント ctx+0x34 のコマンド鍵**を設定する。鍵の実体はイベントデータ +0x300（16 バイト）で、これは `ClientHandleInfo` が **info メッセージの JSON の `crypto_key`** を読んで格納したもの。つまり**コマンド鍵は機器が info で送ってくる**（ログ: `set aes[%s] ... quick_aes_key[%d]`）。同 info には `sdp`・`candidate`・`crypto_iv` も入り得る。
   - **未取得**: こちらの wake セッションでは info メッセージは candidate（code 0）のみで、`crypto_key` を含む info がまだ来ていない（アプリ側では code 1485 の info が多数あった）。機器に鍵を送らせる条件（コマンド要求か、ストリーム開始後か）の特定が次の作業。鍵さえ得られれば `cmd 1003 startStream` の JSON を AES-128-GCM で暗号化して送れる。
   - 参考: Web クライアント（NVR）経路は [HallyAus/Eufy-Home-Assistant](https://github.com/HallyAus/Eufy-Home-Assistant) が完成実装を公開（aiortc＋libsctp WASM＋`build_openlive`/`build_startstream`）。本アカウントは共有メンバーのため Web の station_list が null で、この経路は共有端末には使えないことを実測で確認した。
   - **KCP 疎通に成功（2026-09-23）**: ICE 後に 32B プレフィックス＋KCP PUSH（conv=1、`ts=0`、sn=0、payload=`notify ヘッド＋XZYH cmd 0x0473`）を送ると、カメラが **KCP ACK（conv=1, cmd 0x52）** を返し、続けて **conv=3 の PUSH（XZYH cmd 1＝"heartbeat" を含む 52B）** を送ってくる。KCP チャネルは確立できる。
   - **KCP 上のコマンドは未応答**: hello 後に `cmd 1103/1003` の JSON を (a) KCP ペイロード（平文）、(b) ANKExV4 プレフィックス＋AES-128-GCM（自前 sdp_info 鍵）、の両方で送ったが応答なし。暗号鍵は機器の `crypto_key`（info メッセージ）であり、これが未取得のため本命の (b) が復号されない可能性が高い。
   - カメラはバッテリー式のため wake 後の応答が不安定で、KCP の ACK が返る回と返らない回がある（セッション状態・スリープの影響）。
   - **後継 SDK の実機テスト（2026-09-23）**: `@mega-yfue/eufy-sdk` v0.2.0 を dev-b（Node 24.21）で実行。ログイン成功（captcha 不要）、S4 を `camera` 能力付きで認識（`live()`/`snapshotLive()` あり）。しかし `live()` は `session-connect-wait` → **P2P connect timeout**（ログ: `stationModel: T8172`・`topology: own`・`stationAdmin: other`）。SDK のライブは従来 PPCS P2P 実装で、**新 leo_rtc 方式の S4 には未対応**。SDK リポジトリに T8172/新方式の issue は未登録。
   - コマンド鍵の候補（`sdp_info.crypto_key`・ログインセッション鍵・その MD5・実 `user_id` 付き JSON）はすべて無応答。機器の `crypto_key`（info メッセージ）が未取得のまま。
3. **メディア受信**: ICE ペア上の RTP（PT97 H.265）を受け、フレームを復号する。`rtc_crypto_decrypt_video_frame`（`decomp_all_r.c` 119494 行）から判明した方式は次のとおりで、**鍵は `sdp_info` 直載せではなく ECIES（micro-ecc）でフレームごとに配送**される。
   - フレーム（`param_2`）のレイアウト: `+0x16` に 0x81（129）バイトの ECC ブロブ、`+0x97` に GCM タグ 16 バイト、`+0xa7` に IV 12 バイト、`+0xb3` から暗号文。AAD は固定文字列 `"eufy security"`（13 バイト）。
   - 鍵: `DecryptECC(frame+0x16, 0x81, out, &outlen, client_ecc_private)` の出力先頭 32 バイト。ECC は `uECC_make_key`／`uECC_decompress`（micro-ecc、`uECC_bytes()=0x20`、`uECC_curve()=3`）で、クライアント公開鍵は `rtc_crypto_get_ecc_crypto` が 0x40 バイトを 16 進文字列化して返し、シグナリングで機器へ渡す。
   - 復号本体: `aes_gcm256_decrypt_media`（同 83059 行）＝ AES-256-GCM、IV 12 バイト、タグ 16 バイト、AAD `"eufy security"`。主鍵で失敗すると機器のバックアップ鍵で再試行する実装。
   - RTP 側は NAL ヘッダ（VPS/SPS/PPS/FU/SEI）が平文で見える一方、**本文は上記暗号**。SEI（`Hello,Axera!`）は平文で届く。パラメータセット単体を ffmpeg に掛けると解析不能（暗号化の裏付け）。
   - 次段: ECIES の KDF（`kdf_func`／`derive_S_DeCompFrom_PRI`）と曲線を確定し、Python（`cryptography` の P-256／secp256k1 実装）で再実装する。自前の ECC 鍵を `sdp_info` 経由で送れば、自セッションのフレームを復号できる。

### 鍵配送とライブ復号（2026-09-23 判明）

ライブ系（`zx_p2p_media_read_*`）は RTC の ECIES とは別に **P2P agent** の鍵交換を使う。

- クライアントは `zx_p2p_get_crypto` で **RSA-1024 鍵対**を生成し、公開鍵（`BN_bn2hex` の modulus 文字列）を保持。`zx_p2p_get_ecc_crypto` では micro-ecc の鍵対を生成し、公開鍵 0x40 バイトを `%02X` で 128 文字の hex にする。
- これらの公開鍵は `cmd_sender_send_command`（`decomp_all_r.c` 122210 行〜）で**コマンドフレーム**に載り、`rtc_client_write`（クライアントソケット＝シグナリング）で機器へ送られる。0x400/0x401/0x46c/0x4bf/0x4c0/0x4c1/0x586 の各ケースが ECC 公開鍵を含む。
- コマンドフレームは 0x195（405）バイト: 先頭 0x15 バイトのヘッダ（+0x06 に長さ 0x185、+0x0c に 0xff とストリーム種別）、+0x15 から `sn`（0x7f）、+0x94 から `account`（0x7f）、+0x113 の 2 バイト、**+0x115 から ECC 公開鍵 hex（0x80 バイト）**。
- ライブ映像の復号は `zx_p2p_media_read_video_decrypted`（93328 行）: 機器が送る **RSA-1024 暗号文 0x80 バイト**を `p2p_agent_rsa_decrypt` で復号して AES 鍵を得て、フレーム先頭 **0x80 バイトを AES でその場復号**する。フレームは 0x16 バイトの comm_head の後ろが本体（`zx_p2p_media_read_video_manager` 呼び出しで `data+0x16`, `size-0x16` を渡している）。
- ダウンロード／履歴系は `rtc_crypto_decrypt_video_frame` の ECIES 経路（前述）。**ライブとダウンロードで鍵方式が異なる**点に注意。
- 次段: 上記コマンドフレームを `leo_rtc` から送れるようにし、RSA/AES と ECIES/GCM の両方を Python で実装して、ICE 上の RTP を復号する。
4. **裏取り**: 上記キャプチャで handshake のネットワーク挙動は取れたため、アプリ内の `boot_action` 等の平文は必須ではない。必要になった場合のみ所有者の実機で確認する。
5. **橋渡し**: RTSP publish か HA カメラ統合への接続。採用は H01 と調整する。
