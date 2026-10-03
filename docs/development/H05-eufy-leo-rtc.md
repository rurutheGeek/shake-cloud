---
title: H05 Eufy leo_rtc ネイティブクライアント
updated: 2026-10-02
section: 開発計画
audience: 開発者
tags:
  - plan
  - home-assistant
  - reverse-engineering
---

# H05 Eufy leo_rtc ネイティブクライアント

> **更新日** 2026-10-02 ・ **区分** 開発計画 ・ **読む人** 開発者

これは開発計画であり配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。**H04 の「フルRE でネイティブ leo_rtc クライアントを実装」を別作業IDとして切り出したものです。** 公開ソフトでのライブ不可の根拠は [H04](H04-eufy.md) が正本です。

**プロトコル仕様・鍵・暗号・シーケンス・試行錯誤の詳細は、RE 用の別リポジトリ `eufy-leo-rtc-re`（`docs/protocol.md`・`docs/keys.md`・`docs/crypto.md`・`docs/sequences.md`・`docs/history.md`）が正本です。** この文書は計画と現在地だけを持ちます。

## 目的と現在地

単体運用の eufyCam S4（T8172）のライブ映像を、スマホアプリと同じネイティブ leo_rtc 経路で受信し、Home Assistant で見られるようにします。既存の `eufy-security-ws`（イベント・Push・スナップショット）は置き換えません。

**状態（2026-09-29）**: **自前クライアントで受信したライブ映像のクリーンなデコードに成功**（1280x720・61フレーム。部屋とOSDをレビューで目視確認）。Pスライスは平文・IDRのみ AES-128-GCM（鍵=`crypto_key`、IV=`crypto_iv`）と確定。残りは**捕捉時のパケット欠落の解消（連続ストリーム化）**と HA 橋渡し（MJPEG/RTSP）。**HA 表示は未達。**

## できていること（実機で確認済み）

1. **シグナリング（Eufy アカウント不要）** — 機器の `p2p_did`/`p2p_license` だけで discover → login → `priv1` scall が通り、待機中のカメラが `100` → `200` を返す（0.2 秒 / 約 4 秒）。`sdp_info`（86 バイト）が必須。
2. **機器の info（type 4）** — 難読化なし・ヘッダ `0x3b` で ICE candidate が届く。アプリと同じ info 200 echo で ACK。**call が `200` になる前の info は `480`。**
3. **ICE** — `ICE-CONTROLLING`（`0x802a`）＋`USE-CANDIDATE`（`0x0025`）＋ベンダー属性 `0xC057` で 5-tuple が確立する（`0x8029` ではカメラが check を返さない）。
4. **KCP** — 32B プレフィックス＋KCP PUSH（conv=1、24B notify＋XZYH）。**sn 増分と una が前提**（簡易実装では会話が続かない）。
5. **コマンド受理（2026-09-27）** — 鍵は `sdp_info.crypto_key`（チャネルごと）。`1306` → `code 0`、ライブ開始 `1003`（XZYH 0x546 封筒＋JSON）→ `code 0`＋カメラ `1351`（`live_stream` 承認）。
6. **映像開始トリガと CS2 層（2026-09-28）** — ①映像を開始させるのは **メディアチャネル（ANKExV4）側の 1003**（KCP 側だけでは映像は始まらない。アプリ実測: 送信 +0.02 秒でカメラ `80cc` → +0.22 秒で映像）。②メディア側のペイロードは **CS2 P2P（ThroughTek 系）の独自ストリーム暗号**で、鍵は `crypto_key`、テーブルは .so 内の 256B（詳細は RE リポ `docs/crypto.md`）。③カメラ→アプリの映像は**平文 H.265**（`9061…` 1166B、先頭 SEI `Hello,Axera`）。
7. **ログイン応答の AES 部は 48 バイト**（2026-09-28）— 48B にするとサーバが**ランダム 32hex の contact** を返し（16B では SN）、この条件で **priv_p2p 鍵がカメラのメディア ctx に登録**（`1003` が `-110`→`-104` 復号成功）することを実機確認。
8. **映像の実体と暗号（2026-09-29 確定）** — RTP（PT97・SSRC `0dc1a815`・拡張 `0xbede`・ヘッダ24B、重複約3）＋RFC7798 FU（`62 01`）。**Pスライスは平文、IDR（Iスライス）のみ AES-128-GCM（AADなし、鍵 = `sdp_info.crypto_key`、IV = `sdp_info.crypto_iv`）**。ワイヤ形式は `[NAL 2B][暗号文][GCMタグ16B][トレーラ9B]`、VPS/SPS/PPS も同鍵で暗号化。旧「E2E（AES-256-GCM）」は録画/ダウンロード系でライブには誤り。
9. **★クリーンなデコード成功（2026-09-29）** — 1280x720・61フレーム（部屋・OSD「Sep 29 2026 04:35:02 PM」まで判読）。旧破損の原因は ①各フレームの最終 FU 断片が markerビット付き RTP（`90 e1`）で届くのを見落とし ②単一NAL（`02 01`）をデパケットしていなかったこと。`leo_rtc/video.py` の `decrypt_idr`/`decrypt_parameter_nal`・`tools/packets_to_annexb.py`・`tools/mjpeg_bridge.py` で実装。
10. **残り** — 捕捉時のパケット欠落（IDR 10本中7本が seq ギャップ）をドレイン強化で解消し、連続ストリーム → HA（MJPEG/RTSP）。成果物は Nextcloud `inbox/eufy-leo-rtc/`。

