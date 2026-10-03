---
title: サービスの置き場所とクラウドVMでの作り方
updated: 2026-10-04
section: 運用手順
audience: 管理者
tags:
  - ops
  - placement
---

# サービスの置き場所とクラウドVMでの作り方

> **更新日** 2026-10-04 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 方針と手順。apps-01 の常用サービス（Home Assistant・eufy-security-ws・Homarr・Vaultwarden・CUPS・LibreSpeed・ドキュメント・mail-view・ポケモン翻訳）、media-01 のメディア系、monitor-01 の監視系（M01）は配備済み（apps-01 へは 2026-10-03 に移設）。

## 方針

**これからのホームラボのサービスは、原則としてクラウドVM（`cloud` プール、VMID 5000–5999）に作ります。** サービスのコードは Git に置き、VM はクラウドAPI（Terraform Provider）で作り、中身は Compose か Kubernetes へ配ります。

例外は**基盤そのもの**です。core-01（Authentik・NetBox・入口の Caddy）、cloud-01（クラウドAPI・管理DB・Garage）、monitor-01（監視。クラウドが壊れたときに原因を見る道具なので基盤側）、router-01、Kubernetes の各ノードは `platform` プールの基盤VMで、Terraform `10-platform`（core-01 は `05-seed` + 台帳）が作ります。**基盤をクラウドAPIで作ると、「APIを載せる前にAPIが要る」循環になります。** 所有境界は[IaCの所有境界](../architecture/iac.md)を正とします。

**配置は停止単位と運用上の利点で決めます。** 既存KubernetesのAWX・DB提供（CloudNativePG）・関数提供（Knative）は維持します。Homarr・Vaultwardenを単に小さいWebアプリだからKubernetesへ移すことはしません。

- core-01 には NetBox・入口の Caddy・Authentik を残し、その他の常用サービスは apps-01（クラウドVM）へ置きます。apps-01 には Home Assistant Container・eufy-security-ws（HAとは別Compose）・eufy-leo-rtc・Homarr・Vaultwarden・CUPS・メールビューア・ドキュメントサイト・LibreSpeed・ポケモン翻訳・ポケモン系のPostgreSQL（[pkdb](pkdb.md)）・Discord Bot（[UBSLEEPY](ubsleepy.md)）を別Composeで置きます。**2026-10-03 に services-01 から移設済みで、配備先は `/opt/<アプリ名>`、データは `/srv/<アプリ名>` です**（VPNは未配備）。
- game1にはゲームとAI一式（ポケモン・汎用RAG・Discord Bot）をまとめます。ポケモン系のPostgreSQLだけは常時つなぐため apps-01 に置きます。既存VMはcloud APIの所有を維持し、停止中は全機能が停止します。
- media-01は新規cloud VMにNextcloud・Calendar・Tasks・Kavita・Navidrome・FreshRSS・MeTube・タグAPI・LocalSend・Nextcloud印刷を載せます。機能群の停止・再開をVM単位で行います。**2026-09-12に配備済みで、既存環境からのデータ移行が未完です。**FreshRSSは全員で1つの購読リストを共有する共通RSSタイムラインです。RomMはゲームVM（game1）へ載せ、メディアの機能群とは分けます。
- monitor-01は基盤VM（VMID 120、`192.168.10.210`）で、Prometheus・Alertmanager・Grafana・各exporter（監視一式、M01）を載せます。**2026-10-03 にクラウドVMから基盤VMへ移し、Grafanaは `https://grafana.apextox.dpdns.org`（core-01 の Authentik OIDC）。**残りはHomarrの Proxmox/PeaNUT 連携、低電池シャットダウン、ダッシュボード拡充です。
- public-edgeは公開要件が揃ってから新規cloud VMとして追加します。AI専用VMは追加しません。

スペック案・独立した作業ID・依存関係は[並列開発計画](../development/index.md)を参照してください。増設は現有ホストへのVM追加を指し、ハードウェア増設の提案は含めません。

## リポジトリのどこに置くか

