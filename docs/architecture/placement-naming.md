---
title: 配置と命名の再編（提案）
updated: 2026-10-03
section: 設計
audience: 管理者・開発者
tags:
  - design
  - iac
---

# 配置と命名の再編（提案）

> **更新日** 2026-10-03 ・ **区分** 設計 ・ **読む人** 管理者・開発者

**状態**: **提案。まだ決まっていない。** 承認されたら[決定ログ](decisions.md)へ移し、この文書は移行の記録にする。実機は何も変えていない。

VMの置き場所（Terraformで直接作るか、クラウドAPIで作るか）と、名前の付け方がサービスごとにばらばらになっています。ここでは「どこに置くか」の基準と命名規則を1つに決め、**今後VMを作り直すとき・サービスを移すときに、新しい規則へ寄せていく**ことを提案します。動いているものを名前のためだけに一斉に作り直すことはしません。

## 1. いまの状態

### 置き場所

| VM | 作り方 | 中身 |
| --- | --- | --- |
| router-01 | Terraform（router） | 家庭内ルータ（OpenWrt） |
| identity・cloud-01・storage-s3 | Terraform（`hosts.yaml`） | Authentik、クラウドAPI、Garage |
| k8s-cp-01・k8s-worker-01/02 | Terraform（`hosts.yaml`） | Kubernetes（使うときだけ起動） |
| dev-a・dev-b・probe-01 | Terraform（`hosts.yaml`） | 開発VM、クラウドの検証用 |
| services-01 | Terraform（`05-seed`） | **NetBox・入口のCaddy と、アプリ10個の同居**（Homarr・Vaultwarden・LibreSpeed・Home Assistant・eufy 2つ・CUPS・mail-view・ドキュメント・poke-translate） |
| media-01・monitor-01・net-01・android-01・win11pro | クラウドAPI | メディア、監視、Tailscale、Android、Windows検証 |
| game1 | 手作り（クラウドAPIが引き取り済み） | ゲームサーバ |

services-01 は、NetBox を最初に立てるための「過渡的なホスト」として作られたまま、アプリの置き場になっています。

### 命名のばらつき

| 対象 | 実例 | ばらつき |
| --- | --- | --- |
| ホスト名 | `router-01`・`media-01` / `identity`・`storage-s3` / `dev-a` / `game1` / `win11pro` | 連番の有無と形、役割名と製品名の混在（`storage-s3`）、中身と名前のずれ（`net-01` は Tailscale） |
| Compose のプロジェクト名 | `media-kavita`・`services-home-assistant`・`game1-romm` / `homarr`・`identity`・`monitoring` / **`media-netbox`**（実体は services-01） | ホスト名の前置きの有無、実体と違う前置き |
| 配備先ディレクトリ | `/opt/homarr-stack` / `/opt/services/vaultwarden` / `/opt/media-stack/media/kavita` / `/opt/docs-site` | 3通り以上 |
| データの置き場 | `/srv/homarr-stack/storage` / `/srv/services/vaultwarden` / `/srv/media-stack/storage` / `/srv/monitoring` | 同上 |
| リポジトリのスタック | `stacks/media/kavita` / `stacks/music-tools`（同じ media-01） / `stacks/pokemon-ai/ollama` | 入れ子の基準が無い |
| Playbook | `media-kavita.yml` / `homarr.yml` / `media-kavita-sso.yml` / `cloud.yml` | 前置きと分割の基準が無い。`inventory.netbox.yml`・`cloud-inventory.yml`・`k8s-vars.yml` など Playbook でないものが同じ場所にある |
| インベントリのグループ | タグ `media-stack` → `media`、`identity` → `identity_provider`、`cloud-control` → `cloud_control` | タグとグループの名前の対応がまちまち |
| SOPS のファイル | `eufy-security`・`music-tags`（サービス別） / `services`（Terraformのクラウド鍵） / `cloudflare` と `cloudflare-dns` | 単位が混在 |
| VMID | platform帯（100〜399）に `game1`（100、実はcloudプール）と `router-01`（101） | 帯と中身が一致しない |

## 2. 置き場所の基準

**判断は1つだけです。「クラウドAPIが動くため、またはクラウドAPIが壊れたときに直すために要るか」。** 要るものは基盤（Terraformで直接作る）、要らないものはサービス（クラウドAPIで作る）に置きます。

### 基盤（クラウドAPIを通さない。`hosts.yaml` と Terraform）

| VM | 中身 | いまのVMとの対応 |
| --- | --- | --- |
| router-01 | ルータ（OpenWrt） | 変更なし。ネットワークそのもので、最初に起動する |
| **core-01** | Authentik（ログイン）・NetBox（台帳）・入口のCaddy | identity と、services-01 の NetBox・入口をまとめる |
| **cloud-01** | クラウドAPIとその管理DB・Garage（S3の実体） | いまの cloud-01 に storage-s3 を合流する。**クラウド関連は core-01 と分ける**（クラウドAPIは Proxmox でVMを作る・消す強い権限を持つため） |
| **net-01** | Tailscale の subnet router（宅外からの復旧経路） | クラウドVMから基盤へ移す。クラウドが壊れたときに直すための経路なので、作り直しにクラウドAPIを要らなくする |
| k8s | database・function・AWX の実体 | 変更なし。使うときだけ起動する |