## 鍵とフレームの要点

- コマンド暗号: AES-128-GCM、鍵 = `sdp_info.crypto_key`、AAD `"eufy security"`、フレームは `[XZYH 16][tag 16][iv 12][counter 4][暗号文]`（**tag は先頭**）。
- `sdp_info[0x05]` = key_mode（アプリ実測 6。0 は invalid）。notify の `[20:24]` = KCP sn。
- カメラ応答も同一鍵・形式で、IV はクライアントの `crypto_iv` をエコーする。
- - **採用構成（2026-09-29 夜）**: `DRWAck（自前・cmd 0xd1）＋ wake リトライ（25 秒無映像で新 call 再送）＋ 受信バッファ 16MB ＋ (seq,ts) 重複除去 ＋ IDR/パラメータ/音声の AES-128-GCM 復号`。**周期的な media 1003 再送は禁止**（カメラがストリームを再開＝seq リセットして参照が壊れる。外したら 5 セッション連続で runs=1・欠落 0・IDR 100%）。35 分試験で **29 セッション中 26 で映像（90%）・3478 フレーム（約 231 秒）・IDR 136/163 復号**、うち 8 セッションは欠落ゼロ。**アプリの `f1ce` レポートのリプレイは廃止**（テンプレートを自前値で埋めた自前レポートはカメラが映像を止めるため。完全な形式解読が課題）。**再送を促す仕組みが残課題**（アプリ版は再送で欠落を埋めていた）。
- **セッション実行（リポジトリ版）**: `tools/leo_live.py`（要 `EUFY_SN`/`EUFY_DID`/`EUFY_LICENSE`/`EUFY_ACCOUNT`、任意で `EUFY_CONTACT`）。`LEO_OUT=<dir> python3 tools/leo_live.py` で接続〜映像取得し、`vf_9061.bin`（映像）・`vf_90e1.bin`（最終断片）・`vf_90ef.bin`（音声）を書く。`tools/mjpeg_bridge.py --raw --follow <それら> --audio-raw <音声>` で配信。
- **音声**: 別ストリーム `90 ef`（SSRC 228448e9・ヘッダ 20B）で、映像と同じ AES-128-GCM → ADTS AAC-LC 16kHz モノラル。`leo_rtc/audio.py` で復号（30 分捕捉の 11,440 パケット全復号＝12.2 分）。`tools/mjpeg_bridge.py --audio-raw vf_90ef.bin` で音声も RTSP へ載る（H.264+AAC の受信を実測）。
- **RTSP 配信**: `tools/mjpeg_bridge.py --rtsp rtsp://…` で ffmpeg から RTSP publish（ffmpeg listen モードでの実測でリスナ 121 フレーム受信）。本番は Mediamtx 等→HA/Frigate。
- **HA 配信**: `tools/mjpeg_bridge.py` が raw 捕捉（`vf_9061.bin`+`vf_90e1.bin`、`--raw --follow`）を追記追従し、IDR/パラメータを復号して MJPEG(HTTP) を配信する（HA の MJPEG カメラで参照可。オフライン実測 HTTP 200）。鍵は環境変数 `EUFY_MEDIA_KEY`/`EUFY_MEDIA_IV`（Git に置かない）。
- **セッション寿命（残課題）**: 自前クライアントの映像は約 15 秒で停止する（アプリは数分）。アプリは camera 方向へ CS2 暗号化 `f1ce` レポートを約 24/s 送っており（`06 <SSRC> <seq>` レコード列、902f の seq を参照）、暗号化済みレポートのリプレイで 15s→28s に延びた。**自前 seq でのレポート生成が次の本命**。
- **メディア（2本目の 5-tuple）** — ICE 成立済み（webrtc 候補交換・別ソケット・20B keepalive）。ペイロードは **CS2 P2P 独自暗号**（256Bテーブル＋鍵スケジュール＋前暗号文フィードバック）で解読済み（RE `docs/crypto.md`）。**映像開始はメディア版 `1003` の約0.22秒後**（実測）。映像は **P スライス＝平文 H.265、I スライス（IDR）のみ AES-128-GCM**（鍵=`crypto_key`、IV=`crypto_iv`、AAD なし、`ct=body[:-25]`/`tag=body[-25:-9]`）。`leo_rtc/video.py` の `decrypt_idr`/`decrypt_parameter_nal` で復号。**パラメータセットは元の位置に挿入**（セッション途中で解像度が切り替わるため）。**受信バッファは 16MB を確保**（`net.core.rmem_max` が小さいと 416KB に切り詰められ IDR が欠落＝復号不能の主因）。**2026-09-29: 232 フレーム（15.5 秒）の欠落ゼロ・全 IDR 復号・全編クリーンな実映像を確認**（`live4.mp4`）。各フレームの最終 FU 断片はマーカービット付き RTP（`90 e1`）で届く。
- 詳細・値は RE リポジトリ（`docs/keys.md`・`docs/crypto.md`）を参照。**鍵の値は本リポジトリに書かない。**

