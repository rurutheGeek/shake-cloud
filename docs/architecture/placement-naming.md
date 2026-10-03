---
title: 配置と命名の再編
updated: 2026-10-03
section: 設計
audience: 管理者・開発者
tags:
  - design
  - iac
---

# 配置と命名の再編

> **更新日** 2026-10-03 ・ **区分** 設計 ・ **読む人** 管理者・開発者

**状態**: **方針は合意済み（2026-10-03。5章）。実機への移行は未着手**で、実機は何も変えていない。

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
| router-01 | ルータ（OpenWrt）・AdGuard Home・**Tailscale の subnet router** | AdGuard Home は今もここ。Tailscale を net-01 から移す。宅外からの復旧経路は、依存が最も少ない場所に置く（core-01 が固まっても入れる）。net-01 は消す |
| **core-01** | Authentik（ログイン）・NetBox（台帳）・入口のCaddy | identity と、services-01 の NetBox・入口をまとめる |
| **cloud-01** | クラウドAPIとその管理DB・Garage（S3の実体） | いまの cloud-01 に storage-s3 を合流する。**クラウド関連は core-01 と分ける**（クラウドAPIは Proxmox でVMを作る・消す強い権限を持つため） |
| **monitor-01** | Prometheus・Grafana・通知・UPS監視（PeaNUT） | クラウドVMから基盤へ移す。クラウドが壊れたときに原因を見る道具なので、作り直しにクラウドAPIを要らなくする。**core-01 には入れない**（見張る相手と一緒に止まると通知が出ない） |
| k8s | database・function・AWX の実体 | 変更なし。使うときだけ起動する |

core-01 の中身は、いま測った使用量で約2.9GB（Authentik 約1.4GB・NetBox 約1.4GB・Caddy）です。互いに依存している（Authentik が止まればポータルに入れず、NetBox が止まればIPを払い出せない）ので、別VMに分けても使えなくなる範囲はほとんど変わりません。**1つの暴走がほかを巻き込まないよう、コンテナごとのメモリ上限を入れることを前提にします**（2026-09-26 の identity のメモリ枯渇と同じ形を防ぐ）。

### クラウドVM（クラウドAPI。`platform/terraform/services/<name>`）

用途は「サービス」と「開発」の2つに分け、タグ `Purpose` に書きます（ポータルで見分けるのにも使う）。所有者は2人だけです。

| VM | いまの名前 | 用途 | 所有者 | 中身 |
| --- | --- | --- | --- | --- |
| media-01 | media-01 | サービス | `rurutheGeek` | 変更なし |
| **apps-01**（新） | — | サービス | `rurutheGeek` | services-01 に同居しているアプリ全部（Homarr・Vaultwarden・LibreSpeed・Home Assistant・eufy 2つ・CUPS・mail-view・ドキュメント・poke-translate） |
| game-01 | game1 | サービス | `shunyazhiyuan97` | ゲームサーバ。作り直すときに改名し、VMID も直す |
| **dev-01** | dev-a | 開発 | `shunyazhiyuan97` | 開発VM。基盤（Terraform）からクラウドVMへ移す |
| **dev-02** | dev-b | 開発 | `rurutheGeek` | 開発VM。同上。**このリポジトリの管理作業をしている機械**なので、移すのは最後にし、作業中のデータ（ホーム約20GB）を先に退避する |
| android-01 | android-01 | 開発 | `rurutheGeek` | Android の検証 |
| win-01 | win11pro | 開発 | `rurutheGeek` | Windows 11 の検証 |

2026-10-03 に管理DBで確かめた時点の所有者は、game1 が1つのアカウント、ほか5台（win11pro・media-01・monitor-01・net-01・android-01）が別の1つのアカウントで、上の割り当てと食い違いはありません。

services-01 は、いまメモリが 3.5GB / 3.9GB でほぼ満杯です（2026-10-03 実測）。アプリを apps-01 へ、NetBox を core-01 へ移すと、services-01 は役目を終えて消せます。検証用の probe-01 は基盤のまま（クラウドの検証に使うので、クラウドの外に置く）。

## 3. 命名規則

| 対象 | 規則 | 例 |
| --- | --- | --- |
| ホスト名 | `<役割>-<2桁の連番>`。役割は**機能の名前**で、製品名にしない。連番は、同じ役割を並べるとき（`k8s-worker-01`・`02`）と、作り直すときに使う（動いている `core-01` を残したまま `core-02` を作り、移し終えてから01を消す。新旧が NetBox・DNS・Proxmox で名前をぶつけない）。1台だけの役割にも付けて揃える | `router-01`・`core-01`・`cloud-01`・`monitor-01`・`media-01`・`apps-01`・`game-01`・`dev-01`・`android-01`・`win-01` |
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

名前を変えるだけのために、動いているVMやデータの置き場所を一斉に動かすことはしません。

