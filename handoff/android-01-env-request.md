# android-01 環境構築 依頼書

> 更新日 2026-09-23 ・ 区分 作業依頼（外部委託）

## 範囲

クラウドVM `android-01` 上で、指定アプリを Frida でフックした状態で操作・ログ取得できる環境を整える。**環境構築のみ**で、解析・実装は含まない。

## 完了条件

1. RDP で Android 画面へ入れる。
2. 指定アプリを起動し、テスト用アカウントでログインできる（認証情報は別途受け渡し）。
3. Frida がアプリへアタッチしたまま動作し続け、`/opt/leo/hook2.log` にログが出続ける（アプリが落ちない）。
4. 有効だった手順・対策を「実施記録」へ追記する。

## 環境（構築済み）

| 項目 | 内容 |
| --- | --- |
| VM | `android-01`（instance `i-62f1d8395418e26c2`）`192.168.10.104`、Debian 13、4vCPU / 6GiB 固定 |
| Android | Waydroid 1.6.3（LineageOS 20 GAPPS）＋ libndk 0.2.3 |
| アプリ | 指定アプリ 6.0.90（v7a）インストール済み。ログイン画面の表示まで確認 |
| Frida | `frida-server` 17.18.0（x86_64）`/opt/leo/frida-server`、CLI `/opt/leo/venv/bin/frida`、フック `/opt/leo/hook.js` |
| 画面 | RDP `192.168.10.104:3389`（weston、`idle-time=0`） |
| adb | `192.168.10.104:5555`（Android 側は `192.168.240.112`）。待受は外向き IP のみ |
| 常駐 | tmux セッション `wd`（weston / session / socat / ui） |
| 起動 | `bash /opt/leo/persist.sh`（再実行可能。binder・ブリッジ確認 → Android 起動待ち → suspend 無効化 → 消灯無効化 → ui ループ起動を 1 本で実施） |
| 自動起動 | `android-env.service`（VM 再起動で `persist.sh` が自動実行され、約 20 秒で復旧） |

補助スクリプト（`/opt/leo/`）:

- `ui-loop.sh`: 15 秒ごとに FROZEN を検知して自動解除する。ログは異常時のみ残す。
- `recover.sh`: 手動で FROZEN を解除する。必要ならセッションごと再起動する。
- `verify.sh`: 状態確認用。
- 作業メモ: `/opt/leo/ENV-NOTES.md`

## 手順

1. SSH: `ssh -i <鍵> debian@192.168.10.104`（鍵は別途受け渡し）。再起動後は自動復旧するため通常は操作不要。
2. 手動で作り直すときは `bash /opt/leo/persist.sh` を実行し、`waydroid status` が `Session: RUNNING` / `Container: RUNNING` になることを確認する。
3. 異常時は `bash /opt/leo/verify.sh` で状態を確認する。FROZEN は通常 `ui-loop.sh` が自動解除し、手動なら `recover.sh` を使う。
4. RDP で接続し、指定アプリを起動してテスト用アカウントでログインする。
5. 端末内で frida-server を root で起動する（`adb root` は使用不可）。
   `sudo waydroid shell -- /data/local/tmp/frida-server -l 0.0.0.0:27042`
6. アプリが安定してからアタッチする。
   `/opt/leo/venv/bin/frida -H 192.168.240.112:27042 -p <pid> -l /opt/leo/hook.js -o /opt/leo/hook2.log`
7. アプリを操作し、`/opt/leo/hook2.log` にログが出続けることを確認する。

## 既知の課題

- **アタッチでアプリが落ちる（未解決）**: `frida ... -p <pid>` の直後に `target terminated with signal 6` で終了する。パック難読化＋アンチデバッグ入りのため対策が必要。候補:
  - frida-server の実行ファイル名・ソケット名を変更して起動する。
  - アタッチを起動直後ではなく画面安定後に行う。
  - arm64 版のアプリへ差し替える（Play Store または Aurora Store から取得可能）。
  - 上記で不可なら Frida gadget 方式を検討する。

## 注意（引き継ぎ）

- `persist.sh` は tmux `wd` を作り直すため、frida などのウィンドウは実行後に追加し直す。
- RDP は VM 内クライアントでの接続確認まで。実画面の最終確認は依頼者端末で行う（VM には `xvfb` と `freerdp3-x11` を導入済み）。
- コンテナの FROZEN は `persist.waydroid.suspend=false` で解消済み（再起動後も保持）。RDP 接続だけでは復帰しないが、`show-full-ui` の実行で約 0.6 秒で復帰する。
- VM 再起動後は「`persist.sh` → `show-full-ui` ループ → frida-server」の順で起動する。

## やらないこと

- テストアカウントの変更・ログアウト。
- アプリの設定変更。
- 認証情報・取得したログ・鍵を Git や外部へ共有しない。
- リポジトリへのコミット（作業メモは VM の `/opt/leo/` に置く）。

## 実施記録

### 2026-09-23 FROZEN の原因調査と安定化

- **原因**: セッション開始直後に UI が表示されていない状態（active_apps が空）だと、Android が約 30 秒で suspend を要求し、Waydroid がコンテナを freeze する。RDP の有無・画面消灯の有無では変わらず、切り分け 4 パターンすべてで既定設定では 30 秒で再現した。消灯設定は引き金ではない。
- **対策**: `services.jar` 内の `persist.waydroid.suspend` を false に設定。最も厳しい条件でも 150 秒間 FROZEN にならず、再起動後も設定は保持される。
- **復帰**: `show-full-ui` の実行だけで約 0.6 秒で復帰し、120 秒経過しても再発しない。RDP を接続しただけでは復帰しない。
- **VM への変更**:
  - `persist.sh` を再実行可能な形に刷新（旧版は `persist.sh.orig`）。binder・ブリッジ確認、Android 起動完了待ち、suspend 無効化、消灯無効化、ui ループ起動を 1 本で行う。
  - `ui-loop.sh`（FROZEN の 15 秒ごとの自動解除）、`recover.sh`（手動復帰）、`verify.sh`（状態確認）を追加。
  - weston を `idle-time=0` に設定。
  - `android-env.service` を追加し、再起動時に `persist.sh` を自動実行。debian ユーザーの linger 有効化と binder の起動順序設定も追加。
  - adb の待受を外向き IP `192.168.10.104` のみに限定（全インターフェース待受だと adb が `emulator-5554` を誤検出し、`-s` なしの `adb shell` が失敗していた）。
- **確認結果**:
  - 再起動 2 回とも約 20 秒で Session / Container が RUNNING、tmux の 4 ウィンドウがそろい、adb と RDP に接続できた。
  - 外部 IP 経由の RDP・adb 接続を確認。
  - 手動 `persist.sh` 実行後、5 分間 FROZEN なし。
  - ui ループの自動解除と `recover.sh` の動作を確認。
- **残**: RDP 実画面の最終確認は依頼者端末で行う。Frida アタッチ（signal 6）は未解決。