## 次の一手（未解決。この順で）

1. **K2 の `-104` を安定再現** — **48B ログイン＋サーバ割当 contact＋priv1 先行＋オラクル待ち 0s**。カメラを休ませ、多重実行を避けて1セッションずつ。
2. **`-104` → `code 0` の条件特定** — メディアチャネルが connected と見なされる条件。アプリの type-8 レポート直後のメディア `1003` とカメラ `80cc` 応答の並びを比較する。
3. **常時視聴へ** — 復号レシピと欠落対策は確定（受信バッファ 16MB＋IDR 復号＋パラメータのその場挿入。実測 232 フレーム・欠落ゼロ）。残りは長時間セッションの維持（カメラのスリープ対策・1003/キープアライブの継続送出）、RTSP/MJPEG 配信（`tools/mjpeg_bridge.py`）と HA 橋渡し。
4. **HA への橋渡し** — [H01](H01-home-assistant.md) と調整する。

## 試したことと結果

要点のみ（全文は RE リポジトリの `docs/history.md`）。

- 公開ソフトでのライブ取得は不可（[H04](H04-eufy.md) が正本。再試行不要）。
- 応答コード: `-110` = 復号失敗、`-104` = 復号成功・内容/状態拒否。`1103` の ACK は鍵オラクルにならない。
- 鍵の総当たり・メモリ走査は非効率で打ち切り。**アプリ pcap / signaling との突き合わせ**が有効だった。
- 落とし穴: カメラはこちらの候補 info をそのまま返す（mirror）。自 IP を候補に採らない。

## 配置と開発範囲

