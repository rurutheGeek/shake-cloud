---
title: クラウドAPIの運用
updated: 2026-10-23
section: 運用手順
audience: 管理者
tags:
  - ops
  - cloud
---

# クラウドAPIの運用

> **更新日** 2026-10-23 ・ **区分** 運用手順 ・ **読む人** 管理者

自作クラウド shakecloud の管理者向けの手順です。使い方は[クラウドの使い方](../services/cloud.md)、作った理由と設計は[最小クラウドとProvider](../architecture/cloud.md)、API の正本は `cloud/openapi/shakecloud.yaml` です。

## 1. 置き場所

| もの | 場所 |
| --- | --- |
| API・ポータル・管理DB | cloud-01（`192.168.10.205`）の `/opt/cloud-stack`。入口は `https://cloud.apextox.dpdns.org` |
| S3（Garage） | cloud-01。S3 API は `http://192.168.10.205:3900`（[Garage](garage.md)） |
| database・function | Kubernetes（k8s-cp-01）の CloudNativePG と Knative（[Kubernetes](kubernetes.md)） |
| コード | `cloud/api`（API とポータル）・`cloud/client`・`cloud/cli`・`cloud/provider`・`cloud/mcp` |
| 配備 | `platform/ansible/cloud.yml`（ロール `cloud_api`） |
| Proxmox 側の権限 | `platform/terraform/00-bootstrap`（`cloudapi@pve`・ロール・ACL・`cloud-images` ストレージ・データセンターFW） |
| 秘密値 | `platform/sops/cloudapi.sops.yaml`（Proxmox・NetBox・Garage のトークン）。cloud-01 の `/opt/cloud-stack/secrets/` |

## 2. 配備・更新

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/cloud.yml'
```

- API のイメージは cloud-01 でビルドする。DB のマイグレーションは起動時に自動で流れる。
- 再実行で変更ゼロになる。

## 3. 初めから作り直すとき

順番は[初回セットアップの順番](bootstrap.md)が正本です。クラウドに関わる部分だけを抜き出します。

1. 実機を読み取って `site.yaml` を作る: `.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/survey-pve.yml` → `python3 tools/site-yaml.py .survey/<ホスト名>.facts.json`
2. Proxmox 側の権限: `tools/tf 00-bootstrap apply`。**実質 root と同じ権限で動く**ので、人が手元から流す。
3. トークンを SOPS へ: `tools/tf 00-bootstrap output -raw cloudapi_token_value` を `sops platform/sops/cloudapi.sops.yaml` に入れる。
4. NetBox（[NetBox](netbox.md)）と Authentik（[認証基盤](identity.md)）を用意する。
5. 上の「配備・更新」を流し、下の「実機プローブ」を流す。

## 4. 管理者の操作

| したいこと | やり方 |
| --- | --- |
| 容量と上限を見る・変える | ポータルの「容量」「上限」。`GET /v1/capacity`、`PUT /v1/limits` |
| 既存の VM をクラウドへ引き取る | `ssh root@192.168.10.10 qm set <VMID> --pool cloud` のあと `POST /v1/instances/adopt`（`vmid`・`account_id`・`private_ip_address`） |
| 利用者を招く | [認証基盤](identity.md)の招待 |
| 管理用の鍵が要る（緊急時） | cloud-01 で `sudo sh -c 'cd /opt/cloud-stack && python3 manage.py rotate-bootstrap-key'`。使い終えたら `disable-bootstrap-key` |
| Windows の VM | [Windows 11 Pro の VM](windows.md) |

**上限を 0（無制限）にしても、ホストを守る検査は残ります。** ノードに残すメモリ（既定 4GiB）、ディスクの使用率（既定 85%）を 0 にすると、ホストごと倒せます。

## 5. 管理DBのバックアップと戻し方

`cloud-backup.timer` が毎日 `/var/backups/cloud-api` へ取り、14世代残します。最終成功時刻は監視が見ています。

```bash
sudo sh -c 'cd /opt/cloud-stack && python3 manage.py backup --destination /var/backups/cloud-api --keep 14'
```

```bash
sudo sh -c 'cd /opt/cloud-stack && cat /var/backups/cloud-api/<stamp>/shakecloud.dump | \
  docker compose -f compose.yaml exec -T postgres pg_restore -U shakecloud -d shakecloud --clean --if-exists'
```

同じ機械の上の写しなので、ディスクが壊れたら一緒に失われます（[#212](https://github.com/rurutheGeek/shake-cloud/issues/212)）。

## 6. 実機プローブ

Proxmox を更新したら流します。`cloudapi@pve` の絞った権限で、設計の前提（空き容量が読める・ISO を消せる・`platform` プールには作れない・コンソール・ディスクの付け替え・VM のファイアウォール）が成り立つかを自動で判定します。使い捨ての VM（5998・5999）を作って必ず片付けます。

```bash
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-cloud.py'
```

ボリュームとセキュリティグループを実際に遮断・許可するところまで見るときは、ポータルで発行したアクセスキーで次も流します。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_...'
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-volumes.py'
```

## 7. 元に戻す

- `tools/tf 00-bootstrap destroy` で `cloudapi@pve`・ACL・`cloud-images` ストレージは消える。**`/srv/cloud-images` の中身は残る**ので、利用者のイメージが無いか確かめてから消す。
- NetBox の `cloudapi` のユーザーとトークンは Ansible では消さない。要らなくなったら NetBox の画面で無効にする。

はまったことは[確認と、はまりどころ](verify.md)にあります。
