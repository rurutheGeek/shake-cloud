# web-01 のVM宣言

状態: **2026-10-05 作成**。旧 `shakeserver`（Raspberry Pi 5）で動いていた
Web アプリ（Shake-Web・pkhack・Alexa スキル・ayahuya・nginx）をここへ移す。
移行の全体は [docs/operations/handover.md](../../../../docs/operations/handover.md) と
[docs/operations/web.md](../../../../docs/operations/web.md) を参照。

- 2 vCPU・4GiB（下限2GiB）、root 32GiB、データディスク 32GiB を `/srv` にマウント
- セキュリティグループは LAN から SSH、入口（core-01）と公開の中継
  （negitoroserver、`100.92.253.28`）から 80/443、monitor-01 から node_exporter
- Ansible のグループは `web`（NetBox のタグ。`cloud.yaml` の `ledger.tags_by_name`）

## なぜ negitoroserver を SG に書くか

公開は `Cloudflare → negitoroserver（学内拠点）→ web-01` の順で、
negitoroserver の nginx stream が `proxy_protocol on` で 443 を中継する
（旧 shakeserver と同じ。設定の正本は shake-infra の proxy ロール）。
tailnet のサブネットルート（router-01）を通るので、送信元は
negitoroserver の tailnet アドレス `100.92.253.28` のまま届く。

## この state が作るもの

| リソース | 内容 |
| --- | --- |
| `shakecloud_key_pair.web` | `ssh_public_key_path` の公開鍵を cloud API へ登録 |
| `shakecloud_security_group.web` | LAN から 22、入口と中継から 80/443、monitor-01 から 9100 |
| `shakecloud_instance.web` | `img-debian13` から 2vCPU／4096MiB／OS32GiB。`tags.Name` が `web-01` |
| `shakecloud_volume.data` | 32GiB のデータディスク（`prevent_destroy`） |
| `shakecloud_volume_attachment.data` | 空きの virtio スロットへ接続 |

cloud-init はユーザー・qemu-guest-agent・Docker・データディスクのマウント
だけを行う。アプリの Compose・設定は `stacks/shake-web/` から配る。

## 外向き（egress）は自宅LANへ届かせない

公開サイトが突破されても自宅LANを踏み台にされないよう、外向きも既定拒否で
明示の許可だけにしている（DNS→`192.168.10.1`、NTP、pkdb→`192.168.10.105:5432`、
HTTP/HTTPS）。PVE の `8006`・SSH、他VMへは届かない。

**新しい SG は外向きが全許可**（EC2 と同じ）。作成時に API が付ける
「全許可」2本（`0.0.0.0/0`・`::/0` の all）は、次の手順で import して削除してある。

```bash
# 一度だけ。main.tf へ同名・同内容の resource を一時的に足してから
tools/tf services/web import \
  shakecloud_security_group_rule.egress_default_all_v4 \
  "$(tools/tf services/web output -raw security_group_id)/sgr-..."
# import 後に一時ブロックを消し、plan（2 to destroy）を apply する
```

SG を作り直すと既定が戻る。`shake_web` ロールが配備のたびに確認して revoke する。

## データディスクの扱い

- マウント先は `/srv`。`/dev/disk/by-id/virtio-<serial>` を systemd の
  `web-data-mount.service` が待ってマウントする。デバイス名の順序には依存しない。
- 空のディスクのときだけ `mkfs.ext4` する。既存のファイルシステムは上書きしない。
- `docker.service` は `web-data-mount.service` を `Requires` する。マウントに
  失敗した VM では Docker が起動しない（fail closed）。
- `shakecloud_volume.data` は `prevent_destroy`。意図的に消す場合は、先に
  バックアップを取り、このブロックの `prevent_destroy` を外してから apply する。

## 実行

```bash
# リポジトリのルートで
tools/tf services/web init
tools/tf services/web plan  -var 'ssh_public_key_path=~/.ssh/id_ed25519_pve.pub'
tools/tf services/web apply -var 'ssh_public_key_path=~/.ssh/id_ed25519_pve.pub'
tools/tf services/web output
```

アクセスキーは `platform/sops/services.sops.yaml` から `tools/tf` が渡す。
state のキーは `shake-cloud/services/web/terraform.tfstate`。

`apply` 後は次で確認する。

```bash
tools/tf services/web output
ssh debian@<address> 'systemctl is-active web-data-mount.service docker'
ssh debian@<address> 'findmnt /srv'
```

- vCPU・メモリの変更は停止中のみ（APIが拒否する）。ディスク拡張は
  in-place で、VMは置換されない。`tags` の変更は置換になる。
- 2026-10-05 時点でテンプレートは debian13。

## 検証

```bash
terraform -chdir=platform/terraform/services/web fmt -check
terraform -chdir=platform/terraform/services/web validate   # dev override が必要
```
