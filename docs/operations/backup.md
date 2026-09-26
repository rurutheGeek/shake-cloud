---
title: バックアップ（重要VM・game1セーブ）
updated: 2026-09-22
section: 運用手順
audience: 管理者
tags:
  - ops
  - backup
  - storage
---

# バックアップ（重要VM・game1セーブ）

> **更新日** 2026-09-22 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **週次vzdumpを設定・初回取得済み**。保存先は6TB USB HDD（`/srv/bulk/backups`、Proxmoxの `bulk-backup` ストレージ）です。宣言は Ansible ロール `platform/ansible/roles/pve_backup` と `platform/ansible/pve-backup.yml`、game1のセーブは `tools/game1-saves-backup.sh` です。

## 1. 何を「大事」とみなすか

**再取得できないもの**だけを取ります。OS・コンテナイメージ・ゲーム本体・Ollamaモデル・メディア原本は再取得できるので含めません。

| 優先 | 対象 | 目安 | 理由 |
| --- | --- | --- | --- |
| 1 | 140 cloud-01 | ~7G | 管理DB（VM・ボリューム・SG・鍵の台帳） |
| 1 | 110 identity | ~6G | Authentikのユーザー・パスキー設定 |
| 1 | 150 services-01 | ~15G | Home Assistant設定・履歴 |
| 1 | 101 router-01 | ~0.2G | ルータ設定 |
| 1 | 5001 media-01 | ~40G | Nextcloud DB・設定（ライブラリ原本はHDD側） |
| 1 | 130 storage-s3 | ~2.5G | GarageのS3データ |
| 1 | 401 dev-b | ~18G | SSH鍵・SOPS age鍵・未コミットの作業 |
| 1 | 5002 monitor-01 | ~11G | 監視履歴（再生成不可。必須度は中） |
| 1 | game1 のセーブ | 数G | `/home` 全体（~237G）は取らず、セーブだけ別途 |
| 2 | k8s 200/210/211 | ほぼ0 | Fluxで再構築可。PVCの中身は別途確認 |
| 2 | 100 game1 全体 | ~237G | ゲーム・モデルが大半。丸ごとは取らない |
| 3 | メディア原本 | 12G+ | **すでにUSB HDD上**。同一ディスクへは取れない |

**最重要は `~/.config/sops/age/keys.txt`（dev-b）です。** これが無いとリポジトリの秘密値が復号できません。[秘密値の管理](secrets.md)の方針どおり、管理PCと外部コピーの2箇所にあることを確認してください。

## 2. 仕組み

- 保存先は Proxmox の `dir` ストレージ `bulk-backup`（`/srv/bulk/backups`）。`pve_backup` ロールが登録します。
- `/cluster/backup` にジョブを1つ作ります。**毎週日曜 06:00、snapshotモード、zstd、keep-last=4**。深夜は利用中のことがあるため早朝にしています。
- snapshotはLVM-thinのスナップショットなので、稼働中のVMが止まりません。VM設定も一緒に残ります。
- ジョブの名前は `shake-cloud tier1 weekly`。ロールはこのコメントで既存ジョブを探して作成／更新します。

## 3. セットアップと再実行

保存先のディスクを先に用意します（[共有バルクストレージ](bulk-storage.md)）。

```bash
# 1) ディスク・共有（初回のみ -e pve_bulk_storage_initialize=true）
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-bulk-storage.yml

# 2) バックアップジョブ
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
  .venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-backup.yml
```

対象VMを変えるときは `platform/ansible/roles/pve_backup/defaults/main.yml` の `pve_backup_vmids` を直して再実行します。

## 4. 確認と手動実行

```bash
# ジョブと次回時刻
ssh root@192.168.10.10 'pvesh get /cluster/backup'
# 保存先と容量
ssh root@192.168.10.10 'pvesm status | grep bulk; ls -lh /srv/bulk/backups/dump | tail'

# 1台だけ手動で取る（例: cloud-01）
ssh root@192.168.10.10 'vzdump 140 --storage bulk-backup --mode snapshot --compress zstd'
```

週次の結果は Proxmox の通知（UIの通知履歴）で確認します。**失敗通知の監視スタック連携は未了**です。

## 5. 復元

VM全体を戻す場合は、既存VMを消さずに別VMIDへ戻して確認します。

```bash
ssh root@192.168.10.10
ls /srv/bulk/backups/dump
qmrestore /srv/bulk/backups/dump/vzdump-qemu-140-<日時>.vma.zst 5140 --storage local-lvm
qm start 5140
```

**ファイル単体が欲しいとき**も、一時VMへ復元してからコピーするのが安全です（vmaからの手作業抽出はミスしやすい）。全体の復旧順序は[VM・アプリ状態の復元](../development/O03-restore.md)に従います。

## 6. game1 のセーブ

game1はAnsible管理外なので、**game1の端末で**実行します。まず保存先をNFSマウントします（[共有バルクストレージ](bulk-storage.md) §4と同じ要領）。

```bash
sudo mkdir -p /srv/game1/backup
echo '192.168.10.10:/srv/bulk/backups/game1-saves /srv/game1/backup nfs4 _netdev,nofail,x-systemd.mount-timeout=30 0 0' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount /srv/game1/backup
findmnt /srv/game1/backup
```

`tools/game1-saves-backup.sh` をgame1へ置き、**自分のユーザーで**実行します（sudo不要）。保存対象はスクリプト冒頭の `SAVE_PATHS` です。`du -sh` で大きさを確かめ、ゲーム本体（`steamapps/common`）やモデルを入れないでください。

```bash
chmod +x game1-saves-backup.sh
./game1-saves-backup.sh
```

毎週自動で取る場合はユーザー単位のsystemd timerにします。

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/game1-saves-backup.service <<'EOF'
[Unit]
Description=Back up game1 saves to the bulk HDD
[Service]
Type=oneshot
ExecStart=%h/game1-saves-backup.sh
EOF
cat > ~/.config/systemd/user/game1-saves-backup.timer <<'EOF'
[Unit]
Description=Weekly game1 saves backup
[Timer]
OnCalendar=Sun 06:30
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now game1-saves-backup.timer
```

## 7. 限界と注意

- **同じ筐体・単一ディスクです。** NVMe故障には効きますが、HDD自身の故障・火災・盗難・ランサムウェアには無力です。特に重要なものは別機器・別拠点へもコピーしてください。
- **メディア原本とNextcloudのユーザーファイル（`/srv/bulk/media`・`/srv/bulk/nextcloud-data`）はこのHDD上にあり、同じHDDへバックアップできません。** media-01のvzdumpには含まれない（NFSはVMのディスクではない）ため、**これらは別の外付けやGarageなど、別の障害単位へコピーしてください**。
- **DBの整合はクラッシュ整合です。** PostgreSQL/MariaDBはWALで概ね戻せますが、厳密な論理ダンプ（`pg_dump`・`mariadb-dump`）は未実装です（[O01](../development/O01-cloud-backup.md)・[O02](../development/O02-cnpg-backup.md)）。
- **age鍵のコピーを忘れない。** 秘密値は鍵とセットで初めて復元できます。
- 保存先が未マウントのままバックアップするとrootを埋めます。`pve_backup` ロールはマウントを確認して止まりますが、手動の `vzdump` はその限りではありません。