| 置き場所 | 何を置くか | 例 |
| --- | --- | --- |
| `platform/terraform/services/<name>/` | サービスのVM・ディスク・セキュリティグループの宣言（shakecloud Provider）。**サービスごとに1ディレクトリ・1 state** | 新規 |
| `stacks/<name>/` | VM の中で動かすソフト（Compose、`manage.py`、`.env.example`） | `stacks/identity/` |
| `platform/ansible/roles/<name>/` と `platform/ansible/<name>.yml` | VM の中の構成を冪等に適用する場合（任意） | `roles/garage/` |
| `platform/flux/apps/<name>.yaml` | Kubernetes に載せる場合 | `awx.yaml` |
| `platform/terraform/dns.yaml` | LAN の中で名前を付ける場合。`20-dns` が Cloudflare へ書く | `awx`、`cloud` |
| `docs/development/<ID>-<name>.md` | 独立して開発・確認できる作業ごとの計画。番号は実施順ではない | [W01 Homarr](../development/W01-homarr.md) |
| `docs/operations/<name>.md` | 管理者向けの構築・運用 | [identity.md](identity.md) |
| `docs/services/<name>.md` | 利用者向けの使い方 | [usage.md](../services/usage.md) |

### 開発コードはどこに書くか

| 作るもの | 置き場所 | 例 |
| --- | --- | --- |
| VM 1台に載るサービスのコード | **`stacks/<name>/`** | `stacks/identity/`（Compose + `manage.py` + `.env.example` + テスト） |
| 複数コンポーネントの大きなソフト | **トップレベルの専用ディレクトリ** | `cloud/`（API・CLI・Provider・client を1つに） |
| Kubernetes に載せるアプリ | ソースは `stacks/<name>/` か専用ディレクトリ。配備は `platform/flux/apps/<name>.yaml` | [Flux にアプリを足す](flux-apps.md) |
| 使い捨て・補助スクリプト | **`tools/`** | `tools/tf`、`tools/k8s` |
| 設定値の宣言 | `platform/terraform/*.yaml` | `hosts.yaml`、`network.yaml` |

迷ったら「**VM 1台に載る1サービス → `stacks/<name>/`**」「**複数コンポーネント → トップレベル**」で判断します。`stacks/identity/` と同じ形（`init` / `lock` / `up` / `status`）にそろえると、配備と再実行が同じ手順になります。

`hosts.yaml` と `10-platform` は**基盤VM専用**です。サービス用のVMをここへ足さないでください。VMID とプールの境界が崩れ、クラウドAPIの到達範囲（`/pool/cloud` のみ）から外れて管理できなくなります。

## クラウドVMにサービスを作る手順

### 0. 前提

- cloud-01 が動いている（`https://cloud.apextox.dpdns.org/healthz` が 200）。
- アクセスキーをポータルで発行済み。ポータル → アクセスキー（**発行はポータルのログインからだけ**。CLI は `shakecloud access-key ls` / `rm` のみで作成できません）。
- Provider の dev override を設定済み（[shakecloud Terraform Provider](terraform-provider.md)）。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_<キーID>.<秘密値>'
```

### 1. 置き場所を作る

```bash
mkdir -p platform/terraform/services/<name>
```

ひな形の説明は `platform/terraform/services/README.md` にあります。

### 2. VM とリソースを書く

`platform/terraform/services/<name>/main.tf` の例です。SSH とサービスポートを LAN へ開け、SSH鍵を入れ、データディスクを付けた Debian VM を1台作ります。

```hcl
terraform {
  required_providers {
    shakecloud = { source = "ruruthegeek/shakecloud" }
  }
}

provider "shakecloud" {}

resource "shakecloud_key_pair" "service" {
  key_name   = "<name>"
  public_key = file("~/.ssh/id_ed25519.pub")
}

resource "shakecloud_security_group" "service" {
  group_name  = "<name>"
  description = "<name> service"
}

resource "shakecloud_security_group_rule" "ssh" {
  group_id  = shakecloud_security_group.service.id
  direction = "ingress"
  protocol  = "tcp"
  from_port = 22
  to_port   = 22
  cidr      = "192.168.10.0/24"
}

