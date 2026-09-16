# Flux にアプリを足す手順

更新日: 2026-09-13。`platform/flux` にアプリを追加するときの決まりと雛形。実際の例は AWX（`apps/awx*.yaml` と `apps/awx-instance/`）と Let's Encrypt の発行体（`apps/cert-issuer.yaml` と `infra/cert-issuer/`）にあります。

## 決まり

- Flux は `main` の **`platform/flux`** を見ます。ルートの `platform/flux/kustomization.yaml` が**適用する一覧**を持ちます（再帰適用しません。CRD が先に必要な CR を直接置かないため）。
- アプリ1つ = **子 Kustomization 1つ** + **中身のディレクトリ1つ**。
  - 子 Kustomization: `platform/flux/apps/<name>.yaml`
  - 中身: `platform/flux/apps/<name>/`（インフラ寄りなら `platform/flux/infra/<name>/`）
- **秘密値は SOPS**。`platform/flux/**/*.sops.yaml` を age で暗号化します。復号鍵はクラスタ内の `flux-system/sops-age` にあります。ルート Kustomization（`platform/flux/flux-system/gotk-sync.yaml`）にも `decryption` を設定済みですが、**暗号化ファイルを適用する Kustomization に `decryption` が必要**です。子 Kustomization はそれぞれ自分の `path` 先を復号するので、子のパスに秘密値を置くときはその子にも付けます（AWX が実例）。

## 手順

1. 中身のディレクトリ `platform/flux/apps/<name>/` を作り、マニフェストを置く。
2. 子 Kustomization を `platform/flux/apps/<name>.yaml` に作る（下の雛形）。
3. ルート `platform/flux/kustomization.yaml` の `resources` に `apps/<name>.yaml` を足す。
4. 秘密値があれば暗号化する: `sops --encrypt --in-place platform/flux/apps/<name>/secret.sops.yaml`。
5. commit して `main` へ push。Flux が拾う（GitRepository は1分、Kustomization は30分。急ぐときは `flux reconcile`）。

## 雛形

### A. 普通のマニフェスト（必要なら SOPS の秘密値を含む）

```yaml
# platform/flux/apps/web.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: web
  namespace: flux-system
spec:
  interval: 30m
  path: ./platform/flux/apps/web
  prune: true
  wait: true
  sourceRef:
    kind: GitRepository
    name: flux-system
  decryption:            # 秘密値を復号するときだけ
    provider: sops
    secretRef:
      name: sops-age
```

### B. CRD を持つ Operator の後（順番を固定する）

Operator が先、その CR は後。子 Kustomization に `dependsOn` を付けます。

```yaml
spec:
  # ... 上の A と同じ ...
  dependsOn:
    - name: <operator の Kustomization 名>
```

### C. 上流リポジトリの kustomize を使う（例: AWX Operator）

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata: {name: <name>, namespace: flux-system}
spec:
  interval: 30m
  url: https://github.com/<org>/<repo>
  ref: {tag: "x.y.z"}
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata: {name: <name>, namespace: flux-system}
spec:
  interval: 30m
  path: ./config/default
  prune: true
  wait: true
  sourceRef: {kind: GitRepository, name: <name>}
  targetNamespace: <namespace>
  # 上流が :latest や削除済みイメージを使うなら固定・差し替え
  images:
    - {name: gcr.io/example/old, newName: quay.io/example/mirror, newTag: v1.2.3}
    - {name: example/app, newTag: "1.2.3"}
```

### D. Helm チャート（helm-controller が入っています）

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: HelmRepository
metadata: {name: <repo>, namespace: flux-system}
spec: {interval: 1h, url: https://example.github.io/charts}
---
apiVersion: helm.toolkit.fluxcd.io/v2
kind: HelmRelease
metadata: {name: <name>, namespace: <namespace>}
spec:
  interval: 30m
  chart:
    spec:
      chart: <chart>
      version: "1.2.3"
      sourceRef: {kind: HelmRepository, name: <repo>, namespace: flux-system}
  values:
    key: value
```

## 確認

```bash
export KUBECONFIG=~/.kube/shake.kubeconfig

flux get kustomizations
flux reconcile kustomization <name> --with-source   # 即時反映（失敗時は待ち続けるので注意）
kubectl -n <namespace> get pods

# 失敗の理由
kubectl -n flux-system get kustomization <name> \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}'
```

## 落とし穴

- ルートに CR を直接置くと、**まだ CRD が無い状態で適用**されて失敗ループになります。子 Kustomization に分けて `dependsOn` を付けてください。
- SOPS の `decryption` は**そのファイルを適用する Kustomization に**必要です。
- **`sops-age` Secret は Git に置けません**（復号鍵そのもの）。初回だけ人が入れます（[Kubernetes クラスタ](kubernetes.md#gitopsflux--sops)）。
- 上流イメージの `:latest` や削除済みタグはトラブルの元です。`images:` で固定してください（AWX で実際に踏みました）。
