---
title: 共有バルクストレージ（6TB USB HDD）
updated: 2026-09-22
section: 運用手順
audience: 管理者
tags:
  - ops
  - storage
  - nfs
---

# 共有バルクストレージ（6TB USB HDD）

> **更新日** 2026-09-22 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **構築済み・データ移行済み**。Proxmoxホスト（apextox）へUSB接続した6TB HDDをext4にし、**media-01**（メディアライブラリ）と**game1**（ROM原本）へNFSで共有します。宣言は Ansible ロール `platform/ansible/roles/pve_bulk_storage`（ホスト側）と `platform/ansible/media-base.yml`（media-01側）です。

VMのOSディスク・DB・アプリ状態はSSDのままです。ここへ置くのは、大きく・読み取り中心のライブラリだけにします。

## 1. 実体

| | 値 |
| --- | --- |
| ディスク | WDC WD60EZAX-00C8VB0（6TB、5400rpm、CMR）。ディスク自身の識別子で固定: `/dev/disk/by-id/ata-WDC_WD60EZAX-00C8VB0_WD-WX32D94PX6R8` |
| 接続 | Sharkoon SATA QuickPort Duo（JMicron JMS551）のUSB。**USB3ポートを使う**（USB2では実効40MB/s前後） |
| ファイルシステム | ext4、ラベル `bulk6tb`、`/srv/bulk` へUUIDマウント（`nofail,noatime`、予約領域1%） |
| 共有 | ホストの NFS。`/etc/exports.d/bulk.exports` をロールが書く |
| 内容 | `/srv/bulk/media`（media-01用の `books`・`docs`・`inbox`・`music`）、`/srv/bulk/nextcloud-data`（Nextcloudのユーザーホーム・appdata）、`/srv/bulk/roms`（game1用）、`/srv/bulk/backups`（vzdumpの保存先とgame1セーブ。[バックアップ](backup.md)） |
| 冗長性 | **無い**。単一ディスク・USB接続。唯一の保存先・唯一のバックアップにしない |

## 2. セットアップと再実行

ホスト（初回だけディスクを初期化する。既存データは消える）:

```bash
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/pve.ini \
    -e pve_bulk_storage_initialize=true \
    platform/ansible/pve-bulk-storage.yml
```

`pve_bulk_storage_initialize=true` は**ファイルシステムが無いときだけ**初期化します。既存のext4には触れません。指定せずに実行した場合、ファイルシステムが無ければ安全のため「無い」で止まります。再実行は `changed=0` です。

media-01（共有ライブラリのマウント。`media.yml` が最初に通す `media-base.yml` に含まれる）:

```bash
sops exec-env platform/sops/services.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
   .venv/bin/ansible-playbook -i platform/ansible/inventory.cloud.py \
     platform/ansible/media-base.yml'
```

## 3. media-01 のマウント

- `/srv/media-stack/library` へ `192.168.10.10:/srv/bulk/media`、`/srv/media-stack/storage/nextcloud/data` へ `192.168.10.10:/srv/bulk/nextcloud-data` を `nfs4` でマウントします。fstabは `_netdev,nofail,x-systemd.mount-timeout=30`。**Nextcloudのユーザーホーム（各ユーザーの「ファイル」）とappdataもHDD上**にあります。
- `docker.service` に `RequiresMountsFor=/srv/media-stack/library` のdrop-inがあります。**共有ライブラリをマウントできなければDockerは起動しません**（未マウントのまま原本領域へ書かせない。データディスクと同じ考え方）。
- マウントを後から足したときは、起動済みコンテナが古いローカルディスクを掴んだままです。ロールはマウントしたときに `docker` を再起動します。
- Nextcloudの外部ストレージ・Kavita・Navidrome・LocalSendの `LIBRARY_ROOT` は今までどおり `/srv/media-stack/library` です。見え方は[Nextcloudの共有ライブラリのアクセス権限](nextcloud-permissions.md)のままです。
- **Nextcloudのユーザーホーム（各ユーザーの「ファイル」）とappdata（プレビュー等）もHDD上**になりました（2026-09-23移行。303MB・408ファイルをバイト一致で確認）。画像の多いフォルダの表示はSSD時代より遅くなる可能性があります。
- 移行前のデータはSSDに `data.ssd-backup-20260923` として残っています。Nextcloudのログインとファイル表示を確認したあと、`sudo rm -rf /srv/media-stack/storage/nextcloud/data.ssd-backup-20260923` で消せます。

## 4. game1 のマウント（Bazzite）

