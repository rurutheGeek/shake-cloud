---
title: 配備台帳（実機の状態とTODO）
updated: 2026-10-22
section: 運用手順
audience: 管理者
tags:
  - ops
  - handover
---

# 配備台帳（実機の状態とTODO）

> **更新日** 2026-10-22 ・ **区分** 運用手順 ・ **読む人** 管理者

**この文書は「いま」だけを書きます。** 1行は1〜2文。状態が変わったら書き足さずに上書きし、済んだ作業の行は消します。

| 書きたいもの | 書く場所 |
| --- | --- |
| 経緯（いつ・何をしたか） | コミットメッセージ。`git log -p -- <ファイル>` で追える |
| 残っている作業・仕様・進捗 | [GitHub Issues](https://github.com/rurutheGeek/shake-cloud/issues) |
| 決めたこと | [決定ログ](../architecture/decisions.md) |
| はまったこと | [確認と、はまりどころ](verify.md) |
| 手順・設定値 | そのサービスの運用ページ |
| ログイン情報と秘密値の置き場所 | [秘密値の管理 §7](secrets.md#where) |

## 1. 状態

- **クラウド**: VM・S3・database・function の4機能が API・Provider・CLI・ポータルで揃っている。Kubernetes は k8s-cp-01 の1台で常時動かす。
- **基盤**: core-01（Authentik・NetBox・HTTPS の入口）、cloud-01（クラウドAPI・Garage）、apps-01・media-01（アプリ）。監視は K11 の外の tarakoserver。
- **ネットワーク**: ルータは Flint 3。区画（サーバー・DMZ・個人端末・ネット専用・AdGuard なし・ゲーム）は実機で分離済み。公開サイトは DMZ の shakeserver。守りの全体は[セキュリティ](../architecture/security.md)。

## 2. いまの実機

Proxmox ホストは `apextox`（`https://192.168.10.10:8006`、PVE 9.2.2）。IP の帯は `platform/terraform/network.yaml`、ゲストのタイムゾーンは `Asia/Tokyo`。

| VMID | 名前 | IP | 役割 | 状態 |
| --- | --- | --- | --- | --- |
| 100 | game-01 | 192.168.10.127 | ゲーム（Bazzite、GPU パススルー）。クラウドVMとして引き取り済み | 稼働 |
| 140 | cloud-01 | 192.168.10.205 | クラウドAPI・管理DB・Garage | 稼働 |
| 150 | core-01 | 192.168.10.200 | Authentik・NetBox・入口の Caddy・ドキュメント | 稼働 |
| 200 / 210 / 211 | k8s-cp-01 / k8s-worker-01 / k8s-worker-02 | .207 / .209 / .208 | Kubernetes（AWX・CNPG・Knative・poke-translate の function） | k8s-cp-01 の1台で常時稼働（7GiB）。worker-01・02 は停止した予備（[Kubernetes](kubernetes.md)） |
| 400 / 401 | dev-01 / dev-02 | .202 / .203 | 開発VM（クラウドVM）。dev-02 が自動化の実行ホスト | 稼働 |
| 900 | probe-01 | 192.168.10.201 | 検証用 | 使うときだけ起動 |
| 5000 | win-01 | 192.168.10.100 | Windows 11（クラウドVM） | 停止 |
| — | android-01 | 192.168.10.104 | Waydroid（Eufy の解析用、クラウドVM） | 停止。解析のときだけ起動（[android-01](android-01.md)） |
| 5001 | media-01 | 192.168.10.101 | Nextcloud・Kavita・Navidrome・FreshRSS・MeTube・LocalSend・UrBackup・Forgejo | 稼働 |
| 5005 | apps-01 | 192.168.10.105 | Homarr・Vaultwarden・LibreSpeed・mail-view・CUPS・ポケモン翻訳・pkdb・UBSLEEPY・Home Assistant・eufy | 稼働 |
| 5997 | shakecloud-volumes | — | デタッチしたボリュームの置き場。起動しない | 停止 |

| 物理機 | IP | 役割 |
| --- | --- | --- |
| Flint 3（GL-BE9300） | 192.168.10.1 | ルータ・区画・AdGuard Home・Tailscale（[Flint 3](flint3.md)） |
| tarakoserver（Pi 4） | 192.168.10.11 | 監視・ログ・ネットワーク図・UPS（[監視](monitoring.md)） |
| shakeserver（Pi 5） | 192.168.30.12（DMZ） | 公開サイト・Minecraft（[公開サイト](web.md)） |
| negitoroserver（Pi Zero 2 W、家の外） | tailnet のみ | 公開の中継・外からの監視 |

## 3. 残っている作業

**[GitHub Issues](https://github.com/rurutheGeek/shake-cloud/issues) が正本です。** 写しは毎日 Forgejo の `archive/shake-cloud-issues` へ取ります。

- 家での物理作業か人の判断が要るもの: [ラベル `人の手`](https://github.com/rurutheGeek/shake-cloud/issues?q=is%3Aopen+label%3A%E4%BA%BA%E3%81%AE%E6%89%8B)
- 守りの穴: [ラベル `セキュリティ`](https://github.com/rurutheGeek/shake-cloud/issues?q=is%3Aopen+label%3A%E3%82%BB%E3%82%AD%E3%83%A5%E3%83%AA%E3%83%86%E3%82%A3)

## 4. 未決事項

| 項目 | いま | 決める材料 |
| --- | --- | --- |
| 無料ドメインの継続性 | DigitalPlat の更新・取り消しの規則が分からない | 取り上げられたら名前の付け替え。困るなら有料ドメインへ |
| 端末台帳 | NetBox に Pixel 8a が残り、家族の Galaxy が未登録 | 機種名を確かめて `platform/netbox/devices.yaml` を直す |
| サービスの state 用キー | `services.sops.yaml` は作成済みだが、キーの有効性・権限は未確認 | `tools/tf services/<name> plan` が通るか |
| ボリュームの種類（SSD⇔HDD） | 変える API が無い。win-01 のデータは手で HDD へ移し、管理DBを合わせた | 要るなら API に足す |
| Nextcloud MCP の実データ確認 | 人のアカウントでのタグ編集〜Navidrome 反映などが未確認 | 確認までは動作確認済みと書かない（[A06](https://github.com/rurutheGeek/shake-cloud/issues/192)） |

## 5. 引き継ぐ人のアクセス

アクセス手段は dev-02 の1か所に集まっています。もう1人分を作る方法は[秘密値の管理 §7](secrets.md#where)にあります。
