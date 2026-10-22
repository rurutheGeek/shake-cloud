---
title: I08 クラウドのコンテナサービス
updated: 2026-10-22
section: 開発計画
audience: 開発者
tags:
  - plan
  - cloud
  - kubernetes
---

# I08 クラウドのコンテナサービス

> **更新日** 2026-10-22 ・ **区分** 開発計画 ・ **読む人** 開発者

**区分**: 自作クラウドの機能追加（設計） ・ **状態**: 設計のみ。実装・依存の追加・構成の変更は未着手で、下の「提案」は了承待ち。

## 目的・現状

常時動くコンテナ（AWS ECS のサービス・Cloud Run の service 相当）を自作クラウドに足し、apps-01・media-01 の小さなアプリを Kubernetes（k8s-cp-01 の1台構成、2026-10-22 から常時稼働）へ移せるようにする。

いまのコンテナ機能は function（Knative、`/v1/functions`）だけで、次の理由でほとんどのアプリが載らない。

| 足りないもの | function | 載らないアプリの例 |
| --- | --- | --- |
| 常時稼働 | 0台まで縮む | Discord Bot（Gateway に常時接続） |
| 状態（ディスク） | なし | aihist（SQLite＋`raw/`）、UBSLEEPY（`resource/image`） |
| 秘密値 | なし | mail-view（IMAP パスワード）、netmap（読み取り鍵） |
| SSO | なし | mail-view・netmap（Authentik の Forward Auth 前提） |

## 名前と範囲

- リソース名は **service**（`/v1/services`、ID `svc-` ＋16進17桁）。CLI・Provider は `shakecloud service`・`shakecloud_service`。
- 1 service = 1コンテナ・固定台数（1〜2、既定1）。サイドカー・複数コンテナ・cron は扱わない（cron は後で `job` として別に足す）。
- イメージは function と同じく指定するだけ。ビルドはしない（`build: .` のアプリは GHCR へ push するワークフローを先に足す）。

## API（`cloud/openapi/shakecloud.yaml`）

`/v1/functions`・`/v1/databases`・`/v1/volumes` の流儀（`Describe*`／`Create*`／`Delete*`、`x-shakecloud-scope`、`<名>Envelope`、同名の再作成は既存を返す、作成はすぐ返り `status` が後から変わる）に合わせる。

| メソッド・パス | operationId | scope | 内容 |
| --- | --- | --- | --- |
| `GET /v1/services` | DescribeServices | read | 自分の service。管理者は全アカウント |
| `POST /v1/services` | CreateService | write | 作成（201） |
| `GET /v1/services/{service_id}` | DescribeService | read | 1件 |
| `PATCH /v1/services/{service_id}` | UpdateService | write | `image`・`env`・`replicas`・`memory_mib`・`auth` の変更（ローリング更新） |
| `DELETE /v1/services/{service_id}` | DeleteService | write | 削除。ディスクは `retain_volume` が真なら残す |
| `POST /v1/services/{service_id}/restart` | RestartService | write | Pod の作り直し（`kubectl rollout restart` 相当） |
| `GET /v1/services/{service_id}/logs` | GetServiceLogs | read | 直近の標準出力（`tail` 行数指定）。function にも同じものを足せる |
| `PUT /v1/services/{service_id}/secrets/{name}` | PutServiceSecret | write | 秘密値の登録。値は返さない |
| `DELETE /v1/services/{service_id}/secrets/{name}` | DeleteServiceSecret | write | 秘密値の削除 |

`CreateServiceRequest`（`additionalProperties: false`）:

| 項目 | 型 | 既定 | 備考 |
| --- | --- | --- | --- |
| `name` | `^[a-z][a-z0-9-]{1,29}$` | 必須 | function と同じ規則 |
| `image` | string | 必須 | digest 指定を推奨（`compose.lock.yaml` と同じ考え） |
| `port` | int | なし | なければ入口を作らない（Bot など） |
| `replicas` | 1〜2 | 1 | ディスク付きは1に固定 |
| `memory_mib` | 32〜512 | 128 | requests＝limits（後述） |
| `cpu_millis` | 50〜1000 | 100 | requests のみ。limits は付けない |
| `env` | map | なし | 秘密でない環境変数 |
| `secret_env` | 配列 | なし | 環境変数名の一覧。値は `PutServiceSecret` で入れる |
| `disk` | `{size_gib, mount_path}` | なし | 1〜16GiB、1つまで |
| `auth` | `none`／`sso` | `sso` | 入口に Forward Auth を付けるか |
| `command`・`args` | 配列 | なし | イメージの既定を上書き |