game1はこのリポジトリのAnsible管理外（キー投入なし・guest agentなし）なので、**game1のデスクトップ端末で**実行します。

```bash
# nfs-utils が無ければ入れる（Fedora Atomicなので再起動が要る）
rpm -q nfs-utils || sudo rpm-ostree install nfs-utils
```

`/etc/fstab` へ1行足します。既存の `/srv/game1/games` に中身があれば、先に退避してください（マウントで隠れます）。

```bash
sudo mkdir -p /srv/game1/games
echo '192.168.10.10:/srv/bulk/roms /srv/game1/games nfs4 _netdev,nofail,x-systemd.mount-timeout=30 0 0' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount /srv/game1/games
findmnt /srv/game1/games
```

RomMは `/srv/game1/games` を `/romm/library:ro` で読みます（正本は `stacks/romm/README.md`）。RomMのプロジェクトを再起動すると新しい場所を読みます。

## 5. 権限とNFSオプション

| 項目 | 値 | 理由 |
| --- | --- | --- |
| media | `all_squash,anonuid=33,anongid=33` | コンテナはwww-data(33)で読み書きする。root_squashだけだとroot実行のKavitaがnobodyになり、2750のディレクトリを読めない |
| nextcloud-data | `all_squash,anonuid=33,anongid=33` | Nextcloudのユーザーホーム・appdata。mediaと同じ扱い |
| roms | `all_squash,anonuid=1000,anongid=1000` | game1の利用者がそのままコピーできる。ゲスト側のuidに依存しない |
| game1-saves | `all_squash,anonuid=1000,anongid=1000` | game1のセーブの受け取り先。romsと同じ扱い |
| 公開先 | 192.168.10.101（media-01）と192.168.10.127（game1） | LAN全体には出さない。`backups` 自体は公開しない |

ゲスト側のuidに依存しないので、VMを作り直しても共有側の所有権は変わりません。RomMコンテナはcompose側の `:ro` で原本を守ります。

## 6. 確認

```bash
# ホスト
ssh root@192.168.10.10 'findmnt /srv/bulk; exportfs -v; smartctl -a -d sat /dev/sda | head -20'

# media-01
ssh debian@192.168.10.101 'findmnt /srv/media-stack/library; df -h /srv/media-stack/library'
ssh debian@192.168.10.101 'sudo -u www-data touch /srv/media-stack/library/inbox/.probe && sudo rm /srv/media-stack/library/inbox/.probe && echo WRITE_OK'
```

2026-09-22 に、既存の `/srv/media-stack/library`（2812ファイル・12GiB）をNFS経由で移行し、**ファイル数と合計バイト数が一致**することを確認しました。Docker再起動後、Nextcloud・Kavita・Navidrome・FreshRSS・LocalSend・music-toolsはすべて healthy です。

## 7. 運用上の注意

- **USBが落ちたとき。** ホストのext4はそのまま残ります。NFSはI/Oエラーを返すので、ホストで `dmesg` と再接続を確認し、必要なら `mount /srv/bulk` → `exportfs -ra`。ゲストは `mount -a` のあと `systemctl restart docker` で戻します。
- **USBの挿し替え。** 識別子で固定しているので挿し位置を変えても同じパスです。**必ず `umount /srv/bulk` してから**抜いてください。
- **UASのエラーが繰り返すとき。** JMS551はUASで不安定な例があります（2026-09-22の設置時に1回、UAS abortと再接続を記録）。USB3ポートでも続くなら `/etc/default/grub` の `GRUB_CMDLINE_LINUX_DEFAULT` へ `usb-storage.quirks=152d:0561:u` を足して `update-grub` → 再起動し、UASを無効化します。
- **SMART。** ホストのnode_exporterが15分ごとに `smartmon_*` として集め、Grafanaの「Shake Lab storage」で健康・温度・セクター/CRC・マウント状態が見えます（[M01](../development/M01-monitoring.md)）。手元では `smartctl -a -d sat /dev/sda`。異常時は `storage` グループのアラートが鳴ります。
- **バックアップ。** このディスクはバックアップではありません（[Garage](garage.md)とは別物）。唯一のコピーになるライブラリは、別ディスク・別機器へもコピーしてください。
- **旧データの掃除。** 移行元は `/srv/media-stack/library` の下（データディスク `/dev/vdb` 上）に隠れたまま残っています。回収するときはDockerを止めてNFSを外し、ローカルの同名ディレクトリを消してから戻します。消す前に `findmnt` でNFSが外れていることを必ず確認してください。
