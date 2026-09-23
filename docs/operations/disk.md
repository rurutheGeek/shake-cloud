---
title: ディスク増設
updated: 2026-09-13
section: 運用手順
audience: 管理者
tags:
  - ops
  - storage
---

# ディスク増設

> **更新日** 2026-09-13 ・ **区分** 運用手順 ・ **読む人** 管理者

media-01 のメディア系データは専用データディスク（`/srv/media-stack`）に置きます。**容量の増設・拡張はクラウドのボリュームAPI（`shakecloud volume resize`）か `platform/terraform/services/media`（I02）で行います。** 現在は 64GiB のデータディスク1本です。

大容量のメディアライブラリ・ROM原本は、ホスト直結の6TB USB HDDへ置いてNFSで共有します。こちらはデータディスクの拡張ではなく、[共有バルクストレージ（6TB USB HDD）](bulk-storage.md)の手順です。

## 現在の構成

- デバイスは `/dev/disk/by-id/virtio-<serial>` です。`vda`・`vdb` のようなデバイス名の順序には依存しません。
- systemd の `media-data-mount.service` がデバイスの出現を待ち、`/srv/media-stack` へマウントします。
- ファイルシステムが無いディスクのときだけ `mkfs.ext4` します。既存のファイルシステムは上書きしません。
- `docker.service` は `media-data-mount.service` を `Requires` します。**マウントに失敗した VM では Docker が起動しません**（未マウントのまま原本領域へ書かせない）。
- ボリュームは `prevent_destroy` です。VM を消してもデータディスクは残ります。

保存対象は `/srv/media-stack/library` 配下の `books`・`music`・`docs`・`inbox` で、Nextcloud はこれを外部ストレージとして見せます（[Nextcloudの共有ライブラリのアクセス権限](nextcloud-permissions.md)）。アプリの状態は VM の OS ディスク（`/opt/media-stack/` 配下）にあります。

## 容量を拡張する

ディスクは**拡大のみ**で、縮小はできません。VM は置換されず、稼働中に拡張できます。

まず現在の使用量と空きを確認します。

```bash
shakecloud volume ls
ssh debian@192.168.10.101 'df -hT /srv/media-stack'
```

クラウド側で拡張します。

```bash
shakecloud volume resize vol-cff33af40771b2b74 128
```

宣言を正本にする場合は、`platform/terraform/services/media` の `data_disk_gib` を変えて適用します。

```bash
# data_disk_gib を 128 にしてから
tools/tf services/media plan
tools/tf services/media apply
```

どちらの場合も、**ゲスト側でファイルシステムを広げる作業が別に必要です**。ボリュームはパーティションを切らずに ext4 を直接作っているので、`resize2fs` をそのデバイスへ実行します。

```bash
ssh debian@192.168.10.101
DEV=$(findmnt -n -o SOURCE /srv/media-stack)
sudo resize2fs "$DEV"
df -hT /srv/media-stack
```

## 拡張後の確認

```bash
ssh debian@192.168.10.101 'systemctl is-active media-data-mount.service docker'
ssh debian@192.168.10.101 'findmnt /srv/media-stack'
ssh debian@192.168.10.101 'df -hT /srv/media-stack'
```

再起動後も、`media-data-mount.service` が先に動き、Docker がその後に起動することを確認します。

## 寿命を延ばす設定

SSDへの無駄な書き込みを減らす設定を、ホストとサービスVMへ当ててあります。正本は `platform/ansible/roles/storage_health` と `platform/ansible/storage-health.yml` です。

| 対策 | 内容 | 効果 |
| --- | --- | --- |
| discard | game1の `scsi0` に `discard=on`（2026-09-23追加。**次回起動から有効**） | ゲストの削除をLVM-thinまで伝え、空きを返す。書き込み増幅を抑える |
| noatime | `/` のマウントオプション（ホスト・サービスVM） | 読み取りのたびのatime更新を止める |
| journald上限 | `/etc/systemd/journald.conf.d/20-storage-health.conf`（`SystemMaxUse=200M`） | ログの容量・書き込みの暴走を防ぐ |
| Dockerログ上限 | `/etc/docker/daemon.json`（`max-size=10m`・`max-file=3`） | json-fileの無制限成長を止める。**既存コンテナは次に再作成されたときから** |

```bash
# ホスト
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/storage-health.yml
# monitor-01 と identity
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/monitor.ini platform/ansible/storage-health.yml
# media-01（クラウドVM）
sops exec-env platform/sops/services.sops.yaml \
  '.venv/bin/ansible-playbook -i platform/ansible/inventory.cloud.py platform/ansible/storage-health.yml'
```

Dockerを止めたくないときは `-e storage_health_restart_docker=false`（次回の配備・再起動で反映）。

**見える化**: Grafanaの「Shake Lab storage」にNVMeの総書込量・書込速度と、HDDのLoad Cycle／Start-Stop／Power-On時間を出しています（[M01](../development/M01-monitoring.md)）。2026-09-23時点はNVMeが2.08TB／355時間（寿命消費0%）、HDDが33℃・Load Cycle 110,682・Start/Stop 8,085です。

**HDD側の注意**: 満杯にしない（空き10%でアラート）／通気と温度／USBケーブル・ポート（UASエラー再発時はquirk）／DBやVMディスクを置かない（順次アクセス専用）／スピンダウンはブリッジがAPM非対応なので自然なstandbyに任せる。

## 注意

- **バックアップは別のディスク・別の機器へ取ります。** 同じディスク上に置いたバックアップは、ディスク故障の対策になりません。
- データディスクの削除は `prevent_destroy` が拒否します。意図的に消す場合は `platform/terraform/services/media/README.md` の手順に従います。
- 2本目のデータディスクが必要になったら、`platform/terraform/services/media` にボリュームと接続を足し、`cloud-init` のマウント設定も合わせて更新します（現在は1本だけを前提にしています）。
