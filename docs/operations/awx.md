---
title: AWX の使い方
updated: 2026-10-23
section: 運用手順
audience: 管理者
tags:
  - ops
  - awx
---

# AWX の使い方

> **更新日** 2026-10-23 ・ **区分** 運用手順 ・ **読む人** 管理者

## 入口とログイン

| 項目 | 値 |
| --- | --- |
| URL | <https://awx.apextox.dpdns.org/> |
| ログイン | ログイン画面の下の **Sign in with OIDC**（Authentik）。`admins` グループだけが入れ、入ると Default 組織の管理者になる |
| 予備のログイン | `admin`。パスワードは `sops -d --extract '["stringData"]["password"]' platform/flux/apps/awx-instance/admin-password.sops.yaml`（Authentik が止まっているとき） |
| 稼働場所 | k8s-cp-01（namespace `awx`、[Kubernetes](kubernetes.md#アプリ-awx)） |

## Playbook を流す

1. 左の **Templates** を開く。Playbook 1本が1行で、名前は Playbook の先頭コメントの1文目、括弧の中がファイル名。上の **Label** で種類（メディア・アプリ・監視・Proxmox など）に絞れる。
2. 行の右のロケット（Launch）を押す。
3. **Job type** を選ぶ。`Check` は何が変わるかを表示するだけで、実機は変えない。`Run` が本番。基盤を変えるもの（Proxmox・Kubernetes・認証・入口・クラウド・`guests`・`site`）は既定が `Check`。
4. **Limit** は空のままでよい。1台だけにしたいときはグループ名（`media`・`apps` など）を入れる。クラウドVMのホスト名はインスタンスID（`i-…`）。
5. 出力がその場で流れる。終わったら **Jobs** に、いつ・誰が・何を流して成功したかが残る。

一覧と各 Playbook の説明は [Playbook の一覧](playbooks.md) にもある（AWX が止まっていても読める）。

## 仕組み

| もの | 中身 |
| --- | --- |
| プロジェクト `shake-cloud` | GitHub の `main`。ジョブのたびに最新を取る |
| インベントリ `全ホスト` | `NetBox`（`platform/ansible/inventory.netbox.yml`）と `Proxmox 本体`（`dns.yaml` の `pve`）を合わせたもの |
| 実行環境 `shakecloud-ee` | `platform/awx/execution-environment.yml`。sops・pynetbox・mkdocs などを入れたイメージ |
| 資格情報 `ホストへの SSH` | 管理PCの `~/.ssh/id_ed25519_pve` と同じ鍵 |
| 資格情報 `既知ホスト` | 管理PCの `known_hosts` から、インベントリのアドレスの分だけ写したもの。ホスト鍵は確かめる |
| 資格情報 `秘密値の復号（sops）` | AWX 専用の age 鍵（`platform/sops/awx.sops.yaml`）。`platform/sops/*.sops.yaml` の受信者に入っている。Flux の秘密値は読めない |
| 資格情報 `NetBox（読み取り）` | `platform/sops/netbox-inventory.sops.yaml` |

登録は `platform/awx/configure.yml` が行う（[platform/awx/README.md](https://github.com/rurutheGeek/shake-cloud/blob/main/platform/awx/README.md)）。AWX の画面でテンプレートや資格情報を直接直さない。Playbook を足したら `python3 tools/awx-catalog.py` と `configure.yml` を流す。

**AWX に載らない Playbook**（NetBox の台帳に無いホスト向け）は [Playbook の一覧](playbooks.md) で「手元専用」になっている。管理PCから従来どおり流す。

**一度も入ったことのないホスト**（止めてある予備の k8s-worker-02 など）は既知ホストに載らず、ジョブがホスト鍵の確認で止まる。管理PCから一度 SSH で入り、`configure.yml` を流し直す。

## 運用

- **アップグレード**は `platform/flux/apps/awx-instance/awx.yaml` の版を変えて `main` へ（Flux が反映）。
- **バックアップ**は未設定。DB を失っても `configure.yml` で登録は戻るが、ジョブの履歴は消える。
- 2026-10-22 の1台構成への移行で DB を作り直した。Operator が古い移行ジョブ（`awx-migration-<版>`）を見て移行済みと思い込むので、DB を作り直したらそのジョブを消す（[Kubernetes](kubernetes.md#アプリ-awx)）。

## 関連

- [Playbook の一覧](playbooks.md)
- [Kubernetes クラスタ](kubernetes.md#アプリ-awx)
- [接続先一覧](../reference/urls.md)