- **開発・検証は dev-b（とカメラと同じ LAN の android-01 VM）。** 2026-09-29〜30 の検証では、android-01 VM 上で `tools/live_supervisor.sh` を常駐させて Mediamtx へ配信しました（検証用。恒久配備の方法＝systemd 等は未定）。`stacks/eufy-leo-rtc/` の CLI は必要なときだけ実行します。
- 容量: **追加なし**（既存 dev-b の範囲。CPU・RAM・ディスクの新規予算は要求しません）。[I01](I01-resources.md) への追加実測も不要です。
- 資格情報: `EUFY_DID`・`EUFY_LICENSE`・`EUFY_ACCOUNT` は `stacks/eufy-leo-rtc/.env`（0600）か環境変数だけに置きます。**Git・ログ・チャットへ残しません。** 常設運用にする場合は H04 と同じく `platform/sops/eufy-security.sops.yaml` へ追加します。
- 既存の `eufy-security-ws` と Eufy アプリ・録画・カメラ設定は変更しません。
- RE の生成物（APK・Ghidra プロジェクト・ダンプ）は作業機の一時領域に置き、Git へ入れません。

## 実装手順（進捗つき）

1. （済）`python3 -m leo_rtc discover` — サーバ一覧とログイン。
2. （済）`python3 -m leo_rtc wake --wait 45` — `code=200`・`addr`/`port`・`turn`。
3. （済）機器 info の復号・ACK・candidate 収集。
4. （済）ICE/KCP/コマンド層を `leo_rtc/` へ反映（`ice.py`・`kcp.py`・`envelope.py`・
   `media_channel.py`・`report.py`。セッション実行は `tools/leo_live.py`）。
5. （済）映像・音声の復号（`video.py`・`audio.py`）。P スライスは平文、IDR とパラメータは
   AES-GCM、先頭 IDR 前のスライスは捨てる。`(seq, ts)` 重複除去つき再構成。
6. （済）RTSP/HA への橋渡し（`tools/mjpeg_bridge.py`・`tools/live_supervisor.sh`・Mediamtx・
   HA Generic Camera `camera.eufycam_s4_leo_rtc`）。2026-09-30 に実機で配信を確認。
7. （未）セッション維持（カメラが数十秒〜数分で止まる。0xce レポートの自前生成が候補）と、
   バッテリー消費・遅延の定量測定。常駐の配備方法（VM 上の supervisor をどう管理するか）。

### 2026-09-30 の追加（映像品質と HA の絵）

- 捕捉した RTP は **同一 ts 内で seq が前後している**ことがあり（実測で 1 セッション
  132 個）、到着順のまま FU を再構成するとフレームを捨てる。ブリッジで
  **直前フレームの次の seq を基準に並べ直して**から再構成する（`_order_frame_group`。
  ラップあり。テスト付き）。ffmpeg の POC エラーは減るが、セッションによっては
  まだ崩れる（受信欠落そのものか、カメラ側の都合かは未切り分け）。
- HA のカード用に **毎秒 1 枚の JPEG**（`--snapshot`）を書き、`http.server` で配る。
  ffmpeg は truncate してから書くため、**別名へ書いて rename で差し替える**
  （0 バイトを配ると HA は 500 を返して最後の画像を失う）。`still_image_url` は
  go2rtc の MJPEG が音声トラックで失敗するため、この URL を使う。
- 1 セッションの実測: 映像 50〜117 秒・4000〜6300 パケット（受信は継続）、
  200〜600 パケットで止まる回もある。**同じセッションでも時間帯で長さが変わる**。
- **緑・欠けたフレームの原因は ffmpeg の `-fflags nobuffer`** だった（H.265 の
  参照が壊れる）。外すと、同じ捕捉のオフライン復号が **128 フレーム・エラー0**、
  スナップショットも完全な実映像（部屋・時刻オーバーレイ付き）になった。
