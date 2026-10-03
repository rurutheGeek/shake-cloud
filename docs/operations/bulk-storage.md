---
title: 共有バルクストレージ（6TB USB HDD）
updated: 2026-10-03
section: 運用手順
audience: 管理者
tags:
  - ops
  - storage
  - nfs
---

# 共有バルクストレージ（6TB USB HDD）

> **更新日** 2026-10-03 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **構築済み。2026-10-03 に「バックアップ領域」と「クラウド領域」の2つへ整理**。Proxmoxホスト（apextox）へUSB接続した6TB HDDをext4にし、vzdump などのバックアップと、クラウドAPIのHDDティア（VMのディスクとボリューム）に使います。**media-01 のデータ（共有ライブラリ・Nextcloudデータ・端末バックアップ）は、ホストの HDD を NFS で直接使うのをやめ、クラウドの HDD ボリュームへ移しました。** NFS で出すのは game1 向けの ROM とセーブだけです。

VMのOSディスク・DB・アプリ状態はSSDのままです。ここへ置くのは、大きく・読み取り中心のデータとバックアップだけにします。

## 1. 実体

| | 値 |
| --- | --- |
| ディスク | WDC WD60EZAX-00C8VB0（6TB、5400rpm、CMR）。ディスク自身の識別子で固定: `/dev/disk/by-id/ata-WDC_WD60EZAX-00C8VB0_WD-WX32D94PX6R8` |
| 接続 | Sharkoon SATA QuickPort Duo（JMicron JMS551）のUSB。**USB3ポートを使う**（USB2では実効40MB/s前後） |
| ファイルシステム | ext4、ラベル `bulk6tb`、`/srv/bulk` へUUIDマウント（`nofail,noatime`、予約領域1%） |
| 共有 | ホストの NFS（game1 向けだけ）。`/etc/exports.d/bulk.exports` をロールが書く |
| 内容 | **バックアップ領域** `/srv/bulk/backups`（vzdump の `dump`、game1 のセーブ `game1-saves`）と、**クラウド領域** `/srv/bulk/disks`（Proxmox の dir ストレージ `bulk-disks`。HDDティアのVMディスクとボリューム）。ほかに game1 用の `/srv/bulk/roms` |
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

このロールはマウント後、クラウドAPIのHDDティア用に `/srv/bulk/disks` を作り、Proxmoxの dir ストレージ `bulk-disks`（`content=images`）として登録します（未登録のときだけ）。**マウント前に登録するとVMディスクがrootに載る**ため、ロールは `mountpoint` を確認してから登録します。`bulk-backup`（vzdump）とはディレクトリもストレージも分けています。ストレージのACLは `platform/terraform/00-bootstrap`（`/storage/bulk-disks`、`CloudApiStorage` ロール）が付与します。利用者から見た使い方は[クラウドAPIとインスタンス](cloud-api.md)の `disk_tier` です。

media-01（共有ライブラリのマウント。`media.yml` が最初に通す `media-base.yml` に含まれる）:

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
   .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml \
     platform/ansible/media-base.yml'
```

## 3. media-01 のマウント

media-01 のデータは、クラウドの HDD ボリューム（`platform/terraform/services/media` の `shakecloud_volume.bulk`、500GiB、実際に書いた分だけ HDD を使う）に置きます。

- `media-base.yml` がボリュームをラベル `media-bulk` で `/srv/media-bulk` へ載せ、その下の3つのディレクトリをアプリの場所へ bind します。`library` → `/srv/media-stack/library`、`nextcloud-data` → `/srv/media-stack/storage/nextcloud/data`、`client-backups` → `/srv/media-stack/client-backups`。
- ボリュームの初期化（mkfs）は、デバイスを明示したときだけ行います。中身のあるデバイスは消しません。デバイスは `tools/tf services/media output bulk_device_path` の値です。

    ```bash
    ... platform/ansible/media-base.yml -e media_bulk_initialize_device=/dev/disk/by-id/virtio-vol...
    ```

- `docker.service` に `RequiresMountsFor` のdrop-in（`20-media-library.conf`）があります。**この3つをマウントできなければDockerは起動しません**（未マウントのまま原本領域へ書かせない）。
- Nextcloudの外部ストレージ・Kavita・Navidrome・LocalSendの `LIBRARY_ROOT` は今までどおり `/srv/media-stack/library` です。見え方は[Nextcloudの共有ライブラリのアクセス権限](nextcloud-permissions.md)のままです。
- 所有権はコンテナの利用者そのまま（`library`・`nextcloud-data` は www-data 33、`client-backups` は UrBackup 101）。NFS の頃の `all_squash` による読み替えはもうありません。

## 領域ごとの上限

パーティションは切り直さず、ext4 のプロジェクトクォータでディレクトリごとに上限を持たせています。片方が膨らんでも、もう片方の空きを食いません。上限に達した領域への書き込みは「ディスクが満杯」と同じ失敗になります。

| 領域 | 場所 | 上限 |
| --- | --- | --- |
| バックアップ | `/srv/bulk/backups` | 2000GiB |
| クラウド | `/srv/bulk/disks` | 3400GiB |

値は `platform/ansible/roles/pve_bulk_storage/defaults/main.yml` の `pve_bulk_storage_quotas` です。使用量は `repquota -P /srv/bulk` で見ます。クォータの機能を初めて入れるときだけアンマウントが要るので、HDD を使うVMを止めてから `-e pve_bulk_storage_enable_quota_offline=true` を付けて実行します。

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
| roms | `all_squash,anonuid=1000,anongid=1000` | game1の利用者がそのままコピーできる。ゲスト側のuidに依存しない |
| game1-saves | `all_squash,anonuid=1000,anongid=1000` | game1のセーブの受け取り先。romsと同じ扱い |
| 公開先 | 192.168.10.127（game1）だけ | LAN全体には出さない。`backups` 自体は公開しない |

ゲスト側のuidに依存しないので、VMを作り直しても共有側の所有権は変わりません。RomMコンテナはcompose側の `:ro` で原本を守ります。

## 6. 確認

```bash
# ホスト
ssh root@192.168.10.10 'findmnt /srv/bulk; exportfs -v; smartctl -a -d sat /dev/sda | head -20'

