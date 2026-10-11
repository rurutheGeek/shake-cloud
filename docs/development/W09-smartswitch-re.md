---
title: W09 Smart Switchの非公式クライアント（解析）
updated: 2026-10-03
section: 開発計画
audience: 開発者
tags:
  - plan
  - smartswitch
  - reverse-engineering
---

# W09 Smart Switchの非公式クライアント（解析）

> **更新日** 2026-10-03 ・ **区分** 開発計画 ・ **読む人** 開発者

これは開発計画であり、配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。

## 目的

**Samsung Smart Switch PC を使わず、非rootのGalaxyからアプリデータ込みの完全バックアップを取る**ための非公式クライアントを作る。W08で整えたバックアップポータル（ADB over WebUSB）から駆動できれば、Windows PCもSamsung製ソフトも不要になる。

- 対象: Galaxy（SCG20）のアプリ・アプリデータ・SMS/通話・連絡先・設定・カレンダー等（画像/ビデオ/オーディオは除外可能）
- 前提: 非root。アプリデータは端末のSmart Switchアプリ（`com.sec.android.easyMover`、特権アプリ）がAndroidの**FullBackupAgent**で梱包する
- 配備候補: media-01（Linux・USB接続）または既存ポータルのWebUSB

## 判明したこと（2026-10-03の実機解析）

### 通信の構成

| チャネル | 役割 |
| --- | --- |
| **MTP**（USB bulk EP1 IN/OUT） | バックアップデータ本体。実測 **42.9GB** がMTPで転送された |
| Samsung独自MTP操作（0x9501〜0x9503・0x9801〜0x9805） | セッション制御・進捗・オブジェクト操作 |
| CDC「CONN3」 | 接続サービス（`CONN`ハンドシェイク。端末情報 SCG20・ver 2.19.1.0・UUID） |
| ADB | **Smart Switchは使わない**（録れていたのは検証用の自作コマンドのみ） |

### バックアップの仕組み（推定）

1. Smart Switch PCがCDCの`CONN`で接続、MTPのOpenSession後、独自操作（0x9801のハンドル列、0x9503のモード切替）でバックアップを開始する
2. 端末の`com.sec.android.easyMover`がカテゴリごとのオブジェクトを作る。実測で見えた名前:
   - `Contact.bk`・`Calendar.bk`・`sdoc.bk`・`fail.bk`
   - `CALLLOG.zip`・`ALARM.zip`・`WORLDCLOCK.zip`・`WIFICONFIG.zip`・`CAMERA.zip`・`BLUETOOTH.zip`・`CLIPBOARD.zip`・`MYFILES.zip`・`THEME.zip`・`WALLPAPER.zip`・`COLORTHEME.zip`・`SHORTCUT.zip`・`FMM.zip`・`HOMEUP.zip`・`QUICKPANEL.zip`・`RINGTONE.zip`・`SMARTMANAGER`
   - アプリ・ユーザーファイル（`Screenshot_*`・`.pdf`・`.m4a`・アプリデータの`*.bin`・`*.apk`・`*.penc`）
3. 一時フォルダ **`OtgBackupTemp`**（セッション名 `20261003T143017` 等）に置き、PCがMTPで引く
4. 進捗は独自操作 **0x9805**（`[現在, ?, 項目コード, ?]`、終了時 `0xFFFFFFFF`）で報告される。最後に 0x9501/0x9502 で終了

### 解析手法（ベストプラクティス）

- **QEMU内蔵のUSB pcap記録が最良**: VMの`args`へ `-device usb-host,hostbus=5,hostport=1,pcap=/srv/bulk/ss-phone.pcap` を付けると、カーネル側でURBを確実に記録できる（usbmon互換pcap）。1URBあたり512Bまで保存されるため、制御・コマンドは完全、大容量データは先頭のみ
- ホスト側`usbmon`＋tcpdumpは**バルク転送を取りこぼす**（実測: 300MBの転送で13MBしか録れず、ドロップ報告も出ない）。WindowsゲストのUSBPcapはドライバ装着が不安定だった
- 取得物: `/srv/bulk/ss-phone.pcap`（1.19GB、42.9GBのMTP転送を記録）

## 次の実験（スマホが戻ったら）

1. **`OtgBackupTemp`の場所を確認**: `adb shell ls -la /sdcard/OtgBackupTemp`。共有ストレージ上なら、既存ポータルのADBでそのまま引ける可能性が高い（トリガーだけが課題）
2. **標準MTPでの可視性**: Linux（media-01）でlibmtp（`mtp-files`）から`OtgBackupTemp`とカテゴリオブジェクトが見えるか。見えればMTPクライアントだけで取得できる
3. **独自操作の解読**: 0x9801（オブジェクトハンドル列）・0x9503（モード2/3）・0x9805（進捗）・0x9501/0x9502（開始/終了）の引数と応答を、pcapのフェーズと突き合わせて意味付ける
4. **試作**: 上記の結果に応じて (a) `OtgBackupTemp`をADBで引くボタンをポータルへ追加、(b) MTPクライアント（libmtp/自前）＋独自操作、のどちらかで実装

## 検証・完了条件

- Windows PCとSmart Switch PCなしで、非rootのGalaxyからアプリデータ込みのバックアップが取れる
- 取得物がSmart Switch PCのバックアップと同じカテゴリ構成（Contact.bk・CALLLOG.zip等）である
- media-01またはポータルから実行でき、再実行が冪等（変更分のみ）である
- Samsungの仕様変更で壊れたときに、pcapの再取得（QEMU pcap）から解析をやり直せる手順が残っている

## 実装記録

- 2026-10-03: **Smart Switch PC 4.3.24094.1 をwin11pro（VMID 5000）へ導入し、実機バックアップを解析。** Smart App Control（SAC）がインストーラを止めていた（Defenderは無関係）。SACをレジストリ`VerifiedAndReputablePolicyState=0`で無効化して導入。バックアップは2回実行し、2回目をQEMU pcapで完全記録（42.9GB・MTP）。通信はMTP＋Samsung独自操作＋CDC`CONN3`で、ADBは不使用。アプリデータはFullBackupAgentが梱包。オブジェクトは`OtgBackupTemp`経由。詳細は本文。
