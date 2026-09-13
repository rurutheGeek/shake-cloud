# ディスク増設

media-01 のメディア系データは専用データディスク（`/srv/media-stack`）に置きます。**容量の増設・拡張はクラウドのボリュームAPI（`shakecloud volume resize`）か `platform/terraform/services/media`（I02）で行います。** 現在は 64GiB のデータディスク1本です。

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

## 注意

- **バックアップは別のディスク・別の機器へ取ります。** 同じディスク上に置いたバックアップは、ディスク故障の対策になりません。
- データディスクの削除は `prevent_destroy` が拒否します。意図的に消す場合は `platform/terraform/services/media/README.md` の手順に従います。
- 2本目のデータディスクが必要になったら、`platform/terraform/services/media` にボリュームと接続を足し、`cloud-init` のマウント設定も合わせて更新します（現在は1本だけを前提にしています）。
