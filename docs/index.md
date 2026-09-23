---
title: Shake Lab Docs
updated: 2026-09-18
section: 入口
audience: 全員
tags:
  - hub
---

# Shake Lab Docs

> **更新日** 2026-09-18 ・ **区分** 入口 ・ **読む人** 全員

Proxmox VE の1台に役割ごとのVMを分け、メディア・家電・パスワードから自作のプライベートクラウドまでを、家庭内LANのHTTPS名から使えるようにしている環境の手順書です。原稿の正本は Git の `docs/` で、正本リポジトリは <https://github.com/rurutheGeek/shake-cloud> です。

このページは案内板です。**目的から1つ選んでください。**

## 1. サービスを使いたい

アカウントを受け取って、ファイル・本・音楽・家電・パスワードを使う人向けです。SSHやコマンドは要りません。

| 最初に読む | 内容 |
| --- | --- |
| [利用ガイドの入口](services/index.md) | 利用者向けページの一覧 |
| [全サービスの使い方](services/usage.md) | 何をどこで開くか |
| [共通ログインの使い方](services/identity.md) | 招待・パスキー・パスワード再設定 |
| [接続先一覧](reference/urls.md) | すべてのURLとアドレス |

## 2. 開発に参加したい

開発VMに入り、機能を作って配備する人向けです。

| 最初に読む | 内容 |
| --- | --- |
| [開発参加ガイド](onboarding.md) | 開発VMへの入り方・鍵・電源 |
| [開発計画の入口](development/index.md) | 作業IDの一覧と並列作業のルール |
| [クラウドの使い方](services/cloud.md) | 自分用のVM・S3・DB・関数を作る |
| [サービスの置き場所](operations/services.md) | 書いたコードをどこへ置くか |

## 3. 環境を立ち上げる・運用する

ホストからやり直す人、日々の運用や復旧をする人向けです。

| 最初に読む | 内容 |
| --- | --- |
| [運用手順の入口](operations/index.md) | 立ち上げ順・日常運用・復旧の一覧 |
| [初回セットアップの順番](operations/bootstrap.md) | 何もない状態からの手順 |
| [配備台帳](operations/handover.md) | 実機の状態・進捗・TODOの正本 |
| [確認と、はまりどころ](operations/verify.md) | 変更後の検査と、実際に踏んだ落とし穴 |
| [秘密値の管理](operations/secrets.md) | SOPS と age |

## 4. 仕組みを知りたい

| 最初に読む | 内容 |
| --- | --- |
| [ホームラボの全体像](architecture/overview.md) | 何がどのVMで動いているかの詳細版 |
| [設計の入口](architecture/index.md) | 決定と根拠 |
| [決定ログ](architecture/decisions.md) | すでに決まっていることと、その理由 |
| [信頼境界とセキュリティ方針](architecture/security.md) | 何を信頼し、何を信頼しないか |
| [障害モードと単一障害点](architecture/failure-modes.md) | 何が止まると何が使えなくなるか |
| [用語集](reference/glossary.md) | VM名・プール・略語 |

## 全体の構成

| 役割 | VM | 中身 |
| --- | --- | --- |
| 共通ログイン | identity | Authentik。招待・メール復旧・パスキー |
| 自作クラウド | cloud-01 | shakecloud API・CLI・Provider・ポータル・管理DB |
| 台帳・docs・パスワード・家電 | services-01 | NetBox・Shake Lab Docs・Homarr・Vaultwarden・Home Assistant・CUPS |
| S3・バックアップ | storage-s3 | Garage（S3互換） |
| クラスタ | k8s-cp-01・k8s-worker-01・k8s-worker-02 | Kubernetes・AWX・CloudNativePG（DB）・Knative（関数） |
| メディア | media-01 | Nextcloud・Kavita・Navidrome・FreshRSS・LocalSend |
| 監視 | monitor-01 | Prometheus・Alertmanager・Grafana |
| ゲーム・AI | game1（GPUパススルー） | Wolf・RomM・SFTPGo |
| 復旧経路 | net-01 | subnet router（宅外から管理LANへ） |
| 開発 | dev-a・dev-b | Terraform・Docker・Go |

**基盤VMは Terraform**、**cloudプールのVMは自作API・Provider** が作り、IPはどちらも NetBox から採番します。役割ごとの詳細は[ホームラボの全体像](architecture/overview.md)、実機の状態は[配備台帳](operations/handover.md)が正本です。

## このドキュメントの歩き方

- **どこに何があるか**は[ドキュメント地図](map.md)にまとめています。Obsidian で `docs/` を開くときも同じ地図を使えます。
- **書き足すとき**は[ドキュメントの書き方](contributing-docs.md)を先に読んでください。
- 各ページの先頭には **更新日・区分・読む人** を置いています。内容が最後に変わった日で、閲覧日ではありません。
- 同じ事実を2か所に書きません。迷ったときの正本は、**URLは[接続先一覧](reference/urls.md)**、**実機の状態は[配備台帳](operations/handover.md)**、**作業の進捗は[各作業IDの計画書](development/index.md)** です。

**既知の制約**: LANの外から使うにはVPNが要ります（未構築）。制約の一覧は[全体像の「既知の制約」](architecture/overview.md)にあります。
