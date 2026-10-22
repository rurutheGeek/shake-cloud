---
title: 構成の移り変わり
updated: 2026-10-22
section: 設計
audience: 全員
tags:
  - design
  - history
---

# 構成の移り変わり

> **更新日** 2026-10-22 ・ **区分** 設計 ・ **読む人** 全員

**大きな改修と構成変更だけを1行ずつ並べます。** 細かい経緯はコミットメッセージ（`git log`）、決めた理由は[決定ログ](decisions.md)、いまの姿は[全体像](overview.md)にあります。足すのは「構成図が変わるほどの変更」だけです。

## 2026-09 土台とクラウド

| 日付 | できごと |
| --- | --- |
| 09-08 | リポジトリを始める。秘密値は SOPS + age、CI で yamllint |
| 09-09 | Terraform で Proxmox の権限境界（00-bootstrap）と基盤VMを作る。最初の1台 services-01 に NetBox |
| 09-10〜11 | 自作クラウド shakecloud（VM・ボリューム・セキュリティグループ・コンソール）、CLI、Terraform Provider、Garage（S3） |
| 09-12 | Kubernetes（kubeadm・Cilium・Flux）と AWX。クラウドに database（CloudNativePG）と function（Knative）が加わり4機能が揃う。Authentik に招待・パスキー・メール復旧 |
| 09-13 | 監視（Prometheus・Grafana）を始める |
| 09-20 | 市販ルータから K11 上の OpenWrt VM（router-01）へ切り替える。DNS は AdGuard Home |
| 09-23 | 6TB HDD を共有し、重要VMの週次バックアップを始める |

## 2026-10 再編と区画

| 日付 | できごと |
| --- | --- |
| 10-02 | Ansible の対象を NetBox の動的インベントリ1本にし、クラウドVMを台帳へ自動登録する |
| 10-03 | 配置の再編。Authentik・NetBox・HTTPS の入口を core-01 へ、Garage を cloud-01 へ、アプリを apps-01 へ集め、identity・storage-s3 などを廃止。証明書と DNS トークンを入口1台に |
| 10-04 | 開発VMをクラウドVMとして引き取る（dev-01・dev-02）。HDD をバックアップ領域とクラウド領域に分ける |
| 10-05 | 旧ホストからポケモン系 DB と Discord Bot を apps-01 へ。公開サイトを web-01 へ移す |
| 10-14 | ルータを物理機 Flint 3 へ。区画（サーバー・個人端末・ネット専用・DMZ）を実機で分ける。監視を K11 の外の tarakoserver（Pi 4）へ移し monitor-01 を廃止。Raspberry Pi を Ansible で管理する |
| 10-15 | 通知を Discord に一本化。UPS を tarakoserver につなぎ替え。Forgejo（リポジトリの保管庫） |
| 10-16 | 公開サイトを DMZ の shakeserver（Pi 5）へ移し、web-01 を廃止 |
| 10-17 | ゲームの区画と AdGuard を通さない無線を足す。公開サイトを CI のイメージ・Podman で動かす |
| 10-18 | ポケモンDB に AI 用の MCP サーバ |
| 10-22 | 守りを足す（基盤VMのファイアウォール、中継の ufw、Cloudflare の WAF、イメージの脆弱性の毎日の点検、おとり）。作業の管理を GitHub Issues へ移し、Forgejo へ写す。Kubernetes を1台構成で常時稼働に |