`Service` の応答: `service_id`・`name`・`account_id`・`owner_username`・`image`・`replicas`・`ready_replicas`・`memory_mib`・`port`・`url`・`auth`・`disk`・`secret_names`・`status`（`provisioning`／`running`／`degraded`／`failed`）・`created_at`・`updated_at`。

`/v1/limits` と `/v1/capacity` に service の数とメモリ合計を足す。

## 各部品で要るもの

| 部品 | 要るもの |
| --- | --- |
| `cloud/api` | `internal/k8s`（Deployment・Service・PVC・Secret・Ingress を扱う薄いクライアント。`internal/knative` と同じ作りで、k8s 依存はここに閉じる）、`server/services.go`、管理DBの `services` 表と移行、監査イベント、所有者確認 |
| `cloud/client` | 上の全操作 |
| `cloud/cli` | `service create/list/show/update/delete/restart/logs`、`service secret put/delete`（値は標準入力から読み、引数に取らない） |
| `cloud/provider` | `shakecloud_service`（`image`・`env`・`replicas`・`memory_mib` は更新で反映、`disk` の変更は作り直し）、`shakecloud_service_secret`（値は sensitive、state には SHA-256 だけ）、data source `shakecloud_service` |
| ポータル（`server/web`） | 一覧・詳細（状態・URL・台数・ログ）・作成・削除・再起動。秘密値は名前だけ表示 |
| `cloud/mcp` | 読み取り専用の `describe_services`・`get_service_logs`（ログは秘密値が混じりうるので管理者だけ） |
| `platform/flux` | namespace `services`、ResourceQuota・LimitRange、API 用の RBAC（`functions-rbac.yaml` と同じ形） |
| `platform/terraform/services/<name>/` | 載せ替えるアプリごとの宣言（VM と同じく1サービス1 state） |

## k8s 上の実体

1つの service から namespace `services` に次を作る。名前はすべて service ID。

| 種類 | 内容 |
| --- | --- |
| Deployment | `replicas` 固定。ディスク付きは `strategy: Recreate`（RWO の取り合いを避ける）、なしは RollingUpdate。`securityContext`: 非root・`readOnlyRootFilesystem`・`capabilities.drop: [ALL]`・`allowPrivilegeEscalation: false`（stacks の compose と同じ）。`/tmp` は emptyDir（`sizeLimit` 64Mi） |
| Service（ClusterIP） | `port` があるときだけ |
| PersistentVolumeClaim | `disk` があるときだけ。後述 |
| Secret | `secret_env` の値。`envFrom` ではなく名前ごとの `secretKeyRef` で渡す |
| Ingress（またはIngressRoute） | `port` があるときだけ。後述 |

- probe はアプリが `/healthz` などを持つときだけ（`health_path` を将来足す）。無いときは TCP の readiness だけ。
- HPA・0台縮小は使わない。function との違いはここだけにしておく。
- ラベルに `shakecloud.io/account` と `shakecloud.io/service` を付け、API はこれで一覧・掃除する。

## 永続ディスク

**提案: k8s 内の local-path（k8s-cp-01 のデータ64GiB）を使う。** 既存の volume 機能（Proxmox のディスクを VM へ attach）は VM 用で、Pod へ渡すには CSI ドライバ（Proxmox CSI）を新たに入れる必要がある。

