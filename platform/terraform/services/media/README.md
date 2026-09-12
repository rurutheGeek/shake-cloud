# media-01 のVM宣言

状態: **apply済み・実機確認済み（2026-09-12）**。`i-a06df9a2dfd1ce6db`、
`192.168.10.101`、4vCPU／6GiB、OS32GiB＋データ64GiB。再 plan は No changes、
再起動後もデータマウントと Docker が復帰することを確認した。

担当は[I02 media-01](../../../../docs/development/I02-media-vm.md)。初期予算は
4vCPU／6GiB、OS32GiB＋データ64GiB。I01のホスト測定・軽量化は記録済み。
アプリの実データ・索引・復元領域は移行（W03〜W06）の前後に測って容量を見直す。

## この state が作るもの

| リソース | 内容 |
| --- | --- |
| `shakecloud_key_pair.media` | `ssh_public_key_path` の公開鍵を cloud API へ登録 |
| `shakecloud_security_group.media` | LAN から 22・80・443 だけを許可 |
| `shakecloud_instance.media` | `img-debian13` から 4vCPU／6144MiB／OS32GiB。`tags.Name` が `media-01` |
| `shakecloud_volume.data` | 64GiB のデータディスク（`prevent_destroy`） |
| `shakecloud_volume_attachment.data` | 空きの virtio スロットへ接続 |

cloud-init はユーザー・qemu-guest-agent・Docker・データディスクのマウント
だけを行う。アプリのCompose・設定は `stacks/media/` と `stacks/music-tools/` から配る（W03〜W06）。

## データディスクの扱い

- マウント先は `/srv/media-stack`。`/dev/disk/by-id/virtio-<serial>` を
  systemd の `media-data-mount.service` が待ってマウントする。デバイス名の
  順序には依存しない。
- 空のディスクのときだけ `mkfs.ext4` する。既存のファイルシステムは上書きしない。
- `docker.service` は `media-data-mount.service` を `Requires` する。マウントに
  失敗した VM では Docker が起動しない。未マウントのまま原本ディレクトリへ
  書かせない（fail closed）。
- `shakecloud_volume.data` は `prevent_destroy`。データディスクの削除を含む計画は拒否される。
  意図的に消す場合は、先にバックアップを取り、このブロックの `prevent_destroy`
  を外してから `terraform apply` する。volume の `tags` 変更は置換になるため
  このガードに当たる。

## 実行

`apply` の前に [terraform-provider.md](../../../../docs/operations/terraform-provider.md)
の dev override を設定し、アクセスキーを渡す。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'

tools/tf services/media init   # リポジトリのルートで実行
tools/tf services/media plan
tools/tf services/media apply
```

`tools/tf` の services 分岐（I05）は、state の bucket・endpoint・資格情報を
`platform/sops/s3.sops.yaml` から、`SHAKECLOUD_ACCESS_KEY` を呼び出し元の
環境変数から渡す。Proxmox・NetBox・Cloudflare の資格情報は渡さない。
`init` はキー無しでも通るが、`plan`・`apply` はキーが無ければ止まる。
state のキーは `shake-cloud/services/media/terraform.tfstate`。

`apply` 後は次で確認する。

```bash
tools/tf services/media output
ssh debian@<address> 'systemctl is-active media-data-mount.service docker'
ssh debian@<address> 'findmnt /srv/media-stack'
```

- 全体への `terraform destroy` はデータディスクも削除対象になるため、
  `prevent_destroy` により拒否される。VMだけを廃止する場合は、データを維持する
  宣言変更と復旧手順を先にレビューし、削除対象を plan で確認する。
- vCPU・メモリの変更は停止中のみ（APIが拒否する）。ディスク拡張は
  in-place で、VMは置換されない。
- services-01 は既存 `05-seed`、game1 は既存 cloud 管理のまま。この state に
  他のVMを宣言しない。

## 検証

```bash
terraform -chdir=platform/terraform/services/media fmt -check
terraform -chdir=platform/terraform/services/media validate   # dev override が必要
.venv/bin/python -m unittest tests.test_media_vm
```
