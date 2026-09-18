---
title: 運用手順の入口
updated: 2026-09-18
section: 運用手順
audience: 管理者
tags:
  - ops
---

# 運用手順の入口

> **更新日** 2026-09-18 ・ **区分** 運用手順 ・ **読む人** 管理者

環境を立ち上げる人と、日々動かす人向けの手順です。**実機の状態・進捗・TODOの正本は[配備台帳](handover.md)** で、この一覧はそこへ至る道順です。

## 1. 立ち上げる（上から順に）

| 順 | ページ | 何をするか |
| --- | --- | --- |
| 1 | [初回セットアップの順番](bootstrap.md) | 何もない状態から。残っている手作業の一覧もここ |
| 2 | [秘密値の管理](secrets.md) | SOPS と age。以降の全手順が前提にする |
| 3 | [Terraformの実行](terraform.md) | プール・ロール・基盤VMを作る |
| 4 | [NetBoxの使い方](netbox.md) | 配備先の台帳。IPの採番元 |
| 5 | [認証基盤（identity・Authentik）](identity.md) | 共通ログイン。他の全サービスが繋がる先 |
| 6 | [クラウドAPIの構築](cloud.md) | shakecloud API・ポータル・管理DB |
| 7 | [Kubernetes クラスタ](kubernetes.md) | AWX・DB提供・関数提供の土台 |
| 8 | [サービスの置き場所とクラウドVMでの作り方](services.md) | サービスVMを作って中身を配る |

## 2. 道具

| ページ | 何が分かるか |
| --- | --- |
| [shakecloud CLI](cli.md) | コマンドからの操作 |
| [shakecloud Terraform Provider](terraform-provider.md) | Terraformからの操作 |
| [AWXの使い方](awx.md) | Playbookをブラウザ・APIから実行する |
| [Flux にアプリを足す](flux-apps.md) | クラスタ側の配備 |

## 3. サービスごとの管理

| ページ | 何が分かるか |
| --- | --- |
| [Nextcloudと追加アプリ](nextcloud.md) | アプリの追加・配備 |
| [Nextcloudのアクセス権限](nextcloud-permissions.md) | 共有ライブラリの見え方 |
| [Vaultwardenの管理](vaultwarden.md) | 保管庫・SSO・招待 |
| [メール設定（SMTP）](smtp.md) | 招待・復旧メールの送信 |
| [Windows 11 Pro のVMを作る](windows.md) | ポータルからのISOインストール |

## 4. ネットワークとストレージ

| ページ | 何が分かるか |
| --- | --- |
| [net-01（subnet router）](net.md) | 宅外から管理LANへの復旧経路 |
| [VLAN 分離への切替](vlan.md) | 管理面と利用者VMを分ける |
| [Garage（S3互換ストレージ）](garage.md) | バケットとキー |
| [ディスク増設](disk.md) | 容量を足す |

## 5. 電源・復旧・引き継ぎ

| ページ | 何が分かるか |
| --- | --- |
| [電源とUPS](power.md) | 安全な停止順と復電 |
| [配備台帳](handover.md) | **実機の状態・決定・TODOの正本** |

## 関連

- 設計の意図と根拠: [設計の入口](../architecture/index.md)
- これから作るもの: [開発計画の入口](../development/index.md)
- URLとアドレス: [接続先一覧](../reference/urls.md)