| 案 | 利点 | 手間・欠点 |
| --- | --- | --- |
| A. local-path（推奨） | 1台構成なら追加なし（local-path-provisioner の有無は実装時に確認し、無ければ導入を別途了承） | ノードに縛られる。ノードを作り直すと消えるので、バックアップ必須 |
| B. Proxmox CSI で volume 機能と統合 | `/v1/volumes` と同じ台帳・同じスナップショット | 依存の追加（CSI ドライバと PVE の権限）。1台構成では利点が小さい |
| C. ディスクを持たせず S3（Garage）だけ | Pod が使い捨てになる | SQLite のアプリは書き直しが要る |

- バックアップ: CNPG と同じく Garage へ。service に `backup: daily` を付けると、API が CronJob（restic か `tar`→S3）を作る案を [O02](O02-cnpg-backup.md)・[O03](O03-restore.md) と合わせて決める。aihist を載せる前に必須。
- `DeleteService` は既定でディスクも消す。`retain_volume: true` のときは PVC を残し、同名で作り直すと付け直す。

## 秘密値

- 値は管理DBに置かず、k8s の Secret だけに置く（API は書くだけで読まない）。etcd の暗号化（`EncryptionConfiguration`）がまだなら、入れることを提案する（control plane の設定変更なので了承後）。
- 変更すると API が Deployment の注釈（値のハッシュ）を変え、Pod を作り直す。
- 載せ替え時の値の出所は、いまの各 `manage.py` が読む `secrets/` と同じ。移行手順は Terraform の `shakecloud_service_secret` に SOPS で復号した値を渡す形にし、手で `PUT` しない。

## 入口（URL）

- URL は `<name>.svc.<クラウドのドメイン>`（function の `*.functions.…` に合わせる）。人に見せる名前は従来どおり `platform/terraform/dns.yaml` に置き、tls-proxy（core-01 の Caddy）から転送する。
- `auth: sso` のときは Authentik の Forward Auth を通す。実現方法は2案。

| 案 | 内容 | 判断 |
| --- | --- | --- |
| A. core-01 の Caddy で認証してから k8s へ転送（推奨） | いまの netmap・mail-view と同じ `forward_auth`。k8s 側は Ingress を内向きにだけ開ける | 追加なし。Caddy の設定を API から生成する仕組み（dns.yaml と同じく Git 管理）が要る |
| B. k8s の Ingress（Knative と同じ Kourier か別の Ingress Controller）に Authentik の outpost を置く | k8s で完結 | 依存の追加・メモリ（outpost だけで約100〜200MiB）。cp-01 の空きでは厳しい |

- `auth: none` は Bot の Webhook など、アプリ自身が認証するものだけ。既定は `sso`。

## メモリの予算と上限

**cp-01 の中**（6GiB、空き約1GiB）:

| 使い道 | いま | 備考 |
| --- | --- | --- |
| k8s 本体・Flux・CNPG Operator・Knative | 実測（`kubectl top`）で埋める | |
| AWX | 実測で埋める | 最大の消費者 |
| `databases`（ResourceQuota） | 640Mi | |
| `functions`（ResourceQuota） | 384Mi | 多くは0台なので実消費は小さい |
| `services`（新規） | **提案 768Mi** | 下の候補第1〜2段で埋まる量 |

- `services` の LimitRange: 既定 requests＝limits＝128Mi、最大 512Mi、最小 32Mi。CPU は requests 100m だけ。requests と limits を揃えて、1台構成でのオーバーコミット（Evict）を避ける（[Kubernetes](../operations/kubernetes.md) の AWX OOM の教訓）。
- 空き約1GiB に768Mi を足すと余裕がないので、**cp-01 を 6→8GiB にする**ことを合わせて提案する。

**ホスト全体**（認識 59.7GiB、[運用設計](../architecture/operations.md)・[配備台帳](../operations/handover.md)）: VM を減らした分を k8s へ回す。

| VM | いま | 案 | 差 |
| --- | --- | --- | --- |
| k8s-cp-01 | 6GiB | 8GiB | +2 |
| apps-01 | 4GiB（下限3） | 小さいアプリを抜いたあと 3GiB（Home Assistant・Vaultwarden・Homarr・CUPS・eufy は残す） | −1 |
| media-01 | 6GiB | aihist を抜いても大差なし。据え置き | 0 |
| 合計 | | | **+1GiB** |