- 捕捉の欠落は 0（同一 ts 内の入れ替わりだけ）。`incomplete=0`・IDR 7/7 復号。
- **2026-09-30 夜（services-01 移設後の不具合の根本原因）**:
  1. **受信バッファ上限**: services-01 は `net.core.rmem_max` が既定（約 416KB）で、
     カメラのパケットを取りこぼしていた（`incomplete=30`・IDR 失敗 5）。VM では設定済み
     だった。Ansible で `/etc/sysctl.d/99-eufy-leo-rtc.conf`（32MB）を入れて解決。
  2. **コンテナの ffmpeg 5.1** はパイプ入力の HEVC で参照を落とす → 静的ビルド 7.0.2 を
     sha256 固定で導入。
  3. **ストリーミング復号の順序**: 同一フレームの断片が入れ替わって届き、確定後に
     遅れて来た断片が捨てられて参照欠け（灰色・部分復号）になっていた。確定を
     `LEO_FRAME_LAG`（既定 12 フレーム）遅らせて解決。※並べ替え自体を入れると逆に
     壊れる（一括変換と同じ「ts の安定ソート」が正しい）。
  4. **カードの静止画**は一括変換（`tools/packets_to_annexb.py`）で 1 枚作るループに変更
     （ストリーミング復号より確実）。
  → 実機確認: HA のコンテナから `rtsp://172.31.254.1:8554/eufy_av` を読んで
  **クリーンな実映像**、カードの絵も 172KB の完全なフレーム。
- **アプリの KCP 送信の時間軸を pcap から復号**: アプリは **XZYH 0x473（1139 心拍）を
  0.62 秒ごと**に KCP へ送っていた（60 秒で 98 回）。ペイロードは
  `[フレーム長 LE32=16][1][時刻 LE32][1][連番 LE32]` ＋ `XZYH 0x473 len0` の 36 バイト。
  我々の実装は心拍を送っていたが**プリュード 20 バイトが欠けていた**ため、実測どおりの
  完全形にして A/B を取った: **完全形は逆効果**（08:0x の 20 分で 232〜491 パケット／中央値
  約 350）で、裸フレームへ戻すと **5000〜6900 パケット（60〜68 秒）**に回復した。
  結論: 心拍は**裸フレーム（16B）のまま**、0.62 秒間隔。`build_heartbeat`（完全形）は
  テスト付きで残すが、セッションでは使わない（`leo_rtc/media_channel.py`）。

## 依存と並列作業

- 開発開始: 実機の S4 と機器の `p2p_did`/`p2p_license`（クラウド応答）が必要。H04 の解析成果が出発点。
- 配備・切替: いまは無し（dev-b の開発のみ）。HA へ映像を出す段階で [H01](H01-home-assistant.md)・[N03](N03-vlan.md) と調整し、容量は [I01](I01-resources.md) で測る。
- 競合: `eufy-security-ws` は触らない。検証でアカウントログインをしない（共有ユーザーを使う場合も H04 の注意に従う）。

## 検証と完了条件

- wake は `code=200` の応答（`addr`・`port`・`turn`）で判定し、終了時に `hangup` を送る。バッテリーを無駄に消費しない。
- SDP/ICE・メディアが通ったら、遅延・解像度・再接続・バッテリー消費を記録する。未対応の機能を「利用可能」と案内しない。
- 資格情報と映像が許可外へ公開されない。既存アプリ・録画が継続する。
- `tests/test_eufy_leo_rtc.py` がフレーミング・鍵導出・境界・秘密値の非混入を検査する。実機へ接続するのは CLI 実行時だけ。

<a id="handover-log"></a>

## handover移動分の作業記録

handover.md の「5. 進捗とTODO」表の該当行から移した記録（原文のまま。表セルを日付ごとの箇条書きに整形しただけ）。いまの状態と未完は handover.md の該当行を参照。

