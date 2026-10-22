---
title: 開発の進め方
updated: 2026-10-22
section: 開発計画
audience: 開発者
tags:
  - plan
---

# 開発の進め方

> **更新日** 2026-10-22 ・ **区分** 開発計画 ・ **読む人** 開発者

**作業は [GitHub Issues](https://github.com/rurutheGeek/shake-cloud/issues) で管理します。** 仕様・残りの作業・進捗・議論はすべて Issue に書き、このサイトには書きません。写しは毎日 Forgejo の `archive/shake-cloud-issues` へ取ります。

作業環境は dev-01／dev-02 です。接続のしかたは[開発参加ガイド](../onboarding.md)にあります。

## Issue の書き方

- 1つの Issue は、独立して着手・完了できる単位にする。同じ VM に載るものでも、別々に終われるなら分ける。
- ラベルは記号1つ（W Web・メディア／A AI／G ゲーム／H 家電／N ネットワーク／I 基盤／M 監視／O 復旧・運用／D 資料）と、必要なら `セキュリティ`・`人の手`（家での物理作業か人の判断が要る）。
- 本文には「目的」「変更する範囲」「終わりの条件」を書く。進んだらコメントで足し、本文の「残り」を上書きする。
- 調べて前提が確定したら、それを待っていた Issue にもコメントする（[ドキュメントの書き方 §3](../contributing-docs.md#3-前提が確定したら待っている-issue-まで直す)）。
- 直すコミットや PR に `Closes #番号` を書いて閉じる。実機に関わるなら[配備台帳](../operations/handover.md)も直す。
- 2026-10-22 までの計画書（W01〜D08 の作業ID）は、各 Issue の本文からその時点の版へリンクしてある。完了・見送りのもの（W10・N06・I02・I03・D01・D03〜D05・H03）は Issue を作っていない。

## 共有するものの調整

| 共有する対象 | 決まり |
| --- | --- |
| 同じVM | Compose のプロジェクト名・保存先・ポートを分ける。アプリだけの更新を基本とし、VM の再起動は使っている人へ影響を確かめる |
| GPU、大量の走査・取り込み・ビルド | 同時に最大の負荷をかけない（[#195](https://github.com/rurutheGeek/shake-cloud/issues/195)） |
| Terraform の state | 同じ state への適用は1人ずつ。新しい state に同じVMを重ねて宣言しない |
| DNS・共通の TLS・SSO | 必要な名前・ポート・認証設定の差分を用意し、共通ファイル（`dns.yaml`・`stacks/identity/configure.py`）へまとめる |
| 秘密値・実データ・state | Git の本文に入れない（[秘密値の管理](../operations/secrets.md)） |

## コードの入口

- サービスのコードと設定は `stacks/<name>/`。各 README が配備先と関係する Issue を示す。
- サービスVMの宣言は `platform/terraform/services/<name>/`。置き場所の決め方は[サービスの置き場所](../operations/services.md)と[IaCの所有境界](../architecture/iac.md)。