# 領域ごとの使用量と上限
ssh root@192.168.10.10 'repquota -P /srv/bulk'

# media-01
ssh debian@192.168.10.101 'findmnt /srv/media-bulk /srv/media-stack/library; df -h /srv/media-bulk'
ssh debian@192.168.10.101 'sudo -u www-data touch /srv/media-stack/library/inbox/.probe && sudo rm /srv/media-stack/library/inbox/.probe && echo WRITE_OK'
```

2026-09-22 に、既存の `/srv/media-stack/library`（2812ファイル・12GiB）をNFS経由で移行し、**ファイル数と合計バイト数が一致**することを確認しました。Docker再起動後、Nextcloud・Kavita・Navidrome・FreshRSS・LocalSend・music-toolsはすべて healthy です。

## 7. 運用上の注意

- **USBが落ちたとき。** ホストのext4はそのまま残ります。NFSはI/Oエラーを返すので、ホストで `dmesg` と再接続を確認し、必要なら `mount /srv/bulk` → `exportfs -ra`。ゲストは `mount -a` のあと `systemctl restart docker` で戻します。
- **USBの挿し替え。** 識別子で固定しているので挿し位置を変えても同じパスです。**必ず `umount /srv/bulk` してから**抜いてください。
- **UASのエラーが繰り返すとき。** JMS551はUASで不安定な例があります（2026-09-22の設置時に1回、UAS abortと再接続を記録）。USB3ポートでも続くなら `/etc/default/grub` の `GRUB_CMDLINE_LINUX_DEFAULT` へ `usb-storage.quirks=152d:0561:u` を足して `update-grub` → 再起動し、UASを無効化します。
- **SMART。** ホストのnode_exporterが15分ごとに `smartmon_*` として集め、Grafanaの「Shake Lab storage」で健康・温度・セクター/CRC・マウント状態が見えます（[M01](../development/M01-monitoring.md)）。手元では `smartctl -a -d sat /dev/sda`。異常時は `storage` グループのアラートが鳴ります。
- **HDDティアのVMディスク。** クラウドAPIの `disk_tier: hdd` は `/srv/bulk/disks` へ qcow2 で置きます。**5400rpm・USB接続なのでランダムI/Oは得意ではなく、DBやOSの起動ディスクには向きません。** 大きいが普段は眠っているVM（アーカイブ、検証、メディア処理の作業台）向けです。**この1台が落ちるとHDD上のVMはI/Oエラーで止まり、バックアップ・メディア・Nextcloudも同時に落ちます。**vzdumpの `vm_disk_max_used_percent`（既定85%）はHDDのファイルシステム全体（バックアップ・メディア含む）の使用率で判定するので、HDDを埋めると新規作成が止まります。
- **バックアップ。** このディスクはバックアップではありません（[Garage](garage.md)とは別物）。唯一のコピーになるライブラリは、別ディスク・別機器へもコピーしてください。
- **旧データの掃除。** 移行元は `/srv/media-stack/library` の下（データディスク `/dev/vdb` 上）に隠れたまま残っています。回収するときはDockerを止めてNFSを外し、ローカルの同名ディレクトリを消してから戻します。消す前に `findmnt` でNFSが外れていることを必ず確認してください。