- apps-01 を丸ごと無くすのは、Home Assistant（ホストネットワーク・mDNS）・CUPS（USB/IPP）・eufy（P2P・UDP）が k8s に向かないため、この計画ではしない。
- 実測値は実装に着手するときに [I01](I01-resources.md) の手順で取り直し、上の表を埋める。

## 載せる候補と順番

`stacks/` の各 `compose.yaml` で仕分けた。

| 段 | アプリ | いまの場所 | 要るもの | 備考 |
| --- | --- | --- | --- | --- |
| 1 | mail-view | apps-01 | 秘密値・SSO・入口 | 状態なし・`read_only` 済み。イメージは `python:3.13-alpine`＋`app.py` なので、`app.py` を入れたイメージを GHCR へ |
| 1 | poke-translate | apps-01 | 入口 | 状態なし |
| 1 | netmap | apps-01 | 秘密値（ファイル）・SSO | 秘密値をファイルで渡す `secret_files` が要る（`/run/netmap`）。`build: .` なので GHCR へ |
| 2 | UBSLEEPY・CIRCLEAUTH（Discord Bot） | apps-01 | 常時稼働・秘密値・ディスク（`resource/image`） | `port` なし。bot-portal が `/srv/ubsleepy` などを直接読むので、bot-portal の扱いを先に決める（API 経由にするか一緒に載せない） |
| 3 | aihist | media-01（systemd） | ディスク（SQLite＋`raw/`）・バックアップ・SSO | Compose 化されていないのでイメージ化から。ディスクのバックアップが整うまで載せない |
| 載せない | Home Assistant・CUPS（print-api）・eufy 系・LibreSpeed・Vaultwarden・Nextcloud ほか media-01 の重いもの・pkdb（PostgreSQL は database 機能へ寄せる案を別途） | | | ホストネットワーク・USB・UDP・大容量、または移す利点が小さい |

## function との関係

function に秘密値・SSO を足す案と、この service は**同じ部品を共有する**形にする。

- 秘密値（Secret と `secret_env`）と `auth`（Forward Auth）の実装は `internal/k8s` 側に1つ作り、function（Knative Service）と service（Deployment）の両方から使う。API の形（`PutFunctionSecret` など）も揃える。
- 使い分けは「呼ばれたときだけ動く・状態なし」が function、「常時・状態あり」が service。function に `min_scale: 1` を付けて service の代わりにする案は、ディスクを持てないので採らない。
- 先に service を作り、秘密値・SSO を function へ広げるのは後でよい（function の利用者がいまいない）。

## 変更範囲と実装の順

1. `platform/flux` に namespace `services`・ResourceQuota・LimitRange・RBAC（cp-01 の増枠を了承後に）。
2. `cloud/openapi` → `internal/k8s`・`server/services.go`・管理DB → client → CLI → Provider → ポータル → MCP の順に、作成・一覧・削除だけで1本通す。
3. 秘密値・入口（案A）・ディスク（案A）・ログ・再起動・更新。
4. 段1のアプリを `platform/terraform/services/<name>/` で宣言して載せ替え、apps-01 の compose を止める。
5. バックアップを決めてから段2・段3。

## 依存と並列作業

- **了承が要るもの:** cp-01 の 6→8GiB、local-path-provisioner（無い場合）、etcd の暗号化、Caddy 設定の生成の仕組み、GHCR へのイメージ push のワークフロー追加。
- **競合:** `cloud/openapi` と `server/` は [I07](I07-portal-ui.md) と、`platform/flux` の Quota は database・function の担当と調整する。

## 検証・完了条件

- `tools/tf services/<name> apply` で mail-view が k8s に立ち、Authentik でログインした人だけが開ける。apps-01 側を止めても同じ URL で使える。
- 再適用で差分がない。秘密値は API 応答・ログ・Terraform state に平文で出ない。
- Pod を消してもディスクの中身が残る。バックアップから別名で戻せる。
- `services` の合計が Quota を超える作成は 4xx で断られ、既存の AWX・database が Evict されない。
