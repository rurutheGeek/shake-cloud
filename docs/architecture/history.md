---
title: 構成の移り変わり
updated: 2026-10-23
section: 設計
audience: 全員
tags:
  - design
  - history
---

# 構成の移り変わり

> **更新日** 2026-10-23 ・ **区分** 設計 ・ **読む人** 全員

**大きな改修と構成変更だけを1行ずつ並べます。** 細かい経緯はコミットメッセージ（`git log`）、決めた理由は[決定ログ](decisions.md)、いまの姿は[全体像](overview.md)にあります。1行に書くのは「機械を足す・外す」「動かす場所を移す」「入口・区画を変える」のどれかだけです。機能の追加は書きません。

## 2022〜2026-04 Discord Bot と Raspberry Pi

始まりは Discord Bot の [UBSLEEPY](https://github.com/rurutheGeek/UBSLEEPY) です。インフラ用のリポジトリはまだ無く、Bot のリポジトリの GitHub Actions が Pi へ配っていました。

| 日付 | できごと |
| --- | --- |
| 2022-10 ごろ | Raspberry Pi 4 を買う（のちの tarakoserver） |
| 2023-03 ごろ | Replit で UBSLEEPY を作り始める（Git に記録が無く、作った本人の記憶による） |
| 2023-08-16 | UBSLEEPY を GitHub へ移し、Pi 4 のセルフホストランナーで動かす |
| 2024-05 | Raspberry Pi 5 を買う（のちの shakeserver） |
| 2026-03-11 | UPS を買う |
| 2026-03-24 | Raspberry Pi Zero 2 W を買う（のちの negitoroserver） |

## 2026-05〜09 shake-infra

インフラを [rurutheGeek/shake-infra](https://github.com/rurutheGeek/shake-infra) に分け、Pi を Tailscale でつないで Ansible と Terraform で管理しました。ルータは中古の NEC Aterm WG1200HP4 です。

| 日付 | できごと |
| --- | --- |
| 2026-05-17 | shake-infra を始める。Pi 5 に DB・Minecraft・公開サイト・Bot、Pi 4 に監視、家の外の Pi Zero 2 W を公開の中継に |
| 2026-05-21 | Pi が落ちたら Cloudflare Workers のメンテナンス画面へ切り替える |
| 2026-06-10 | 公開サイトを3つのサブドメイン（shake・pkhack・ayahuya）に分ける |

## 2026-09〜 shake-cloud

| 日付 | できごと |
| --- | --- |
| 2026-09-07 | ミニPC K11 を買う。翌日 shake-cloud を始め、Proxmox VE を入れる |
| 2026-09-11 | 自作クラウド shakecloud が動く（VM・S3。09-12 に database・function） |
| 2026-09-12 | Kubernetes（AWX・CloudNativePG・Knative） |
| 2026-09-20 | ルータを Aterm から K11 上の OpenWrt VM（router-01）へ |
| 2026-09-22 | 6TB HDD をつなぎ、共有とバックアップの置き場にする |
| 2026-10-03 | 配置の再編。ログイン・台帳・HTTPS の入口を core-01、S3 を cloud-01、アプリを apps-01 に集め、VM を減らす |
| 2026-10-05 | Bot とポケモン系 DB を Pi 5 から apps-01 へ、公開サイトを web-01（クラウドVM）へ |
| 2026-10-12 | Flint 3（GL-BE9300）を買う |
| 2026-10-14 | ルータを Flint 3 へ替え、区画（サーバー・個人端末・ネット専用・DMZ）を分ける。Aterm を外す。監視を K11 から Pi 4 へ移す |
| 2026-10-15 | UPS を Pi 4 につなぎ替える |
| 2026-10-16 | 公開サイトを DMZ の Pi 5 へ移し、web-01 を消す |
| 2026-10-17 | ゲームの区画と AdGuard を通さない無線を足す |
| 2026-10-22 | 基盤VM・中継・Cloudflare に守りを足す。Kubernetes を1台で常時動かす |
| 2026-10-23 | 旧ルータ router-01 を消す |