resource "shakecloud_security_group_rule" "web" {
  group_id  = shakecloud_security_group.service.id
  direction = "ingress"
  protocol  = "tcp"
  from_port = 8080
  to_port   = 8080
  cidr      = "192.168.10.0/24"
}

resource "shakecloud_instance" "service" {
  image_id           = "img-debian13"
  instance_type      = "small"          # 近道。vcpus/memory_mib/root_disk_gib を直接書いてもよい
  root_disk_gib      = 20
  key_name           = shakecloud_key_pair.service.key_name
  security_group_ids = [shakecloud_security_group.service.id]
  user_data          = file("${path.module}/cloud-init.yaml")
  tags               = { Name = "<name>" }   # これがゲストのホスト名になる
}

resource "shakecloud_volume" "data" {
  size_gib = 20
  tags     = { Name = "<name>-data" }
}

resource "shakecloud_volume_attachment" "data" {
  volume_id   = shakecloud_volume.data.id
  instance_id = shakecloud_instance.service.id
}

output "address" {
  value = shakecloud_instance.service.private_ip_address
}
```

必要ならバケット・DB・関数も同じモジュールに足せます。例は[shakecloud Terraform Provider](terraform-provider.md)にあります。

```hcl
resource "shakecloud_bucket" "assets" { bucket_name = "<name>-assets" }

resource "shakecloud_database" "app" {
  name        = "<name>"
  storage_gib = 5
}

resource "shakecloud_function" "hook" {
  name  = "<name>-hook"
  image = "ghcr.io/example/<name>-hook:1.0.0"
}
```

### 3. 適用する

```bash
terraform -chdir=platform/terraform/services/<name> init
terraform -chdir=platform/terraform/services/<name> apply
```

- **作成と削除はワーカーが終わるまで待ちます。** `apply` が返った時点で VM は `running` です。
- **state はサービスごとに分けます。** 他のモジュールと共有しません。
- 消すときは `terraform destroy`。VM と IP は API の管理下で片付きます。
- state の置き場は Cloudflare R2 の `shake-cloud/services/<name>/terraform.tfstate` です（`tools/tf services/<name>` 経由。I05 で実機確認済み）。**秘密値は state に平文で入り得ます**（[Terraformの実行](terraform.md)）。

### 4. ソフトを配備する

`user_data`（cloud-init）で、ユーザー・パッケージ・Docker など最小限を最初に整えます。ソフト本体は `stacks/<name>/` に置き、`manage.py` を `stacks/identity/manage.py` と同じ「init / lock / up / status」の形にします。

**配備は Playbook に書きます**（手で `scp` して `ssh` で起動しない）。Compose スタックを1つ配備する流れ（ディレクトリ作成 → 定義ファイルの配置 → `.env`（0600）→ `manage.py init` → `manage.py up`）は共通ロール `compose_stack` が持っているので、Playbook には「どこへ・何を・どんな `.env` で」だけを書きます。

```yaml
- name: Deploy <name>
  hosts: <グループ>
  become: true
  vars:
    source_dir: '{{ playbook_dir }}/../../stacks'
  tasks:
    - name: Deploy the <name> stack
      ansible.builtin.include_role:
        name: compose_stack
      vars:
        compose_stack_source_dir: '{{ source_dir }}/<name>'
        compose_stack_project_dir: /opt/<name>
        compose_stack_files: [compose.yaml, compose.lock.yaml, manage.py, .env.example]
        compose_stack_env: |
          STORAGE_ROOT=/srv/<name>
