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

**大きな改修と構成変更だけを1行ずつ並べます。** 細かい経緯はコミットメッセージ（`git log`）、決めた理由は[決定ログ](decisions.md)、いまの姿は[全体像](overview.md)にあります。足すのは「構成図が変わるほどの変更」だけです。

## 2026-05〜09 shake-infra（Raspberry Pi の時代）

前身は別リポジトリ [rurutheGeek/shake-infra](https://github.com/rurutheGeek/shake-infra) です。Raspberry Pi 数台を Tailscale でつなぎ、Ansible と Terraform で管理していました。

| 日付 | できごと |
| --- | --- |
| 05-17 | shake-infra を始める。Pi 5（shakeserver）に PostgreSQL・Minecraft・公開サイト・Alexa スキル・Discord Bot、Pi 4（tarakoserver）に監視、家の外の Pi Zero 2 W（negitoroserver）を公開の中継に |
| 05-20 | GitHub Actions のセルフホストランナー（tarakoserver）で自動配備。通知は Discord |
| 05-21 | ノードが落ちたら Cloudflare Workers のメンテナンス画面へ切り替える仕組み |
| 05-28〜06-01 | Ansible Vault で秘密値、CI に ansible-lint・Trivy・統合テスト、Prometheus・Grafana・Loki・Alertmanager |
| 06-10〜12 | 公開サイトを3つのサブドメイン（shake・pkhack・ayahuya）に分ける |
| 10-04〜05 | Discord Bot と公開サイトを shake-cloud へ移し、shake-infra は中継だけになる |

## 2026-09 土台とクラウド

| 日付 | できごと |
| --- | --- |
| 09-08 | shake-cloud を始める。ミニPC K11 に Proxmox VE。秘密値は SOPS + age、CI で yamllint |
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
| 10-23 | 旧ルータ router-01（OpenWrt）を消す |
