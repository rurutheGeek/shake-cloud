---
title: AWX の使い方
updated: 2026-09-12
section: 運用手順
audience: 管理者
tags:
  - ops
  - awx
---

# AWX の使い方

> **更新日** 2026-09-12 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 配備済み（AWX 24.6.1 / Operator 2.19.1）。ジョブテンプレートの整備はこれから。

AWX は Ansible Playbook をブラウザと API から実行し、実行履歴・権限・スケジュールを管理する基盤です。NetBox をインベントリ源にして、`platform/ansible/` の Playbook を回す用途を想定しています。

## 入口とログイン

| 項目 | 値 |
| --- | --- |
| URL | <https://awx.apextox.dpdns.org/> |
| ユーザー | `admin` |
| パスワード | `platform/flux/apps/awx-instance/admin-password.sops.yaml`（管理者のSOPS鍵で復号） |
| 稼働場所 | Kubernetes の `k8s-worker-01`（namespace `awx`） |
| 配備 | `platform/flux/apps/awx-operator.yaml` → `awx-instance/`（Flux が Git から適用） |

パスワードを見る:

```bash
sops -d platform/flux/apps/awx-instance/admin-password.sops.yaml | grep -i password
```

ログイン後は右上のユーザーメニューから **Access → Users** で追加アカウントを作れます。SSO（Authentik）はまだ繋いでいません。

## 今できること

- **Web UI**: インベントリ・プロジェクト・テンプレート・ジョブ履歴を管理。
- **REST API**: `https://awx.apextox.dpdns.org/api/v2/`（要トークン）。疎通確認は `/api/v2/ping/`。
- **CLI**: `pip install awxkit` で `awx` コマンド。`awx login -f https://awx.apextox.dpdns.org` のように使います。
- **Playbook の実行**: プロジェクト（Git）とジョブテンプレートを登録すれば、このリポジトリの Playbook を実行できます。

```bash
# 疎通確認（未認証でも応答する ping）
curl -sk https://awx.apextox.dpdns.org/api/v2/ping/
```

## これから（移行）

`platform/awx/` に EE（Execution Environment）と登録 Playbook の例があります。AWX へ **NetBox インベントリ・クレデンシャル・プロジェクト・ジョブテンプレート**を登録する手順は同ディレクトリの `README.md` にあります。

**この登録はまだ実 API へ適用していません。** 適用するときは、`platform/awx/configure.yml` を実行し、`Deploy portable services` が動くことを確認してください。

## 運用

- **アップグレード**は `platform/flux/apps/awx-instance/awx.yaml` の版を変えて `main` へ push（Flux が反映）。
- **停止・起動**は Kubernetes 側です。`tools/k8s down` / `up` でノードごと落とせます（[Kubernetes クラスタ](kubernetes.md#起動と停止)）。
- **バックアップ**は別途必要です。AWX の DB・Secret・PVC は `platform/awx/README.md` の注意どおり、管理DBのバックアップとは別に設計します。

## 関連

- [Kubernetes クラスタ](kubernetes.md#アプリ-awx)（配備の中身・HTTPS・トラブルシュート）
- [Flux にアプリを足す](flux-apps.md)
- [接続先一覧](../reference/urls.md)
- `platform/awx/README.md`（EE と登録 Playbook の例）
