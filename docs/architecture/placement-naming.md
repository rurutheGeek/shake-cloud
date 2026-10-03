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

**判断は1つだけです。「クラウドAPIが動くため、またはクラウドAPIが壊れたときに直すために要るか」。**

| 層 | 基準 | 作り方 | 何が入るか |
| --- | --- | --- | --- |
| **基盤** | クラウドAPIがこれに依存している、または復旧経路 | Terraform（`hosts.yaml`）。クラウドAPIを通さない | ルータ、identity（ログイン）、cloud-01（API自身）、storage-s3（S3の実体）、NetBox（IPの台帳）、入口のCaddy、Kubernetes（database・functionの実体） |
| **サービス** | クラウドAPIに依存していない | **クラウドAPI**（`platform/terraform/services/<name>`）。APIで作り直し・サイズ変更・停止ができる | 利用者向けのアプリすべて |
| **開発・検証** | 使うときだけ動かす | どちらでもよい（下の判断待ち） | dev-a・dev-b・probe-01 |

これに当てはめると、**services-01 に同居しているアプリ10個はサービス層**で、クラウドVMへ移すのが筋です。services-01 には NetBox と入口だけが残ります。

| 移す先（案） | 中身 |
| --- | --- |
| apps-01（新規・クラウドVM） | Homarr・Vaultwarden・LibreSpeed・ドキュメント・mail-view・poke-translate |
| home-01（新規・クラウドVM） | Home Assistant・eufy-security-ws・eufy-leo-rtc・CUPS（家電・カメラ・印刷。LANの機器と直接やりとりするものをまとめる） |

ゲームの game1 はすでにクラウドAPIの管理下で、名前と VMID だけが例外です（作り直すときに直す）。

## 3. 命名規則

| 対象 | 規則 | 例 |
| --- | --- | --- |
| ホスト名 | `<役割>-<2桁の連番>`。役割は**機能の名前**で、製品名にしない | `router-01`・`idp-01`・`cloud-01`・`s3-01`・`netbox-01`・`media-01`・`apps-01`・`home-01`・`monitor-01`・`vpn-01`・`game-01`・`dev-01` |
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

名前を変えるだけのために、動いているVMやデータの置き場所を一斉に動かすことはしません。データの移動を伴う作業は、止まる時間とデータを失う危険があるからです。

1. **この規則を決める**（ここで承認をもらう）。決まったら決定ログへ移し、テストで新しく作るものを検査する（例: 新しいホスト名が `<役割>-<2桁>` か）。
2. **新しく作るものは最初から規則どおりにする。** apps-01・home-01 は新しい命名（`/opt/<アプリ名>`、Compose名=アプリ名、`stacks/<アプリ名>`）で作り、サービスを1つずつ移す。移したサービスから順に、古い名前が消える。
3. **費用の小さい改名だけ先にやる。** リポジトリの中だけで済むもの（Playbook の置き場所の整理、インベントリと変数の分離、`stacks/media/*` の1段化、NetBox のタグ名とグループ名の統一）。配備先のパスや Compose 名は変えないよう、移すまでは古い値を変数で残す。
4. **基盤VMの改名は作り直すときに行う**（identity → idp-01、storage-s3 → s3-01、services-01 → netbox-01）。改名には Terraform の state・NetBox・DNS・証明書・インベントリの付け替えが要り、名前だけのために行う価値は低い。

## 5. 決めてほしいこと

| 項目 | 選択肢 |
| --- | --- |
| 置き場所の基準（2章） | このとおり / 変える |
| services-01 のアプリの移し先 | apps-01 と home-01 の2台に分ける / 1台にまとめる / 移さない |
| 開発VM（dev-a・dev-b） | 基盤のまま / クラウドVMへ |
| 命名規則（3章） | このとおり / 部分的に変える |
| 費用の小さい改名（4章の3）を先にやるか | やる / 移行と一緒にやる |
