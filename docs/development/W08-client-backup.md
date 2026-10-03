---
title: W08 クライアント端末のバックアップ
updated: 2026-10-02
section: 開発計画
audience: 開発者
tags:
  - plan
  - backup
  - urbackup
---

# W08 クライアント端末のバックアップ

> **更新日** 2026-10-02 ・ **区分** 開発計画 ・ **読む人** 開発者

これは開発計画であり、配備完了の記録ではありません。[配置・所有境界・並列作業の共通ルール](index.md)を参照してください。番号は実施順を表しません。実機の結果は[配備台帳](../operations/handover.md)へ、使い方は[クライアント端末のバックアップ](../operations/client-backup.md)へ書きます。

## 目的・現状

**状態**: **実装・実機配備済み（2026-10-02）。** Windows PC のシステムイメージとファイルの**世代バックアップ**を media-01 の UrBackup で取る。Android は家族全員 Galaxy のため、**バックアップポータルのボタン1つ（USB・WebUSB）**で写真・書類・APKを media-01 のHDDへ保存する（アプリ内部データはAndroidの制限で対象外。機種変更の引き継ぎは Smart Switch）。入口は**バックアップポータル**（`https://backup.apextox.dpdns.org`。状態と操作を1ページに集約）。保存先は6TB HDDの専用領域で、HDD が単一障害点であることは既存方針どおり別途コピーで補う。**未完**: Windows 実端末の初回バックアップ・復元（と自動発見の実測）、Galaxy 実端末での WebUSB バックアップ（写真・書類・APKの完走と2回目のスキップ）、イメージ復元の演習。

- 対象: Windows PC（イメージ＋ファイル）と Galaxy（写真・動画・ダウンロード・書類・アプリAPK。**最新の1世代**でよい）
- 対象外: Android のアプリ内部データ（ログイン・設定・ゲームセーブ）。非rootでは取り出せないため、機種変更時は Smart Switch の引き継ぎを使う
- 配備先: **media-01**。開発先は `stacks/media/urbackup/`。共有は `platform/ansible/roles/pve_bulk_storage`

### 方式の決定

| 対象 | 実装 | 理由 |
| --- | --- | --- |
| Windows | UrBackup（`uroni/urbackup-server`） | OSSで、公式Windowsクライアント・システムイメージ・世代保持・重複排除・復元メディアまで揃う。Web UI で状態を確認できる |
| Galaxy | **バックアップポータル＋WebUSB（ADB）** | スマホにアプリを入れず、PCにソフトも入れず、USBでつないでボタン1つ。ブラウザー（Vivaldi・Chrome・Edge などのChromium系）が `@yume-chan/adb`（OSS・MIT）で直接読み、サーバーへストリームする。2回目以降は差分スキップ |
| 入口 | バックアップポータル（`stacks/media/urbackup/portal.py`＋`portal-web/`） | 状態・手順・実行ボタンを1ページに集約する。Forward Auth の内側 |
| 保存先 | 6TB HDD の `/srv/bulk/client-backups`（`urbackup/` と `android/`） | media-01 のデータディスクは 64GiB で足りない。既存の NFS 共有に相乗りする |

## 実装手順（実装済みの構成）