- **単体S4のライブをネイティブ leo_rtc で自前実装中（2026-09-29）。★欠落ゼロで 232 フレーム（15.5 秒）の全編クリーンな実映像をデコード。** 決め手は call の `boot_action=1`＋ログイン応答 48B＋同時送信リトライ＋priv1 先行＋1103＋メディアチャネルへの 1003。映像は RTP(PT97・SSRC 0dc1a815・拡張 bede)＋RFC7798 FU。**P スライスは平文、I スライス（IDR）のみ AES-128-GCM（鍵=`crypto_key`・IV=`crypto_iv`・AAD なし、`ct=body[:-25]`/`tag=body[-25:-9]`）**で、`leo_rtc/video.py` の `decrypt_idr`/`decrypt_parameter_nal` で復号（パラメータは**元の位置に挿入**＝途中で解像度が切り替わる）。**各フレームの最終 FU 断片はマーカービット付き RTP（`90 e1`）**。**パケット欠落の真因は受信バッファが `net.core.rmem_max` で 416KB に切り詰められていたこと**（`SO_RCVBUF` 16MB 確保で欠落ゼロ・IDR 9/9 復号）。**採用構成を確定（DRWAck＋wakeリトライ＋受信バッファ16MB＋重複除去＋AES-GCM復号。周期的1003は禁止＝ストリーム再開を誘発）**。欠落ゼロ化は前進（アプリの `f1ce` レポートをリプレイ→カメラが再送→(seq,ts) 重複除去で **IDR 10/10 復号・incomplete=0**。スーパーバイザで自動再接続し **2688x1520・208 フレームの完全クリーン映像**を取得）。**HA 配信は `tools/mjpeg_bridge.py`（raw 追記追従・IDR 復号・MJPEG/HTTP）が動作**（オフライン HTTP 200 実測）。**30 分連続試験を実施（33 分・23 セッション中 17 で映像・映像合計 3288 フレーム/約 221 秒・IDR 128/141 復号）**。14 捕捉セッション中 12 は欠落ゼロ・IDR ほぼ 100%、2 は捕捉ストール（要因調査中）。**RTSP publish も実装**（`--rtsp`、リスナ受信を実測）。上流移植は `feat/leo-rtc-s4`（ローカル・push なし）で media/cs2/media-channel を移植し `npm run verify` green。残りはストール除去・セッション維持（**0xce レポートの自前生成**）・Mediamtx 配備。既存イベント・Push は維持。
- **2026-09-30: 映像に加えて音声（別 RTP `90 ef`・ADTS AAC-LC 16kHz モノラル・IDR と同じ AES-128-GCM）を復号**。`tools/leo_live.py` が `vf_9061.bin`（映像）・`vf_90e1.bin`（最終 FU）・`vf_90ef.bin`（音声）と `session_keys.json` を書き、`tools/mjpeg_bridge.py` が鍵を読み直して追記追従し Mediamtx へ RTSP 配信（`-g 20`＝2 秒キーフレーム。HLS/WebRTC はキーフレーム境界でしかセグメントを作れない）。`tools/live_supervisor.sh` がセッションを繰り返し（映像が取れた回は 15 秒後、失敗が続くと倍々で最大 5 分）、`sessions.csv` に統計を残す。**HA 反映済み**（Generic Camera。HA 用は音声なし＝go2rtc MJPEG の制約、`eufy_av` に映像＋音声）。映像のみの ffmpeg でも**先頭 IDR より前のスライスを捨てる**ゲートを追加（POC 破綻対策）。実測: 1 セッション 4001 パケット/49 秒〜5937/2.7 分と長短あり、カメラ側の都合で数十秒〜数分で止まる（アプリは数分連続＝keepalive の差。周期的 media 1003 はストリーム再開を誘発するため送らない）。上流（mega-yfue/eufy-sdk）へは wire 層 14 モジュール（call/session/live-session 追加、AES-ECB の自動 PKCS#7 除去、1139 心拍、FU 並び替え対応）を移植し `npm run verify` green（220 files/3848 tests、push なし）。
- **2026-09-30 昼**: オンデマンド wake（HA の読み取りを検知して 45 秒間隔へ短縮）、夜間（1〜6 時 JST）は 600 秒間隔に間引き。A/B で **心拍の完全形（プリュード 20B 付き）は逆効果**（セッション中央値 365 ⇔ 裸フレーム 5204）。`-fflags nobuffer` を外すと復号エラーが消えた（緑フレームの原因）。