core-01 の中身は、いま測った使用量で約2.9GB（Authentik 約1.4GB・NetBox 約1.4GB・Caddy）です。互いに依存している（Authentik が止まればポータルに入れず、NetBox が止まればIPを払い出せない）ので、別VMに分けても使えなくなる範囲はほとんど変わりません。**1つの暴走がほかを巻き込まないよう、コンテナごとのメモリ上限を入れることを前提にします**（2026-09-26 の identity のメモリ枯渇と同じ形を防ぐ）。

### サービス（クラウドAPI。`platform/terraform/services/<name>`）

| VM | 中身 |
| --- | --- |
| media-01 | 変更なし |
| **apps-01**（新） | services-01 に同居しているアプリ全部（Homarr・Vaultwarden・LibreSpeed・Home Assistant・eufy 2つ・CUPS・mail-view・ドキュメント・poke-translate） |
| monitor-01・game1・android-01 | 変更なし（game1 は名前と VMID だけが例外。作り直すときに直す） |

services-01 は、いまメモリが 3.5GB / 3.9GB でほぼ満杯です（2026-10-03 実測）。アプリを apps-01 へ、NetBox を core-01 へ移すと、services-01 は役目を終えて消せます。

### 開発・検証

dev-a・dev-b・probe-01 は使うときだけ動かすVMで、置き場所は判断待ち（基盤のままか、クラウドVMにするか）。

## 3. 命名規則

| 対象 | 規則 | 例 |
| --- | --- | --- |
| ホスト名 | `<役割>-<2桁の連番>`。役割は**機能の名前**で、製品名にしない。連番は、同じ役割を並べるとき（`k8s-worker-01`・`02`）と、作り直すときに使う（動いている `core-01` を残したまま `core-02` を作り、移し終えてから01を消す。新旧が NetBox・DNS・Proxmox で名前をぶつけない）。1台だけの役割にも付けて揃える | `router-01`・`core-01`・`cloud-01`・`net-01`・`media-01`・`apps-01`・`monitor-01`・`game-01`・`dev-01` |
| VMID | 100〜199 基盤、200〜299 Kubernetes、400〜499 開発、900〜999 検証、5000〜 クラウドAPIが払い出す | — |
| Compose のプロジェクト名 | アプリ名だけ。ホスト名を前置きしない（ホストがすでに区切り） | `kavita`・`home-assistant`・`netbox` |
| 配備先 | `/opt/<アプリ名>`、データは `/srv/<アプリ名>` | `/opt/kavita`・`/srv/kavita` |
| リポジトリのスタック | `stacks/<アプリ名>` の1段。どのホストに置くかは Playbook と文書が持つ | `stacks/kavita`・`stacks/music-tools` |
| Playbook | アプリごとに `<アプリ名>.yml`、ホスト全体を流す傘は `<ホスト名>.yml`、Proxmox ホスト向けは `pve-*.yml`。SSOの配布は本体の Playbook に入れて分けない | `kavita.yml`・`media-01.yml`・`pve-backup.yml` |
| インベントリ・変数 | `platform/ansible/inventory/` に分け、Playbook の場所に置かない | `inventory/netbox.yml` |
| NetBoxのタグとグループ | 同じ名前にする（ハイフンは Ansible が使えないので `_` に置き換えるだけ） | タグ `media` → グループ `media` |
| DNS名 | 利用者が覚える短い名前。アプリ名か、機能の名前（`auth`・`vault`）。API・機械向けは `<名前>-api` | `navidrome`・`navidrome-api` |
| SOPS | 使う側（Terraformのモジュール・ロール）ごとに1ファイル | `cloudflare-dns.sops.yaml` |

## 4. 進め方

名前を変えるだけのために、動いているVMやデータの置き場所を一斉に動かすことはしません。新しいVMを横に作って1つずつ移し、移し終えた古いVMを消します。

1. **apps-01 を作り、services-01 のアプリを1つずつ移す。** services-01 のメモリが逼迫しているので最初にやる。新しい命名（`/opt/<アプリ名>`、Compose名=アプリ名）で作る。CUPS を `192.168.10.200:631` で登録している端末は設定し直しが要る。
2. **core-01 を作り、NetBox・Authentik・入口を移す。** Authentik は全サイトのSSOに関わるので、DBの移行を確かめてから切り替える。入口の1台化（[HTTPSの入口](../operations/edge.md)）は core-01 の上で行う。
3. **storage-s3 を cloud-01 へ合流する。** Garage のデータディスクを付け替える。
4. **net-01 を基盤へ移す。** `hosts.yaml` に宣言して作り直し、Tailscale に登録し直す。
5. 空になった identity・services-01・storage-s3 を消す。

リポジトリの中だけで済む整理（Playbook の置き場所、インベントリと変数の分離、`stacks/media/*` の1段化、NetBox のタグ名とグループ名の統一）は、移行と並行して先に進められる。

## 5. 決まったこと・決めてほしいこと

| 項目 | 状態 |
| --- | --- |
| 置き場所の基準（2章） | **合意（2026-10-03）** |
| core-01 を作る | **合意（2026-10-03）** |
| クラウド関連（クラウドAPI・Garage）は core-01 と分ける | **合意（2026-10-03）**。Garage を cloud-01 に入れるか、storage-s3 のまま別VMにするかは未決 |
| net-01 を基盤へ | **合意（2026-10-03）** |
| services-01 のアプリを apps-01 の1台へ | 未決 |
| 開発VM（dev-a・dev-b） | 未決 |
| 命名規則（3章）、連番を付けて揃えるか | 未決 |