1. **HDD 側**: `pve_bulk_storage` ロールに `/srv/bulk/client-backups`（`anonuid=101`）を追加し、media-01 だけへ export する。
2. **マウント**: `media-base.yml` が `/srv/media-stack/client-backups` へ NFS マウントし、`RequiresMountsFor` に加える（未マウントなら Docker を起動しない）。
3. **スタック**: `stacks/media/urbackup/`（独立 Compose `media-urbackup`）。Web UI は `127.0.0.1:55414`、クライアント通信は `192.168.10.101:55413`、自動発見は `35623/udp`。サーバー状態はローカルデータディスク、バックアップ本体は HDD。
4. **設定のコード化**: `manage.py configure` が Web API（`/x`）で `settings.json` を冪等に適用する。管理者パスワードは `secrets/urbackup_admin_password` に生成し、ログインできなければ `urbackupsrv reset-admin-pw` で設定する。
5. **入口**: Security Group に TCP 55413 と UDP 35623（LAN のみ）を追加し、`dns.yaml` に `backup.apextox.dpdns.org`（ポータル）と `urbackup.apextox.dpdns.org`（管理画面。どちらも Forward Auth）を追加する。
6. **ポータル**: `portal.py` が UrBackup の状態と端末ごとの手順・実行ボタンを1ページで出す（同じ Compose の `portal` サービス）。Android は `portal-web/`（`@yume-chan/adb` を esbuild でバンドルした `portal-backup.js`）がブラウザーで ADB over WebUSB を話し、`/api/android/*` へストリームする。
7. **テスト**: `tests/test_media_urbackup.py`、`test_pve_bulk_storage.py`、`test_media_playbook.py`、`test_media_vm.py`、`test_tls_proxy.py`。

## 依存と並列作業

- 配備: [I02](I02-media-vm.md)（media-01）、[共有バルクストレージ](../operations/bulk-storage.md)、[N05](N05-https.md)（HTTPS/Forward Auth）、identity。
- 競合調整: `pve_bulk_storage` の export 一覧、`media-base.yml` の Docker 依存、`dns.yaml`、Security Group。既存ユニットの複製ではなく差分で足す。
- Windows クライアントの配布はサーバー Web UI から行う。端末側の初期設定は[クライアント端末のバックアップ](../operations/client-backup.md)に従う。

## 検証・完了条件

- `media-verify.yml` が UrBackup の Web UI 応答とコンテナ healthy を確認する。
- `https://backup.apextox.dpdns.org` が SSO の内側で開き、`manage.py configure` の2回目が `OK:`（変更ゼロ）になる。
- Windows 実機で: クライアントが LAN で自動発見される（UDP 35623 が Docker 越しに届くか実測）、初回のファイル＋イメージバックアップが完了し、Web UI に履歴が出る。単体ファイルの復元を1件行う。
- 復元メディアでのベアメタル復元は端末の準備ができた時点で演習し、結果を[配備台帳](../operations/handover.md)へ記録する。
- Galaxy: Vivaldi（Chromium系）でポータルを開き、USBデバッグを許可した端末で「スマホをバックアップ」を実行し、写真・書類・APKが `/srv/bulk/client-backups/android/<端末>/files` に入ることを確認する。2回目が差分スキップで短時間に終わることも見る。
- ポータル: `https://backup.apextox.dpdns.org` が SSO の内側で開き、UrBackup の状態・Androidの実行ボタン・最終バックアップ一覧が出る。`media-verify.yml` が portal の 200 を確認する。

## 実装記録

