---
title: 利用ガイドの入口
updated: 2026-09-23
section: 利用ガイド
audience: 利用者
tags:
  - guide
  - usage
---

# 利用ガイドの入口

> **更新日** 2026-09-23 ・ **区分** 利用ガイド ・ **読む人** 利用者

サービスを日常的に使う人向けのページをまとめています。SSH・Docker・設定ファイルの操作は出てきません。すべてのURLは[接続先一覧](../reference/urls.md)にあります。

## はじめに読む

| ページ | 何が分かるか |
| --- | --- |
| [全サービスの使い方](usage.md) | 何をどこで開くか。スマートフォンから使う方法 |
| [共通ログインの使い方](identity.md) | 招待の受け取り、パスキー、パスワードの再設定 |
| [Homarrの使い方](homarr.md) | サービス一覧のハブ画面 |
| [日本語に切り替える](language.md) | 各アプリの表示言語 |

## ファイル・本・音楽

| ページ | 何が分かるか |
| --- | --- |
| [Nextcloudの使い方](nextcloud-guide.md) | ファイル・カレンダー・TODO・スマートフォン連携 |
| [音楽の取り込み・タグ編集](music.md) | 取り込みからNavidromeで聴くまでの流れ |
| [タグ管理（MP3）](tags.md) | タグの直し方と整理 |
| [Nextcloudファイルエージェント（AI用MCP）](nextcloud-agent.md) | AIエージェントから自分のNextcloudを読み書きする |
| [共通RSSタイムライン](rss.md) | FreshRSSの購読を全員で共有する |

## 家電・印刷

| ページ | 何が分かるか |
| --- | --- |
| [Home Assistantと家電の使い方](home-assistant.md) | 家電の操作・自動化・通知 |
| [プリンター](printer.md) | LAN内の端末やNextcloudから印刷する |

## 回線の速度を測る

| ページ | 何が分かるか |
| --- | --- |
| [LibreSpeed（速度テスト）](librespeed.md) | 宅内の回線速度を自前で測る |

## 様子を見る

[Grafana](https://grafana.apextox.dpdns.org) は共通ログインで開けます。**一般の利用者は閲覧のみ**（Viewer）で、サーバーの混み具合・ディスクの空き・UPSの状態などを見られます。設定の変更はできません。アラートの意味と対処は管理者向けの[監視（monitor-01）](../operations/monitoring.md)にあります。

## 自分でVMやストレージを作る

| ページ | 何が分かるか |
| --- | --- |
| [クラウドの使い方](cloud.md) | ポータル・アクセスキー・CLI・TerraformでVM/S3/DB/関数を作る |
| [AIエージェントからクラウドを見る（MCP）](mcp.md) | opencodeからVM・容量・履歴を読み取り専用で調べる |
| [開発VMの使い方](devvm.md) | dev-a・dev-b の起動・停止・接続 |

## 管理側のページ

次のページは利用者が変更する場所ではありません。内容を知りたいときだけ読んでください。

- [Nextcloudのアクセス権限](../operations/nextcloud-permissions.md)
- [共通ログインの管理](../operations/identity.md)
- [配備台帳](../operations/handover.md)
