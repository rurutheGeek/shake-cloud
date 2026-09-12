# Kubernetes クラスタ

更新日: 2026-09-12。状態: **スライス①（宣言・VM作成・ノード準備）を実機で確認済み**。クラスタ本体（`kubeadm init`/join、Cilium）は次のスライス。

## 何に使うか

近い将来に載せるのは **AWX** と、**クラウドの function（Knative）／database（CloudNativePG）**です。自作 cloud API 本体は cloud-01 の Compose のままで動くので、移すかは後で決めます。メディア系の移行は後回しです。

**使わないときは落とせます。** control plane と worker は別VMなので、worker だけ止めて control plane（etcd/API）を残す、全部止める、どちらもできます（[起動と停止](#起動と停止)）。

## 版と CIDR

版は `platform/ansible/roles/k8s_node/defaults/main.yml` が唯一の出所です。

| 項目 | 値 | 理由 |
| --- | --- | --- |
| Kubernetes | **1.36.4** | Cilium 1.20 が e2e で保証するのは 1.36 まで（1.37 は未対応） |
| containerd | **2.3.5**（LTS） | Kubernetes 1.36 が対応。Docker の apt から版指定で入れる |
| Cilium | 1.20.1（次のスライス） | kube-proxy 置換で使う予定 |
| Pod CIDR | `10.244.0.0/16` | LAN `192.168.10.0/24`・クラウド用と重ならない |
| Service CIDR | `10.96.0.0/12` | 同上 |

**k8s ノードはバルーニングしません。** kubelet はVMの上限メモリを「使える量」としてスケジューラに広告するため、後からホストが回収すると Pod が追い出されます。上限＝実際に使う量で固定します。

## ノード

| VMID | 名前 | IP | 役割 | vCPU | RAM | ディスク | 起動 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 200 | k8s-cp-01 | .207 | control plane・etcd | 2 | 3GiB | 32 | 常時 |
| 210 | k8s-worker-01 | .209 | ワークロード（AWX・cloud など） | 4 | 8GiB | OS32+データ64 | 常時 |
| 211 | k8s-worker-02 | .208 | 予備の worker | 4 | 8GiB | OS32+データ48 | **停止のまま作成**。RAM が要るときに起動 |

宣言の正本は `platform/terraform/hosts.yaml`、`10-platform` が作ります。

## 準備（このスライスでやること）

```bash
tools/tf 10-platform apply
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook \
     -i platform/ansible/inventory.netbox.yml platform/ansible/kubernetes.yml'
```

`k8s_node` ロールがやること:

- swap を止め、`/etc/fstab` から外す
- `overlay`・`br_netfilter` を読み込み、`net.ipv4.ip_forward` などを設定
- containerd を版指定で入れて `SystemdCgroup = true`、hold
- `kubeadm`／`kubelet`／`kubectl` を版指定で入れて hold

この時点では **まだクラスタではありません**。`kubelet` は設定待ちで止まっています。`kubectl get nodes` ができるのは次のスライス（`kubeadm init`/join）以降です。

実機確認（2026-09-12）: `tools/tf 10-platform` で3台を作成後、`kubernetes.yml` を cp-01 と worker-01 へ流し、`kubeadm`／`kubelet` が **v1.36.4**、`containerd` が **2.3.5** で active、`qemu-guest-agent` active、`net.ipv4.ip_forward=1`・`net.bridge.bridge-nf-call-iptables=1`、swap 無効、apt hold 済みを確認しました。worker-02 は停止中なので未適用です（起動後に `--limit k8s-worker-02` で流します）。

## 起動と停止

`tools/k8s` で、k8s の VM だけを順番に起こしたり落としたりできます（ACPI で綺麗に落とすので、etcd も正しく停止します）。

```bash
tools/k8s status     # 各VMの状態
tools/k8s up         # cp → worker の順に起動
tools/k8s down       # worker → cp の順に停止
```

RAM が足りないときは `k8s-worker-02` を起動し、使わないときは落としておきます。

## 次のスライス

1. `kubeadm init`（cp）と `kubeadm join`（worker）
2. Cilium を入れ、node Ready・Pod間通信・NetworkPolicy を確認
3. local-path PVC・MetalLB・cert-manager・Flux/SOPS
4. AWX、CloudNativePG、Knative