- 2026-10-02: **実装とテストを追加。** `stacks/media/urbackup/`（compose・lock・manage.py・settings.json・README）、`media-urbackup.yml`、`media-base.yml` の3本目のマウント、`pve_bulk_storage` の `client-backups`、Security Group と `dns.yaml` の `backup`、テスト一式を追加した。UrBackup 2.5.x の Web API（`/x` の `salt`→`login`、`settings?sa=general`、`settings?sa=general_save`）と `urbackupsrv reset-admin-pw -p` を実機の一時コンテナで確認済み。
- 2026-10-02: **実機配備。** Proxmoxホストへ `/srv/bulk/client-backups`（2770・101:101、`all_squash,anonuid=101,anongid=101` で media-01 のみへ export）を作成し、media-01 の `/srv/media-stack/client-backups` へ NFS マウント（`RequiresMountsFor` に追加・Docker 再起動で反映）。Security Group に TCP 55413 と UDP 35623 を追加（`plan: 2 to add`）。DNS は既存の `poke` を消さないよう `backup` レコードだけをターゲット適用し、`backup.apextox.dpdns.org` → `192.168.10.101` を確認。`media-urbackup.yml` で `init`→`up`→`configure` が通り、`configure` は2回目に `OK: server settings already match settings.json`（`server_url`・`default_dirs`・`image_letters`・`internet_mode_enabled=false` を適用）。identity の `configure.py` に Forward Auth プロバイダ `backup` を追加して適用し、`https://backup.apextox.dpdns.org/` が Authentik へ 302（SSO の内側）になることを確認。`media-verify.yml` は全ユニット green。LAN から `192.168.10.101:55413` は到達でき、`55414`・`55415` は閉じていることを実測。
- 2026-10-02: **配備中に見つけた修正。** (1) `media-base.yml` がマウントポイントを作らず `mount` が rc=32 で止まったため、3つのマウントポイントを冪等に作るタスクを追加（既存の NFS マウントには chown しない）。(2) Web API のベースに余分な `/` を付けて `Unknown action []` になったため `/x` のまま使う。(3) 一般設定の値は `{'value': ...}` と素の値が混在するため両対応にした。(4) パスワードリセット直後はログインが数秒通らないため再試行を追加。(5) `media-verify.yml` の music-tools 既定が配備側とずれていた（`review` 欠落・healthcheck 数え上げ）ため同期した。
- 2026-10-02: **監視へ追加。** `stacks/monitoring/prometheus/blackbox-targets.yml` に `https://backup.apextox.dpdns.org/`（Forward Auth の 302 を許す `https_reachable`）を追加し、`monitoring.yml` を配備。Prometheus で `probe_success{instance="https://backup.apextox.dpdns.org/"}` が 1 になることを確認した。
- 2026-10-02: **Android は Swift Backup 1本に決定（利用者判断）。** 真の全バックアップは root か Seedvault 入りカスタムROMが必要で、非rootではアプリ内部データを取り出せない（`adb backup` もAndroid 12以降は実質廃止）。操作を1アプリに寄せ、APK・SMS/通話・壁紙・フォルダ（写真含む）は Swift Backup から Nextcloud の WebDAV へ毎日予約、連絡先・カレンダーだけ Davx5 とした。クラウド保存と予約は有料で、アプリのサインインに Google アカウントが必要（保存先は Nextcloud で、Google へは送られない）。無料・匿名なら端末内バックアップ＋Nextcloud フォルダ同期（予約不可）。手順と復元順は[クライアント端末のバックアップ](../operations/client-backup.md)へ書いた。
- 2026-10-02: **受け皿を用意。** 両ユーザーに Nextcloud のアプリパスワード（名前 `swift-backup`）と `Backups/` を発行し、WebDAV URL・ユーザー名・パスワードを書いた `Backups/_setup-memo.txt` を各アカウントへ置いた（スマホの Nextcloud アプリから読める）。控えは media-01 の `/opt/media-stack/media/nextcloud/secrets/phone-backup-app-passwords.txt`（root のみ）。実機で WebDAV の PROPFIND 207 と `Backups/_setup-memo.txt` を確認。Nextcloud のクォータは未設定＝無制限、HDDは空き5.2TiB。
- 2026-10-02: **方針変更（利用者判断）: Pixel をやめて家族全員 Galaxy になったため、Android は Smart Switch PC（USB）へ切り替えた。** アプリ・アプリデータ（アプリによる）・SMS/通話・連絡先・設定・写真・書類が純正ツールで PC へ入り、保存先の `C:\Users\...\Documents\Samsung\SmartSwitch` を既存の UrBackup がそのまま回収する。端末にバックアップアプリを入れない・有線でよい、という要件に合う。Swift Backup 用に用意した Nextcloud のアプリパスワードと `Backups/`・メモは撤去した（`occ user:auth-tokens:delete` と WebDAV DELETE、実機で確認）。
- 2026-10-02: **バックアップポータルを追加。** `stacks/media/urbackup/portal.py`（標準ライブラリのみ・読み取り専用）を同じ Compose の `portal` サービス（`python:3.13-alpine`、mail-view と同じ digest、`127.0.0.1:55416`）として動かす。UrBackup の `/x` API からクライアントの状態（オンライン・最終ファイル・最終イメージ）を読み、Windows と Galaxy の手順を1ページに出す。入口は `backup.apextox.dpdns.org`（Forward Auth）、管理画面は `urbackup.apextox.dpdns.org` に分けた。identity にプロバイダ `urbackup` を追加し、blackbox と `media-verify`（portal の 200 と healthy 2）へ反映した。
- 2026-10-02: **ポータルを実機配備。** `media-urbackup.yml` で `portal` を起動（healthy、`/healthz` が `{"status":"ok","urbackup":true}`）。DNS は `urbackup` レコードだけをターゲット適用して追加（`backup`・`urbackup` とも `192.168.10.101`）。`media-tls.yml` で Caddy を更新し、identity に Forward Auth プロバイダ `urbackup` を追加。両名とも未認証は Authentik へ 302。`media-verify.yml` は portal の 200（`バックアップポータル` を含む）と healthy 2 を含めて全ユニット green。blackbox の `probe_success` は `backup`・`urbackup` とも 1。
- 2026-10-02: **方針変更（利用者判断）: WebUSBでブラウザー直結。** PCソフト（Smart Switch PC）もスマホアプリも入れたくない、PCにUSBでつないでボタン1つ、という要件のため、ポータルに WebUSB バックアップを実装した。`portal-web/` が `@yume-chan/adb`（MIT）・`@yume-chan/adb-daemon-webusb`・`@yume-chan/adb-credential-web` を使い、esbuild で `portal-backup.js`（約65KB）へバンドルしてリポジトリに含める（`npm install && npm run build` で再生成）。ブラウザー（Vivaldi・Chrome・Edge などのChromium系）が ADB で `/sdcard/DCIM`・`Pictures`・`Download`・`Documents` と `pm` の APK を読み、`/api/android/chunk`→`/finish`→`/manifest` で HDD の `android/<端末>/files` へストリーム保存する。サイズと mtime が同じファイルは2回目以降スキップ。アプリ内部データは非rootでは不可（従来どおり）。
- 2026-10-02: **ポータルを更新して実機確認。** `portal` に `portal-backup.js`（読み取り専用）と `${CLIENT_BACKUP_ROOT}/android`（書き込み可）をマウントし、`ANDROID_BACKUP_ROOT` を渡した。ページに実行ボタン・項目チェック・進捗ログ・最終バックアップ一覧を追加。実機で `/` が200、バンドル配信、`/api/android/index` が `{}`、手動の chunk→finish→manifest 往復で `android/<端末>/files` と `index.json`・`manifest.json` ができることを確認した。
- 2026-10-02: **配備で見つけた修正: NFS上のマウント元。** Docker は bind マウント元が無いと作成時に chown を試み、`all_squash` の NFS で `operation not permitted` になった。`manage.py init` が `${CLIENT_BACKUP_ROOT}/android` を先に作るようにした（root が作ると NFS 側で 101:101 になる）。実機で chunk→finish→manifest→index の往復、`files/DCIM/a.jpg` の中身、`index.json` を確認してテストデータは削除した。
- 2026-10-02: **Vivaldi 対応とバインドマウントの再作成。** 利用者は Vivaldi のみ使うため、文言を「Chromium系（Vivaldi・Chrome・Edge など）」に直し、端末選択が出ないときは Vivaldi 8.x 以降へ更新する案内（古い版の既知の不具合 VB-101499）をバンドルへ入れた。また、`portal.py`・`portal-backup.js` は単一ファイルのバインドマウントで、Ansible が置き換えてもコンテナが古い inode を見続ける（tls_proxy と同じ）ため、`media-urbackup.yml` に「内容が変わったときだけ portal を `--force-recreate` する」タスクを追加した。実機で新しいバンドル（67,140バイト）とページの Vivaldi 表記を確認した。
