---
title: android-01（Waydroid）の環境
updated: 2026-10-02
section: 運用手順
audience: 管理者・開発者
tags:
  - ops
  - vm
  - android
---

# android-01（Waydroid）の環境

> **更新日** 2026-10-02 ・ **区分** 運用手順 ・ **読む人** 管理者・開発者

クラウドVM `android-01` 上のAndroid（Waydroid）環境の構成・復旧手順・FROZENの原因と対策・未解決の課題です。利用者向けの画面の使い方は[Android VMの画面を使う（RDP）](../services/android.md)、Eufyカメラのライブ映像での使われ方は[H05](../development/H05-eufy-leo-rtc.md)を見てください。

**この環境のスクリプトはGitに入っていません。** `/opt/leo/` 配下（`persist.sh`・`ui-loop.sh`・`recover.sh`・`verify.sh`・`hook.js`・`ENV-NOTES.md`）と`android-env.service`はVM上にだけあります。VMを作り直すと失われるので、コード化は未了の宿題です（下の「未了」）。

## 構成

| 項目 | 内容 |
| --- | --- |
| VM | `android-01`（instance `i-62f1d8395418e26c2`）`192.168.10.104`、Debian 13、4vCPU / 6GiB固定 |
| Android | Waydroid 1.6.3（LineageOS 20 GAPPS）＋ libndk 0.2.3 |
| Frida | `frida-server` 17.18.0（x86_64）`/opt/leo/frida-server`、CLI `/opt/leo/venv/bin/frida`、フック `/opt/leo/hook.js` |
| 画面 | RDP `192.168.10.104:3389`（weston、`idle-time=0`） |
| adb | `192.168.10.104:5555`（Android側は`192.168.240.112`）。待受は外向きIPのみ |
| 常駐 | tmuxセッション`wd`（weston・session・socat・ui の4ウィンドウ） |
| 起動 | `bash /opt/leo/persist.sh`（再実行可能） |
| 自動起動 | `android-env.service`。VM再起動で`persist.sh`が走り、約20秒で復旧する |

`persist.sh`は、binder・ブリッジの確認 → Androidの起動完了待ち → suspend無効化 → 消灯無効化 → uiループ起動を1本で行います。補助スクリプト:

- `ui-loop.sh`: 15秒ごとにFROZENを検知して自動解除する。ログは異常時のみ残す。
- `recover.sh`: 手動でFROZENを解除する。必要ならセッションごと再起動する。
- `verify.sh`: 状態確認。

## 手順

1. SSH: `ssh -i <鍵> debian@192.168.10.104`。再起動後は自動復旧するので通常は操作不要。
2. 作り直すときは`bash /opt/leo/persist.sh`を実行し、`waydroid status`が`Session: RUNNING`・`Container: RUNNING`になることを確認する。**`persist.sh`はtmux`wd`を作り直す**ので、fridaなどのウィンドウは実行後に追加し直す。
3. 異常時は`bash /opt/leo/verify.sh`で確認する。FROZENは通常`ui-loop.sh`が自動解除し、手動なら`recover.sh`を使う。
4. VM再起動後は「`persist.sh` → `show-full-ui`ループ → frida-server」の順で起動する。
5. frida-serverは端末内でrootで起動する（`adb root`は使えない）。
   `sudo waydroid shell -- /data/local/tmp/frida-server -l 0.0.0.0:27042`
6. アプリが安定してからアタッチする。
   `/opt/leo/venv/bin/frida -H 192.168.240.112:27042 -p <pid> -l /opt/leo/hook.js -o /opt/leo/hook2.log`

RDPはVM内クライアント（`xvfb`と`freerdp3-x11`を導入済み）での接続確認まで行いました。実画面の最終確認は利用者の端末で行います。

## FROZENの原因と対策（2026-09-23）

- **原因**: セッション開始直後にUIが表示されていない状態（`active_apps`が空）だと、Androidが約30秒でsuspendを要求し、Waydroidがコンテナをfreezeする。RDPの有無・画面消灯の有無では変わらず、切り分け4パターンすべてで既定設定では30秒で再現した。消灯設定は引き金ではない。
- **対策**: `services.jar`内の`persist.waydroid.suspend`をfalseにした。最も厳しい条件でも150秒間FROZENにならず、再起動後も設定は保持される。
- **復帰**: `show-full-ui`の実行だけで約0.6秒で復帰し、120秒経っても再発しない。**RDPを接続しただけでは復帰しない。**
- **VMへの変更**: `persist.sh`を再実行可能な形に刷新（旧版は`persist.sh.orig`）、`ui-loop.sh`・`recover.sh`・`verify.sh`の追加、westonを`idle-time=0`に設定、`android-env.service`の追加（debianユーザーのlinger有効化とbinderの起動順序設定を含む）、adbの待受を外向きIP`192.168.10.104`のみに限定。
- **adbの待受を絞った理由**: 全インターフェースで待受すると、adbが`emulator-5554`を誤検出し、`-s`なしの`adb shell`が失敗していた。
- **確認結果**: 再起動2回とも約20秒でSession/ContainerがRUNNINGになり、tmuxの4ウィンドウがそろい、adbとRDPに接続できた。手動`persist.sh`の後、5分間FROZENなし。uiループの自動解除と`recover.sh`の動作も確認した。

## 未解決・未了

- **Fridaのアタッチでアプリが落ちる（未解決）。** `frida ... -p <pid>`の直後に`target terminated with signal 6`で終了する。対象アプリ（6.0.90、v7a）はパック難読化とアンチデバッグ入り。候補: ①frida-serverの実行ファイル名・ソケット名を変えて起動する、②起動直後ではなく画面が安定してからアタッチする、③arm64版のアプリへ差し替える（Play StoreまたはAurora Storeから取得可能）、④上記で不可ならFrida gadget方式。完了条件は「Fridaがアタッチしたまま動き、`/opt/leo/hook2.log`にログが出続ける（アプリが落ちない）」。
- 公式アプリのライブ表示は2026-09-30時点で開けない（[H05](../development/H05-eufy-leo-rtc.md)）。この環境の用途は、その後ネイティブのleo_rtcクライアントでの検証へ移っている。
- `/opt/leo/`のスクリプトと`android-env.service`をリポジトリ（Ansible）へ取り込む。方針は「コード化できるものはコードにする」。取り込むまでは、VM再作成で消える。
- 認証情報・取得したログ・鍵はGitや外部へ共有しない。テストアカウントの変更・ログアウトとアプリの設定変更はしない。
