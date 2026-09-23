---
title: 用語集
updated: 2026-09-23
section: リファレンス
audience: 全員
tags:
  - reference
  - glossary
---

# 用語集

> **更新日** 2026-09-23 ・ **区分** リファレンス ・ **読む人** 全員

このドキュメントに出てくる固有名と略語です。**詳しい説明はリンク先が正本**で、ここは「読み進めるために最低限いる説明」だけを置きます。

## VMと役割

| 名前 | 何か |
| --- | --- |
| `apextox` | 物理ホスト1台。Proxmox VE が動き、すべてのVMを載せる。管理は `192.168.10.10` |
| `router-01` | **家庭内ルータ（OpenWrt）。** K11上のVM（`192.168.10.1`）で、ファイアウォール・DHCP・DNSを担う（[router-01](../operations/router.md)） |
| `identity` | 共通ログイン（Authentik）のVM（[認証基盤](../operations/identity.md)） |
| `cloud-01` | 自作クラウド shakecloud のAPI・ポータル・管理DB（[クラウドAPIの構築](../operations/cloud.md)） |
| `services-01` | 台帳・手順書サイト・Homarr・パスワード・家電・印刷・速度テスト |
| `storage-s3` | S3互換オブジェクトストア Garage（[Garage](../operations/garage.md)） |
| `media-01` | Nextcloud・Kavita・Navidrome・FreshRSS・LocalSend受信機 |
| `monitor-01` | Prometheus・Alertmanager・Grafana |
| `game1` | ゲームとローカルAI。GPUをパススルーしている |
| `net-01` | 宅外から管理LANへ戻るための subnet router（[net-01](../operations/net.md)） |
| `k8s-cp-01` / `k8s-worker-*` | Kubernetes。AWX・DB提供・関数提供が載る（[Kubernetes](../operations/kubernetes.md)） |
| `dev-a` / `dev-b` | 開発VM（[開発VMの使い方](../services/devvm.md)） |

## 仕組みの名前

| 用語 | 意味 |
| --- | --- |
| **shakecloud** | このリポジトリで自作しているプライベートクラウド。VM・S3・DB・関数の4機能をAPI・CLI・Terraform Provider・ポータルから扱う |
| **プール** | Proxmox 側のVMの区分。`platform`（基盤、Terraformが作る）・`cloud`（利用者VM、shakecloudが作る）・`dev`・`lab` |
| **VMID帯** | プールごとのID範囲。platform 100–399、dev 400–499、lab 900–999、cloud 5000–5999 |
| **アクセスキー** | 機械（CLI・Terraform）用の資格情報。`sca_<キーID>.<秘密値>` の形。ポータルにログインして発行する |
| **配備台帳** | [handover.md](../operations/handover.md)。実機の状態・決定・TODOの正本 |
| **作業ID** | W・A・G・H・N・I・M・O・D で始まる開発単位（[開発計画](../development/index.md)）。番号は実施順ではない |
| **正本** | その事実を書いてよい唯一の場所。ほかのページはリンクするだけにする |
| **機器帯 / DHCP帯** | アドレスの切り分け。機器帯 `.2`–`.19`（ルータ・AP・プリンタ・ホスト）、DHCP `.20`–`.99`（router-01 が配る）、クラウド `.100`–`.180`、管理 `.201`–`.239`、MetalLB `.240`–`.249`。正本は `platform/terraform/network.yaml` |
| **バルク領域** | Proxmoxホスト直結の6TB USB HDD（`/srv/bulk`）。メディア原本と週次バックアップの置き場（[共有バルクストレージ](../operations/bulk-storage.md)） |

## 使っているソフト

| 名前 | 役割 |
| --- | --- |
| **Proxmox VE** | 仮想化基盤。VMを作って動かす |
| **Authentik** | 共通ログイン（OIDC・招待・パスキー） |
| **NetBox** | 配備先とIPの台帳。Ansible・Terraform・クラウドAPIが読む |
| **Terraform** | 宣言からリソースを作る。基盤VMとサービスVMの宣言に使う |
| **Ansible** | ホストの中身（Docker・各サービス）を配る |
| **Flux** | Gitの内容をKubernetesクラスタへ反映する |
| **AWX** | Playbookをブラウザ・APIから実行する基盤 |
| **Caddy** | 各VMのHTTPS入口。証明書をDNS-01で取る（`stacks/tls-proxy/`） |
| **Garage** | S3互換のオブジェクトストア |
| **CloudNativePG** | Kubernetes上のPostgreSQL。クラウドの「database」機能の実体 |
| **Knative** | Kubernetes上のHTTP実行。クラウドの「function」機能の実体 |
| **SOPS / age** | 秘密値を暗号化したままGitに置くための道具（[秘密値の管理](../operations/secrets.md)） |
| **OpenWrt** | ルータ用のLinux。`router-01` の中身。設定の正本は `platform/openwrt/` |
| **AdGuard Home** | DNSサーバー兼広告・トラッカー遮断。`router-01` 上で家中の名前解決を担う（[AdGuard Home](../operations/adguard.md)） |
| **LuCI** | OpenWrt の管理画面。**SSOを付けていない**（復旧経路のため） |
| **LibreSpeed** | 自前の回線速度テスト。services-01（[LibreSpeed](../services/librespeed.md)） |
| **Homarr** | サービス一覧のハブ画面 |
| **Nextcloud / Kavita / Navidrome / FreshRSS** | ファイル／本／音楽／RSS |
| **Vaultwarden** | パスワード保管庫 |
| **Home Assistant** | 家電の操作・自動化 |
| **CUPS** | 印刷サーバ |

## 略語

| 略語 | 展開 |
| --- | --- |
| IaC | Infrastructure as Code。構成をコードで宣言して作ること（[IaCの所有境界](../architecture/iac.md)） |
| SSO | Single Sign-On。1つのアカウントで複数サービスに入ること |
| OIDC | OpenID Connect。ブラウザのログインに使う仕組み |
| Forward Auth | 逆プロキシが先に認証を確かめてからアプリへ通す方式。OIDC非対応のアプリで使う |
| SG | セキュリティグループ。クラウドVMの通信許可の宣言 |
| CNPG | CloudNativePG |
| DNS-01 | DNSレコードで所有を示して証明書を取る方式。サーバーを公開せずに済む |
| UPS | 無停電電源装置（[電源とUPS](../operations/power.md)） |
| OPDS | 電子書籍の配信・購読に使う目録の形式 |