```

- `compose.lock.yaml`（イメージのdigest）は**必ずリポジトリに置いて配ります**。配備先で `pull` して決めさせません（`tests/test_image_locks.py`）。
- `manage.py` は、何かを作った・変えたときだけ `CHANGED:` を、そうでなければ `OK:` を出します。ロールはこれと `docker compose` の出力を見て、**変わったときだけ「changed」と報告します**。再実行して `changed=0` なら、実機はリポジトリと揃っています。
- 追加の手順（初期ユーザーの作成、systemd タイマーなど）は、ロールの呼び出しの後ろへタスクとして足します（例: `platform/ansible/media-kavita.yml`）。
- 配り直す前に `--check --diff` を付けて流すと、実機を変えずに差分だけを確かめられます。秘密値を読むタスクには `check_mode: false` を付けて、確認モードでも後続が値を使えるようにします。
- 秘密は SOPS から写すか、`manage.py init` に配備先で生成させます。**Git へ入れません。** `.env` に秘密値を書く場合は `compose_stack_env_no_log: true` を付けます。

### 5. 名前を付ける（任意）

`*.apextox.dpdns.org` の名前は `platform/terraform/dns.yaml` に書き、`20-dns` を適用します。**公開の証明書（Let's Encrypt）と Cloudflare の DNS 編集トークンを持つのは入口の core-01 だけ**で、その他のホストの Caddy は内部CAの証明書で core-01 からの中継を受けます（[HTTPSの入口](edge.md)）。クラウドVMへ名前を付ける場合も同じで、`hosts.yaml` に居ないため IP を `address` に直接書き、その VM にも `tls_proxy` ロールを配備します（media-01・apps-01 が実例。トークンは置かない）。**現時点でクラウドVMへの DNS 自動登録はありません**（IP は宣言へ直接書く）。

### 6. ドキュメントを足す

`docs/operations/<name>.md`（管理者）と `docs/services/<name>.md`（利用者）を書き、`mkdocs.yml` のナビへ入れます。URL は[接続先一覧](../reference/urls.md)へ追記します。

## 決まりごと

- **state はサービスごとに分ける。** 共有すると、片方の削除がもう片方の現状把握を壊します。
- **秘密値を Provider で作らない。** S3キーとDB資格情報は作成時に一度だけ返る値で、state に置くと漏れます。ポータルか CLI で発行します（`shakecloud s3-key create`・`shakecloud database credentials`）。
- **サイズは自由入力。** `instance_type` は値を埋める近道です。`vcpus`・`memory_mib`・`memory_min_mib`・`ballooning`・`root_disk_gib` を直接書けます。
- **`tags.Name` がゲストのホスト名。** 変えると VM は作り直されます。
- **削除は `terraform destroy`。** 基盤VM（`hosts.yaml`）とサービスVM（`cloud` プール）を混ぜません。

## まだ無いもの

- クラウドVMへの DNS **自動**登録（`dns.yaml` へ手で宣言する）。
- 既存環境からのメディアデータ移行（[並列開発計画](../development/index.md)のW03〜W06）。

<a id="inventory"></a>
## Ansibleのインベントリ（NetBoxへ統一）

**配備対象は NetBox の動的インベントリ（`platform/ansible/inventory.netbox.yml`）1本から見つけます。** グループは NetBox のタグで決まり、タグの正本は `platform/terraform/tags.yaml` です。

| 対象 | NetBoxへ載せるもの | グループの決まり方 |
| --- | --- | --- |
| 基盤VM（cloud-01・monitor-01・k8s・dev など） | `10-platform`（`hosts.yaml`） | `hosts.yaml` の `tags` |
| core-01 | `10-platform`（VM本体は `05-seed`。台帳の器だけ足す） | タグ `core` と `identity`（`identity_provider` グループ） |
| クラウドAPIが作ったVM（media-01・apps-01 など） | **クラウドAPI自身**（VMの状態が変わったらすぐ同期。取りこぼし対策に15分ごとにも見比べる） | `cloud.yaml` の `ledger.tags_by_name`（VM名→タグ） |

クラウドVMの扱いは次のとおりです。

- **ホスト名はインスタンスID（`i-...`）**、表示名（`tags.Name`）は変数 `cloud_name` に入ります。`--limit` はグループ名（`media` など）で絞ります。
- **稼働中のVMだけが対象になります。** 止めると NetBox 上で `offline` になり、インベントリから外れます。削除すると台帳からも消えます。
- **グループはVM自身のタグでは決めません。** グループは「どの秘密値をそのホストへ配るか」を決めるので、誰でも付けられる名前には任せません。`cloud.yaml` の `ledger.group_accounts` に書いたアカウントの、`ledger.tags_by_name` に書いた名前のVMだけにタグが付きます。他の利用者のVMは台帳に載るだけで、どのグループにも入りません（共通の `cloud_instances` を除く）。
- **VMを作り直しても、名前が同じなら宣言の修正は要りません**（2026-10-03 まで使っていた `cloud-inventory.yml` はインスタンスIDで書いていたので、作り直すたびに直す必要がありました）。
- 新しいサービスVMを足すときは、`tags.yaml` にタグ、`inventory.netbox.yml` にグループ、`cloud.yaml` の `ledger.tags_by_name` に名前を足し、`10-platform` と `cloud.yml` を流します。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  '.venv/bin/ansible-inventory -i platform/ansible/inventory.netbox.yml --graph'
```

