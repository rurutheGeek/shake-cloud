---
title: クライアント端末のバックアップ（Windows・Android）
updated: 2026-10-02
section: 運用手順
audience: 全員
tags:
  - ops
  - backup
  - urbackup
  - android
---

# クライアント端末のバックアップ（Windows・Android）

> **更新日** 2026-10-02 ・ **区分** 運用手順 ・ **読む人** 全員

**状態**: **配備済み（2026-10-02）。** 入口は **<https://backup.apextox.dpdns.org>**（バックアップポータル。Forward Auth）で、端末の状態と操作をここに集めています。Windows は media-01 の UrBackup が**ファイルとシステムイメージの世代バックアップ**を取ります。Android は家族全員 Galaxy のため、**ポータルの「スマホをバックアップ」ボタン（USB・WebUSB）**で写真・書類・APKを media-01 のHDDへ保存します（アプリ内部データはAndroidの制限で対象外。機種変更の引き継ぎは Smart Switch）。保存先は6TB HDD の `/srv/bulk/client-backups` で、この HDD が単一障害点である点は[共有バルクストレージ](bulk-storage.md)の注意のままです。

## 1. 全体像

| 端末 | 守るもの | 実装 | 入口 |
| --- | --- | --- | --- |
| Windows PC | システムイメージ（C:）とファイル（`C:\Users`）の世代 | UrBackup サーバー＋公式 Windows クライアント | ポータル／管理画面 `https://urbackup.apextox.dpdns.org`（Forward Auth）。クライアントは `192.168.10.101:55413` へ直結 |
| Galaxy（家族全員） | 写真・動画・ダウンロード・書類・アプリAPK | ポータルのボタン（USB・WebUSB）でブラウザーから直接読み取り | `https://backup.apextox.dpdns.org`（Chromium系: Vivaldi・Chrome・Edge など） |
| 機種変更の引き継ぎ | 連絡先・SMS・設定・アプリデータ | Smart Switch（純正アプリ） | 端末またはPCの Smart Switch |

## 2. Windows PC

### 2.1 クライアントの導入

1. ブラウザーで <https://backup.apextox.dpdns.org> を開き、共通ログイン（SSO）で入る。ここが全体の入口（バックアップポータル）。
2. ポータルの「UrBackup 管理画面」（<https://urbackup.apextox.dpdns.org>）を開き、「Status」から Windows 用クライアント（`UrBackup Client … .msi`）をダウンロードしてインストールする。ダウンロードが使えない場合は [urbackup.org](https://www.urbackup.org/download.html) の同系（2.5.x）を使う。
3. インストール後、**同じ LAN にいれば自動発見**される。数分待っても「Status」に現れない場合は、Web UI の **「Add new client」（クライアント追加）** へ PC の IP かホスト名を入れる（サーバーからその端末へ直接問い合わせる）。Windows 側のファイアウォールで UrBackup Client が**プライベートネットワーク**で許可されていることも確認する。

### 2.2 動き

- ファイルバックアップは既定で毎時、イメージバックアップは定期（既定の保持はファイル増分100・フル10、イメージ増分30・フル5。最低世代はそれぞれ `min_*` で確保）。
- 初回のファイル＋イメージは容量と回線に時間がかかる。Web UI の「Activities」で進行を見る。
- 設定はサーバー側が正（クライアント側の変更は上書きされる）。対象は `settings.json` の `default_dirs`（`C:\Users`）と `image_letters`（`C:`）。D: なども取るなら `image_letters` を `ALL` にする（容量に注意）。

### 2.3 復元

