---
title: 置き場所と名前の決まり
updated: 2026-10-23
section: 設計
audience: 管理者・開発者
tags:
  - design
  - iac
---

# 置き場所と名前の決まり

> **更新日** 2026-10-23 ・ **区分** 設計 ・ **読む人** 管理者・開発者

いまどこに何があるかは[配備台帳](../operations/handover.md)と[サービス図](../service-map.md)にあります。2026-10-03 の再編でこの形にしました（[構成の移り変わり](history.md)）。

## 1. 置き場所の決め方

**判断は1つだけです。「クラウドAPIが動くため、またはクラウドAPIが壊れたときに直すために要るか」。** 要るものは基盤（Terraform の `hosts.yaml` で直接作る）、要らないものはクラウドVM（`platform/terraform/services/<name>`）に置きます。

| 置き場所 | 置くもの | 理由 |
| --- | --- | --- |
| K11 の外の機械 | ルータ（Flint 3）・監視（tarakoserver）・公開サイト（shakeserver）・公開の中継（negitoroserver） | K11 が止まっても、宅外から入れて、止まったことが分かり、公開サイトが残る |
| 基盤 core-01 | Authentik・NetBox・HTTPS の入口 | どれもクラウドAPIの前提。互いに依存しているので1台にまとめる |
| 基盤 cloud-01 | クラウドAPI・管理DB・Garage | VM を作る・消す強い権限を持つので core-01 と分ける |
| 基盤 k8s | database・function・AWX の実体 | クラウドAPIの database と function の中身 |
| クラウドVM（サービス） | media-01・apps-01・game-01 | 壊れてもクラウドAPIから作り直せる |
| クラウドVM（開発） | dev-01・dev-02・android-01・win-01 | 同上。タグ `Purpose=dev` で見分ける |

**監視は見張る相手と同じ機械に置きません。** 一緒に止まると通知が出ないためです。

## 2. 名前の付け方

| 対象 | 規則 | 例 |
| --- | --- | --- |
| ホスト名 | `<役割>-<2桁の連番>`。役割は**機能の名前**で、製品名にしない。連番は、同じ役割を並べるとき（`k8s-worker-01`・`02`）と、作り直すときに使う（動いている `core-01` を残したまま `core-02` を作り、移し終えてから01を消す。新旧が NetBox・DNS・Proxmox で名前をぶつけない）。1台だけの役割にも付けて揃える | `core-01`・`cloud-01`・`media-01`・`apps-01`・`game-01`・`dev-01`・`android-01`・`win-01` |
| VMID | 100〜199 基盤、200〜299 Kubernetes、400〜499 開発、900〜999 検証、5000〜 クラウドAPIが払い出す | — |
| Compose のプロジェクト名 | アプリ名だけ。ホスト名を前置きしない（ホストがすでに区切り） | `kavita`・`home-assistant`・`netbox` |
| 配備先 | `/opt/<アプリ名>`、データは `/srv/<アプリ名>` | `/opt/kavita`・`/srv/kavita` |
| リポジトリのスタック | `stacks/<アプリ名>` の1段。どのホストに置くかは Playbook と文書が持つ | `stacks/kavita`・`stacks/music-tools` |
| Playbook | アプリごとに `<アプリ名>.yml`、ホスト全体を流す傘は `<ホスト名>.yml`、Proxmox ホスト向けは `pve-*.yml`。SSOの配布は本体の Playbook に入れて分けない | `kavita.yml`・`media-01.yml`・`pve-backup.yml` |
| インベントリ・変数 | `platform/ansible/inventory/` に分け、Playbook の場所に置かない | `inventory/netbox.yml` |
| NetBoxのタグとグループ | 同じ名前にする（ハイフンは Ansible が使えないので `_` に置き換えるだけ） | タグ `media` → グループ `media` |
| DNS名 | 利用者が覚える短い名前。アプリ名か、機能の名前（`auth`・`vault`）。API・機械向けは `<名前>-api` | `navidrome`・`navidrome-api` |
| SOPS | 使う側（Terraformのモジュール・ロール）ごとに1ファイル | `cloudflare-dns.sops.yaml` |

**名前の決まりは新しく作るものから守ります。** 既存のプロジェクト名・パス（`media-kavita`、`game1-saves` など）は、作り直すときに合わせます。