### 切替の記録と、手書きインベントリの扱い

**2026-10-03 に実機を切り替えました**（NetBox のタグと core-01 の台帳を `-target` で適用。全体の apply は、使用中の開発VMに差分が出るため未実施）。手順は次のとおりです。

1. `tools/tf 10-platform apply` — NetBox にタグと、core-01 の台帳（VM・インターフェース・primary IP）を作る
2. `cloud.yml` を流してクラウドAPIを更新する（`site.json` に `ledger` が入り、API が台帳への登録を始める）
3. 上の `ansible-inventory --graph` を流し、`media`・`monitoring`・`apps`・`core`・`identity_provider`・`cloud_instances` に期待したホストが居ることを確かめる
4. 以後の配備は `-i platform/ansible/inventory.netbox.yml` で流す

旧来の手書きインベントリは、この切替の完了を受けて **2026-10-03 に削除しました**（`inventory.cloud.py`・`cloud-inventory.yml`・`monitor.ini.example`）。現在残るのは次の2つです。

| インベントリ | 役割 |
| --- | --- |
| `seed.ini`（`seed.ini.example` から作る） | NetBox 自身を作る初回（`netbox.yml`）と、NetBox が落ちて動的インベントリが使えないときの復旧だけ。**NetBox の動的インベントリと併用しない** |
| `pve.ini` | Proxmox ホスト（`pve-*.yml`）。NetBox へ載せるには機器の primary IP とタグの同期（`tools/netbox-dhcp-sync.py`）が要り、未着手 |

<a id="media-units"></a>
### media-01 を単体で配り直す

`media.yml` は下の順で全部を流す傘です。**1つだけ直したいときは、その行のPlaybookを単体で流せます。**

| 順 | Playbook | 対象 |
| --- | --- | --- |
| 1 | `media-base.yml` | 共有ライブラリのNFSマウント・土台（[共有バルクストレージ](bulk-storage.md)） |
| 2 | `media-nextcloud.yml` | Nextcloud・Calendar・Tasks・Notes・自作アプリ（[Nextcloudと追加アプリ](nextcloud.md)） |
| 3 | `media-kavita.yml` | Kavita |
| 4 | `media-localsend.yml` | LocalSend受信機 |
| 5 | `media-navidrome.yml` | Navidrome |
| 6 | `media-freshrss.yml` | FreshRSS |
| 7 | `music-tools.yml` | MeTube・変換・タグAPI・KHInsider |
| 8 | `media-verify.yml` | 各サービスの応答確認 |
| 9 | `media-tls.yml` | Caddy（HTTPS入口） |

**OIDCは別Playbookです。** Kavita・FreshRSS・Nextcloud は本体のPlaybookだけでは**認証が無効のまま起動します**。Authentik（core-01）が作ったクライアント秘密値を配るのが `media-kavita-sso.yml`・`media-freshrss-sso.yml`・`media-sso.yml`（Nextcloud）で、本体を配り直したら**対応するSSO側も流し直してください**。忘れると「ログイン画面が出ないまま中身が見える」状態になります。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/media-navidrome.yml'
```

`media-sso.yml` は core-01（Authentik）から秘密値を slurp するため、**core-01 も同じインベントリに居る必要があります**。NetBox のインベントリなら `media` と `identity_provider` の両方が居ます。ホスト名はインスタンスID（`i-...`）なので、対象は `--limit media` のようにグループ名で絞ります。
