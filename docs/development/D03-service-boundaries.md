---
title: D03 サービス配置とIaC所有境界の更新
updated: 2026-09-12
section: 開発計画
audience: 開発者
tags:
  - plan
  - placement
---

# D03 サービス配置とIaC所有境界の更新

> **更新日** 2026-09-12 ・ **区分** 開発計画 ・ **読む人** 開発者

種別: **資料のみ更新**。状態: **資料更新・文書検証完了（実機作業の完了とは別）**。

[開発計画一覧](index.md)へ戻る。番号は実施順を表さない。

## 目的・現状の根拠

VMの所有者とVM内部のアプリ担当を分け、並列作業で二重管理しない手順にする。

[サービスの作り方](../operations/services.md)と[IaCの所有境界](../architecture/iac.md)が既存の案内。[初回セットアップ](../operations/bootstrap.md)ではNetBoxに依存しない `05-seed` がservices-01を作る。[クラウド運用](../operations/cloud.md)にgame1の引き取り記録がある。

## 変更範囲

services-01は `05-seed`、game1は既存クラウド管理を維持する。新規media-01は `platform/terraform/services/media/` の独立state、アプリは `stacks/` で管理する。同じVMに載るW03〜W06でVMを個別に宣言しない。RomM（W07）はgame1側の既存管理に従う。Composeのプロジェクト名・データ・ポートを分離し、同一state適用と共有DNS／TLS変更は担当間で調整する。Kubernetesを選ぶ理由を既存のOperator・関数機構の利用に絞る。

配備先: 文書は本リポジトリの `docs/`。公開サイトへの反映は文書検証後の既存運用に従い、この計画整備では公開しない。

## 依存関係・並列作業

開始: なし。配備・切替: 文書のみなのでなし。[I05](I05-service-state.md)の共有state方式は別計画とし、その完了を本文更新の待ち条件にしない。

共有変更: `docs/operations/services.md`、`docs/architecture/iac.md`、Terraformサービス案内は I02・I05・D02 と編集範囲を調整する。

## 検証・完了条件

既存VMを新stateへ重複宣言する案内がない。開発担当が配備先・アプリ正本・VM所有者を特定できる。計画用READMEだけで配備が起動しないこと、文書・公開対象検証を確認する。

共通の確認は `python3 -m mkdocs build --strict`、内部リンクの実在確認、`python3 tools/check-publication.py`。実施していない実機確認を完了根拠へ追加しない。

検証記録（2026-09-12）: 厳格ビルド、ローカルリンク・ID対応、公開対象チェック、差分の空白検査が通過。実機確認はこの資料更新では実施していない。
