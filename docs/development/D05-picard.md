---
title: D05 Picardのメディア統合
updated: 2026-09-13
section: 開発計画
audience: 開発者
tags:
  - plan
  - music
---

# D05 Picardのメディア統合

> **更新日** 2026-09-13 ・ **区分** 開発計画 ・ **読む人** 開発者

種別: **資料のみ更新**。状態: **見送り（2026-09-13。タグ編集はNextcloudの `shake_tags` へ統合し、サーバーのPicardは撤去。PC版を使う場合の手順だけ[音楽手順](../services/music.md)に残す）**。

[開発計画一覧](index.md)へ戻る。番号は実施順を表しません。

## 目的・現状の根拠

MusicBrainz Picardを**メディアの音楽導線**（MeTubeの取込 → Nextcloudの共有music → Picardで照合・確認後保存 → Navidromeの表示）に位置づけ、利用者PCとmedia-01のどちらでGUIを使う場合も同じ原本・作業コピー・保存手順で扱えるようにします。**PicardはゲームVMの同居物ではありません。**

[音楽の取り込み・タグ編集](../services/music.md)にPicardのLookup／Scan、作業コピー、確認後Save、同期確認、全自動化の条件が既にあります。

## 変更範囲

既存の音楽案内を正本にし、Picardの配置をmedia-01側へ揃える。MeTubeが保存した音源、Nextcloudの共有music、Navidromeへの反映という3つの接点を明記する。原本をコピーして1アルバムで確認→タグ保存→共有musicへ戻す→Navidromeでの表示・再生確認の導線を整理する。BCSTM原本と再生成対象 `music/Converted/` を直接編集しない注意、作業競合時の保留、元ファイルへの復元を記載する。

Picard本体のmedia-01への導入（Web GUIコンテナ）は[W06](W06-music-tools.md)で行います。無人ジョブ・自動保存の実装は本IDに含めません。

配備先: 文書は本リポジトリの `docs/`。公開サイトへの反映は文書検証後の既存運用に従い、この計画整備では公開しない。

## 依存関係・並列作業

開始: なし。配備・切替: 資料のみなのでなし。[W05](W05-navidrome.md)・[W06](W06-music-tools.md)で保存先が変わったら該当箇所を追記する。

共有変更: `docs/services/music.md` は W05・W06 と担当段落を調整する。実ファイルの照合作業を行う場合は同じ音楽を取り込み・変換・タグ編集で同時更新しない。

## 検証・完了条件

元ファイル・作業コピー・生成物の違い、反映先、失敗時の戻し方を資料から辿れる。Picardの配置がmedia側（media-01または利用者PC）として書かれ、game1の同居物として書かれていない。導入済みと誤記しない。文書・リンク・公開対象検証の通過で完了する。

共通の確認は `python3 -m mkdocs build --strict`、内部リンクの実在確認、`python3 tools/check-publication.py`。実施していない実機確認を完了根拠へ追加しない。
