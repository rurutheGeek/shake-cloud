# Kubernetes クラスタ

更新日: 2026-09-12。状態: **スライス③（共通基盤: local-path・MetalLB・cert-manager）まで実機で確認済み**。PVC の永続化・LoadBalancer・CA 証明書が動いています。**Flux/SOPS だけは Git の取り込み方を決めてから**入れます。

## 何に使うか

近い将来に載せるのは **AWX** と、**クラウドの function（Knative）／database（CloudNativePG）**です。自作 cloud API 本体は cloud-01 の Compose のままで動くので、移すかは後で決めます。メディア系の移行は後回しです。

**使わないときは落とせます。** control plane と worker は別VMなので、worker だけ止めて control plane（etcd/API）を残す、全部止める、どちらもできます（[起動と停止](#起動と停止)）。

## 版と CIDR

版は `platform/ansible/k8s-vars.yml` が唯一の出所です。

| 項目 | 値 | 理由 |
| --- | --- | --- |
| Kubernetes | **1.36.4** | Cilium 1.20 が e2e で保証するのは 1.36 まで（1.37 は未対応） |
| containerd | **2.3.5**（LTS） | Kubernetes 1.36 が対応。Docker の apt から版指定で入れる |
| Cilium | **1.20.1** | **kube-proxy を置き換える**（Service も Cilium が担う） |
| Helm | 3.22.0 | Cilium 導入に使う。cp に版指定＋SHA256 検証で入れる |
| Pod CIDR | `10.244.0.0/16` | LAN `192.168.10.0/24`・クラウド用と重ならない |
| Service CIDR | `10.96.0.0/12` | 同上 |

**k8s ノードはバルーニングしません。** kubelet はVMの上限メモリを「使える量」としてスケジューラに広告するため、後からホストが回収すると Pod が追い出されます。上限＝実際に使う量で固定します。

## ノード

| VMID | 名前 | IP | 役割 | vCPU | RAM | ディスク | 状態 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 200 | k8s-cp-01 | .207 | control plane・etcd | 2 | 3GiB | 32 | Ready（control-plane taint あり） |
| 210 | k8s-worker-01 | .209 | ワークロード（AWX・cloud など） | 4 | 8GiB | OS32+データ64 | Ready |
| 211 | k8s-worker-02 | .208 | 予備の worker | 4 | 8GiB | OS32+データ48 | **停止のまま**。RAM が要るときに起動して join |

宣言の正本は `platform/terraform/hosts.yaml`、`10-platform` が作ります。Pod は control plane に載せず（taint を外さない）、worker に載せます。

## 準備とクラスタ作成

```bash
# VM（初回だけ）
tools/tf 10-platform apply

# ノード準備 → cp で init+Cilium → worker join
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook \
     -i platform/ansible/inventory.netbox.yml platform/ansible/kubernetes.yml \
     --limit k8s-cp-01,k8s-worker-01'
```

playbook は3段です。どれも再実行できます。

1. **`k8s_node`**（全ノード）: swap 無効・`overlay`/`br_netfilter`・sysctl・containerd 2.3.5・`kubeadm`/`kubelet`/`kubectl` 1.36.4。
2. **`k8s_control_plane`**（cp）: `/etc/kubeadm-init.yaml` で `kubeadm init`（**`--skip-phases=addon/kube-proxy`**、Pod/Service CIDR を指定）。かぶらないよう kube-proxy は置きません。Helm を入れ、**Cilium 1.20.1 を kube-proxy 置換で**導入します（`kubeProxyReplacement: true`、`k8sServiceHost` は cp の IP、IPAM は kubernetes）。kubeconfig は `debian` の `~/.kube/config` に置きます。
3. **`k8s_join`**（worker）: 未参加（`/etc/kubernetes/kubelet.conf` が無い）ときだけ join。

停止中の worker-02 は到達できないので `--limit` で外します。起動後に `--limit k8s-worker-02` で流せば参加します。

### 確認

```bash
ssh debian@192.168.10.207 'kubectl get nodes'
```

実機確認（2026-09-12）: 2ノードが **Ready**、`cilium status` が **OK**。テスト用の client→server で **ClusterIP 通信が 200**、`default-deny` の NetworkPolicy で **遮断（000）**、client からの allow で **200** に戻ることを確認しました（テスト namespace は削除済み）。cp には control-plane の taint を残しているので Pod は worker-01 に載ります。

## 共通基盤

`k8s_addons` ロールが cp から入れます（再実行可）。版は `platform/ansible/roles/k8s_addons/defaults/main.yml`。

| 役割 | 何を入れる | 設定 |
| --- | --- | --- |
| 永続ストレージ | local-path-provisioner **v0.0.37** | worker のデータディスク（`/dev/vdb`）を `/srv/k8s` にマウントし、PV は `/srv/k8s/local-path` に置く。`local-path` を既定 StorageClass にする |
| LoadBalancer | MetalLB **0.16.1**（L2） | `network.yaml` の `metallb` レンジ `.240-.249`。NetBox の管理レンジ（`.201-.239`）から切り出してある |
| 証明書 | cert-manager **v1.21.2** | 自前 CA の `ClusterIssuer` **`shakecloud-ca`**（`shakecloud-selfsigned` から発行）。外部 DNS が要らない。Let's Encrypt は後で足す |

実機確認（2026-09-12）: PVC に書いたファイルが Pod を作り直しても残ること、`LoadBalancer` が `.240` を得て `curl` が **200**、`ClusterIssuer` `shakecloud-ca` と CA `Certificate` が **Ready** であることを確認しました。

**Flux/SOPS はまだ入れていません。** 作業ブランチを `main` へ取り込む時期と GitOps のディレクトリ構成を決めてから入れます。

## GitOps（Flux + SOPS）

クラスタ内のアプリは **Flux が Git から適用**します。監視先は `main` の `platform/flux` です。

- **Flux 2.9.5** を bootstrap 済み。`flux-system` namespace で4コントローラが動き、リポジトリ専用の deploy key を使います。
- 置き場: `platform/flux/flux-system/`（Flux 本体と同期設定）、`platform/flux/infra/`・`platform/flux/apps/`（追加していく場所。Flux は再帰的に読みます）。
- **秘密値は SOPS**。`platform/flux/**/*.sops.yaml` を age で暗号化し、クラスタ内の Secret `flux-system/sops-age`（キー `age.agekey`）で復号します。ルート Kustomization に `decryption` を設定済みです。

bootstrap（初回のみ。再実行すると Flux のマニフェストを作り直します）:

```bash
export KUBECONFIG=<クラスタの admin.conf>
GITHUB_TOKEN=$(gh auth token) flux bootstrap github \
  --owner=rurutheGeek --repository=shake-cloud --branch=main --path=platform/flux --personal
```

`sops-age` は**復号の鍵そのもの**なので Git に置けません。配備時に人が入れます（pod が落ちても消えません）:

```bash
kubectl -n flux-system create secret generic sops-age \
  --from-file=age.agekey=$HOME/.config/sops/age/keys.txt
```

新しい秘密値は `.sops.yaml` のルールで暗号化して置きます。コミットして push すれば Flux が復号して適用します:

```bash
sops platform/flux/apps/<name>.sops.yaml
```

実機確認（2026-09-12）: 4コントローラが Running、`Kustomization/flux-system` が `Applied revision`。SOPS で暗号化した Secret が**復号されて作られる**こと、Git から消すと **prune される**ことを確認しました。

## アプリ: AWX

AWX（Ansible の実行基盤）を **worker-01** に Flux で配備しています。

| 項目 | 値 |
| --- | --- |
| 入口 | **`https://awx.apextox.dpdns.org/`**（Cilium Ingress。証明書は cert-manager が Let's Encrypt で発行） |
| 管理者 | ユーザー `admin`。パスワードは `platform/flux/apps/awx-instance/admin-password.sops.yaml`（`sops -d ... \| grep password` で見る） |
| DB | Operator 内蔵の PostgreSQL。PVC は local-path（worker-01 のデータディスク） |
| 版 | Operator **2.19.1** / AWX **24.6.1** |
| 置き場 | `platform/flux/apps/`（Flux が Git から適用。`dependsOn` で Operator → AWX の順） |

- Operator は上流リポジトリ（tag `2.19.1`）を Flux の `GitRepository` で取得し、`config/default` を kustomize で適用します。**`kube-rbac-proxy` は GCR から消えている**ため quay のミラーに差し替えています。
- **HTTPS**: Cilium の Ingress（共有 LB `cilium-ingress` = **192.168.10.241**）が受け、cert-manager の `ClusterIssuer` **`letsencrypt-dns`**（Cloudflare DNS-01）が証明書を発行します。名前は `dns.yaml` の `awx` レコードで `.241` に向けています。AWX は `service_type: ClusterIP` で、Ingress(`cilium`) から `awx-service` へルーティングします。
  - Ingress を有効化した直後は **`cilium-envoy` を作り直さないと共有 LB が待ち受けを始めません**（`k8s_control_plane` ロールが Cilium の値変更時に再起動します）。
- **k8s ノードはバルーニングを無効化**しました（`memory_min_mib` = `memory_mib`）。kubelet が上限を「使える量」として広告するので、ホストが後から回収すると Pod が追い出されます。最初の配備で worker-01 が 5.9GiB に縮み、**AWX が OOM/Evict** されました。固定後は 8GiB を使い、AWX 込みで空き約 4GiB です。
- `awx` namespace の `AWX/awx` は `Running: True`。`https://awx.apextox.dpdns.org/api/v2/ping/` が応答します。HTTP は 301 で HTTPS へ転送されます。

## アプリ: CloudNativePG（database）

クラウドの **`shakecloud_database`**（利用者に PostgreSQL を渡す機能）の実体です。Operator と最初の Cluster を Flux で配っています。

- **Operator**: `platform/flux/apps/cnpg/`（Helm chart **0.29.0 → operator 1.30.0**、namespace `cnpg-system`）。CRD を先に入れる必要があるので子 Kustomization `cnpg` に分け、Cluster 側から `dependsOn` しています。
- **Cluster `demo`**: `platform/flux/apps/databases/`（namespace `databases`、`instances: 1`、PVC は local-path **5Gi**）。
- CNPG が作るもの: `demo-rw`（読み書き）/`demo-ro`（読み取り専用）/`demo-r` の Service、接続情報の Secret **`demo-app`**。レプリカ・バックアップ・フェイルオーバーは台数を増やしたときに効きます。

実機確認（2026-09-12）: `kubectl -n databases get cluster demo` が **INSTANCES 1 / READY 1 / Cluster in healthy state**、PVC `demo-1` が Bound、`psql -U postgres` が **PostgreSQL 18** を返すことを確認しました。

**API から作れます。** `POST /v1/databases` が `databases` namespace に CNPG Cluster を作り、`GET /v1/databases`・`GET`/`DELETE /v1/databases/{id}`・`GET /v1/databases/{id}/credentials` があります。API は Flux で作った ServiceAccount **`databases/cloud-api`**（CNPG Cluster と Secret だけ触れる最小 RBAC）のトークンで Kubernetes を操作します。トークンと CA は `platform/sops/k8s.sops.yaml` に置き、cloud_api ロールが cloud-01 の `secrets/k8s_ca`・`secrets/k8s_token` へ写します。Provider `shakecloud_database` と CLI は次の段です。

## アプリ: Knative（function）

クラウドの **`shakecloud_function`**（利用者にサーバレス HTTP を渡す機能）の実体です。Knative Operator と Serving（Kourier）を Flux で配っています。

- **Knative Operator 1.23.1**（`platform/flux/apps/knative.yaml`）。上流 `config/default` を kustomize で適用しますが、**`ko://` のままなので release の digest に差し替え**ています。また、Operator が Serving 用の RBAC を委譲できるよう `cluster-admin` を束ねています（付けないと `attempting to grant RBAC permissions not currently held` で失敗します）。
- **Knative Serving 1.23.0 + Kourier**（`platform/flux/apps/knative-serving/`）。ゲートウェイは `knative-serving/kourier` の LoadBalancer（MetalLB が IP を配る）。
- **`config-network.ingress-class` は完全名 `kourier.ingress.networking.knative.dev`**。短縮名 `kourier` にすると Ingress の annotation が短縮名になり、net-kourier controller のフィルタ（完全名）に一致せず **Ingress が reconcile されません**（2026-09-12 に実際に踏みました）。
- 関数 URL は `<name>.functions.k8s.apextox.dpdns.org`。DNS は `*.functions.k8s`（`dns.yaml`、Kourier の LB）を向けてあり、**HTTPS** で叩けます。TLS は `config-network.external-domain-tls: Enabled` と `config-certmanager`（`issuerRef: letsencrypt-dns`、Cloudflare DNS-01）で、`namespace-wildcard-cert-selector` に合う namespace（`functions`）へ**ワイルドカード証明書を1枚**発行します。**TLS を有効にした後は `controller` を作り直す**必要があります（実機で踏みました）。
- **API から作れます。** `POST /v1/functions` が `functions` namespace に Knative Service を作ります。API は database と同じ ServiceAccount（`databases/cloud-api`）を使い、Flux が `functions` namespace の Role（Knative Service だけ）を与えています。

実機確認（2026-09-12）: hello-world の Knative Service が **Ready** になり、Kourier の LB IP に Host ヘッダで投げると `Hello shake-cloud!` が返り、Pod が 0→1 にスケールすることを確認しました。`POST /v1/functions` でも同じ流れ（Provisioning → Ready、URL 発行、削除で Service ごと消える）を確認しました。

## 起動と停止

`tools/k8s` で、k8s の VM だけを順番に起こしたり落としたりできます（ACPI で綺麗に落とすので、etcd も正しく停止します）。

```bash
tools/k8s status     # 各VMの状態
tools/k8s up         # cp → worker の順に起動
tools/k8s down       # worker → cp の順に停止
tools/k8s up --all   # worker-02 も含めて起動
```

RAM が足りないときは `k8s-worker-02` を起動し、使わないときは落としておきます。

## 次のスライス

1. CNPG のバックアップを Garage（S3）へ
2. Phase 8 の VLAN 実機切替（物理スイッチ/ルータ）