- **ファイル**: Web UI の「Backups」から該当世代を開き、必要なファイルをダウンロード／復元する。クライアントのトレイアイコン →「Access/restore backups」からも同じ Web UI を開ける（`server_url` を HTTPS にしてあるため SSO を通る）。
- **システムイメージ（ベアメタル）**: [UrBackup の復元メディア](https://www.urbackup.org/restore.html)で USB/CD を作り、対象 PC を起動してサーバー `192.168.10.101` へ接続し、戻す世代を選ぶ。**この演習は未実施**。実施したら[配備台帳](handover.md)へ記録する。

## 3. Android（Galaxy・USB＋WebUSB）

**ポータルのボタン1つで、USBでつないだGalaxyの写真・書類・APKを media-01 へ保存します。** スマホ側にアプリは入れません（ADBの許可だけ）。ブラウザーからUSB経由で直接読み取ります（WebUSB）。

| 対象 | 方法 | 備考 |
| --- | --- | --- |
| 写真・動画（DCIM・Pictures） | ポータルの「スマホをバックアップ」 | 変更のないファイルは2回目以降スキップ |
| ダウンロード・書類（Download・Documents） | 同上 | |
| アプリ（APK） | 同上（チェックを入れる） | 再インストール用。データは入らない |
| アプリ内部データ（ログイン・セーブ） | **不可（Androidの制限）** | 機種変更時は Smart Switch の引き継ぎを使う |

### 3.1 準備（初回だけ・端末ごと）

1. 端末の「設定」→「デバイス情報」→「ビルド番号」を7回タップして開発者向けオプションを出す。
2. 「開発者向けオプション」→「USBデバッグ」をON。
3. Galaxy をUSBでPCへつなぎ、端末に出る「USBデバッグを許可しますか」で**許可**（このPCを常に信頼してよい）。

### 3.2 バックアップ（ふだん）

1. **Chromium系ブラウザー（Vivaldi・Chrome・Edge など）**で <https://backup.apextox.dpdns.org> を開く（FirefoxはWebUSB非対応）。
2. Galaxy をUSBでつなぐ。One UI 8 は通知から「ファイルを転送／Android Auto」を選ぶ。
3. 「Android をバックアップ」の項目を選び、**「スマホをバックアップ」**を押す。
4. 端末選択のダイアログで Galaxy を選ぶ。画面のログにファイル数とサイズが出て、終わると一覧に最終バックアップが表示される。

- 2回目以降は、サイズと更新時刻が同じファイルを飛ばすので短時間で終わる。
- 画面ロックは解除しておく（ADBの許可と読み取りのため）。
- Windowsで他のADBツール（スマホ管理ソフト等）が動いているとUSBを取り合って失敗する。閉じてから実行する。
- 保存先: `/srv/bulk/client-backups/android/<端末>/files/...`（写真・書類）と `apk/`。インデックスは `index.json`。

### 3.3 復元

- **写真・ファイル**: ポータルやNextcloudからダウンロードして端末へ戻す（今は手動）。サーバー側の原本は消えない。
- **アプリ**: 保存したAPKを入れ直し、必要なら再ログイン。
- **機種変更の引き継ぎ**: Smart Switch（純正アプリ、Galaxy同士/PC経由）を使う。連絡先・SMS・設定・アプリデータはこちら。

## 4. 保存先と保持

- サーバー状態: `/srv/media-stack/storage/urbackup`（ローカルデータディスク。`manage.py backup` の対象）
- バックアップ本体: `/srv/bulk/client-backups/urbackup`（6TB HDD。NFS で media-01 の `/srv/media-stack/client-backups` にマウント）
- 空き容量が厳しくなると、UrBackup が古い世代から削除する（ソフトクォータ95%）。Grafana の「Shake Lab storage」で HDD の空きを監視する。
- **HDD は冗長化されていない。** 端末バックアップも唯一のコピーにしないよう、別ディスク・別機器への2次コピーを後日足す（[O01](../development/O01-cloud-backup.md) 系の課題）。

## 5. 設定の変更と確認

入口は2つです。**ポータル**（<https://backup.apextox.dpdns.org>）は状態と手順、**UrBackup 管理画面**（<https://urbackup.apextox.dpdns.org>）はクライアント配布・世代・復元を扱います。どちらも Forward Auth（SSO）の内側です。

設定の正本はスタックの `settings.json` で、`configure` が Web API 経由で冪等に適用します。

```bash
# media-01（sudo 可）
cd /opt/media-stack/media/urbackup
sudo python3 manage.py status      # コンテナの状態
sudo python3 manage.py configure   # settings.json を適用（2回目は OK: 変更なし）
sudo cat secrets/urbackup_admin_password   # Web UI の admin パスワード
```

`settings.json` を変えたら `platform/ansible/media-urbackup.yml` を再実行します。クライアント個別の設定は Web UI で行えますが、サーバー既定（`settings.json`）が優先されます。メール通知は未設定なので、失敗は Web UI の「Activities」「Logs」で確認します。