| 段階 | 内容 | 状態 |
| --- | --- | --- |
| 1 | apps-01 を作り、services-01 のアプリを移す | **完了（2026-10-03）**。LibreSpeed・ドキュメント・mail-view・Homarr・Vaultwarden・CUPS・ポケモン翻訳・Home Assistant・eufy 2つ。services-01 に残るのは NetBox と入口の Caddy |
| 2 | core-01 を作る（Authentik・NetBox・入口） | **完了（2026-10-03）**。services-01 を 6GiB にして Authentik を移し、`core-01` へ改名した（Proxmox のVM名・ゲストのホスト名・NetBox・`dns.yaml`・インベントリのグループ `core`）。identity のVMは停止前の状態で残してある |
| 3 | storage-s3 を cloud-01 へ合流する | **完了（2026-10-03）**。旧 Garage はバケットもキーも0件だったので、cloud-01 にデータディスク（32GiB）を足して新しく構築し、クラウドAPIの接続先とトークンを切り替えた。storage-s3 の Garage は停止 |
| 4 | Tailscale をルータへ移し、net-01 を消す | 未着手 |
| 5 | monitor-01 を基盤へ移す | 未着手 |
| 6 | 開発VM（dev-a・dev-b）をクラウドVMへ、win11pro・game1 を改名 | **dev-a・dev-b・game1 は使用中のため、指示があるまで触らない**。win11pro は空いた（改名はタグ変更APIが要る） |
| 7 | 空になった identity・storage-s3、基盤側の dev-a・dev-b を消す | 未着手 |

### 段階2: core-01 の作り方

**新しいVMを作って両方を移すのではなく、services-01 を core-01 にします。** services-01 には既に NetBox と入口があり、残る仕事は Authentik を受け入れることだけです。新しいVMへ NetBox まで移すと、NetBox をアドレスで参照している利用者（Terraform・クラウドAPI・インベントリ・AWX の資格情報）と、ルータのファイアウォール（AdGuard の画面を 192.168.10.200 だけに開けている）を全部付け替えることになり、得るものがありません。

1. **services-01 のメモリを 4 → 6GiB にする**（`05-seed`）。Authentik（約1.4GiB）と NetBox（約1.4GiB）を同居させるため。VMの再起動で、NetBox と AdGuard・ルータの画面が数分止まる（DNS そのものはルータ上なので止まらない）。あわせて、コンテナごとのメモリ上限を入れる。
2. **Authentik を services-01 へ移す。** identity 側を止める → PostgreSQL のデータ・メディア・秘密値（`secret_key`・DBパスワード・OIDC クライアント秘密）をコピー → `auth` のDNSを services-01 へ → services-01 で起動。**この間（10分前後）、SSO を使う全サービスで新しいログインができない**（ログイン済みのセッションは各アプリ側で生きている）。
3. 各アプリの配備が OIDC の秘密値を読む先（Ansible の `identity_provider` グループ）を services-01 へ向ける。
4. 確認: Authentik のログイン、Forward Auth のサイト（Navidrome など）、OIDC のサイト（Homarr・Grafana・Vaultwarden・NetBox・クラウドのポータル）。
5. 問題が無ければ identity のVMを止める（数日は消さずに残す）。戻すときは `auth` のDNSを戻して identity を起動する。
6. **services-01 を `core-01` に改名する**（Proxmox のVM名・ゲストのホスト名・NetBox・`dns.yaml` の `host`・インベントリ）。VMは作り直さない。入口の1台化（[HTTPSの入口](../operations/edge.md)）はこのあと行う。

## 5. 決まったこと・決めてほしいこと

| 項目 | 状態 |
| --- | --- |
| 置き場所の基準（2章） | **合意（2026-10-03）** |
| 基盤は router-01・core-01・cloud-01・monitor-01・k8s | **合意（2026-10-03）** |
| クラウド関連（クラウドAPI・Garage）は cloud-01 にまとめ、core-01 と分ける | **合意（2026-10-03）** |
| Tailscale はルータへ移し、net-01 は消す | **合意（2026-10-03）** |
| monitor-01 を基盤へ（core-01 とは別VM） | **合意（2026-10-03）** |
| services-01 のアプリを apps-01 の1台へ | **合意（2026-10-03）** |
| 命名規則（3章）で統一する。ホスト名はすべて `<役割>-<2桁>` | **合意（2026-10-03）** |
| クラウドVMの所有者は game-01 と dev-01 が `shunyazhiyuan97`、ほかは `rurutheGeek` | **合意（2026-10-03）** |
| 開発VM もクラウドVMにする。dev-01（今の dev-a）は `shunyazhiyuan97`、dev-02（今の dev-b）は `rurutheGeek` | **合意（2026-10-03）** |
| dev・android・win は用途「開発」としてまとめる（タグ `Purpose`） | **合意（2026-10-03）** |
