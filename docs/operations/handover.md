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
| 作業ごとの仕様・進捗 | [開発計画](../development/index.md)の各計画書 |
| 決めたこと | [決定ログ](../architecture/decisions.md) |
| はまったこと | [確認と、はまりどころ](verify.md) |
| 手順・設定値 | そのサービスの運用ページ |
| ログイン情報と秘密値の置き場所 | [秘密値の管理 §7](secrets.md#where) |

## 1. 状態

- **クラウド**: VM・S3・database・function の4機能が API・Provider・CLI・ポータルで揃っている。Kubernetes のノードは必要なときだけ起動する。
- **基盤**: core-01（Authentik・NetBox・HTTPS の入口）、cloud-01（クラウドAPI・Garage）、apps-01・media-01（アプリ）。監視は K11 の外の tarakoserver。
- **ネットワーク**: ルータは Flint 3。区画（サーバー・DMZ・個人端末・ネット専用・AdGuard なし・ゲーム）は実機で分離済み。公開サイトは DMZ の shakeserver。守りの全体は[セキュリティ](../architecture/security.md)。

## 2. いまの実機

Proxmox ホストは `apextox`（`https://192.168.10.10:8006`、PVE 9.2.2）。IP の帯は `platform/terraform/network.yaml`、ゲストのタイムゾーンは `Asia/Tokyo`。

| VMID | 名前 | IP | 役割 | 状態 |
| --- | --- | --- | --- | --- |
| 100 | game-01 | 192.168.10.127 | ゲーム（Bazzite、GPU パススルー）。クラウドVMとして引き取り済み | 稼働 |
| 101 | router-01 | — | 旧ルータ（OpenWrt） | 停止・自動起動なし。2026-10-28 以降に削除 |
| 140 | cloud-01 | 192.168.10.205 | クラウドAPI・管理DB・Garage | 稼働 |
| 150 | core-01 | 192.168.10.200 | Authentik・NetBox・入口の Caddy・ドキュメント | 稼働 |
| 200 / 210 / 211 | k8s-cp-01 / k8s-worker-01 / k8s-worker-02 | .207 / .209 / .208 | Kubernetes（AWX・CNPG・Knative） | 使うときだけ起動（`tools/k8s up`、[Kubernetes](kubernetes.md)） |
| 400 / 401 | dev-01 / dev-02 | .202 / .203 | 開発VM（クラウドVM）。dev-02 が自動化の実行ホスト | 稼働 |
| 900 | probe-01 | 192.168.10.201 | 検証用 | 使うときだけ起動 |
| 5000 | win-01 | 192.168.10.100 | Windows 11（クラウドVM） | 停止 |
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

👤 は家での物理作業か、人の判断が要るもの。

| 作業 | いま | 詳細 |
| --- | --- | --- |
| K11 の `vmbr0` を VLAN 対応に 👤 | DMZ にクラウドVMを置くときだけ要る。いまは困っていない | [区画](vlan.md#dmz-の作り方)・[N03](../development/N03-vlan.md) |
| DMZ からの侵入の検査・外からのポートスキャン | 未実施 | [セキュリティ §5](../architecture/security.md#5-残っている穴) |
| Proxmox の管理画面・SSH を送信元で絞る | 未実施。個人端末のどれからでも届く | [セキュリティ §5](../architecture/security.md#5-残っている穴) |
| NetBox の接続先を HTTPS にして `:8000` を閉じる | 未着手。`netbox.sops.yaml`・`netbox-inventory.sops.yaml`・`cloudapi.sops.yaml` の URL を変える | [NetBox](netbox.md) |
| Flint 3 の残り 👤 | TL-SG605 の先の割当、UPS の配線（Flint 3・tarakoserver を電池側へ）、SwitchBot ハブを jumpluff へ、非常口の WireGuard、K11 の `/root/tether-*.sh` の削除 | [Flint 3](flint3.md) |
| 既存環境からのメディア移行 | Nextcloud・Kavita・Navidrome は配備済みでデータ移行が未了 | [W03〜W06](../development/index.md) |
| 外部バックアップ | 管理DB・CNPG・端末バックアップの別機器へのコピーと、復元の合格が未了。Garage は単一ノードなので唯一の控えにしない | [O01〜O03](../development/index.md)・[バックアップ](backup.md) |
| 端末バックアップの実測 | Windows の初回バックアップと復元、Galaxy の WebUSB バックアップの完走が未確認 | [W08](../development/W08-client-backup.md) |
| Eufy S4 のライブ映像 | 20 秒ほどで切れる。連続性が未解決 | [H05](../development/H05-eufy-leo-rtc.md) |
| Home Assistant のバックアップと復元試験 | 未了 | [H01](../development/H01-home-assistant.md) |
| Forgejo | ブラウザーでのログイン確認、外形監視と Homarr のタイルの配備、別機器へのバックアップ | [Forgejo](../services/forgejo.md) |
| ポケモンDBの MCP | `admins` 以外のアプリパスワードが拒まれることの確認。OAuth で使う別クライアントの戻り先の追加 | [pkdb](pkdb.md) |
| 読み取り専用のアクセスキー | ReadOnly キーで書き込みが拒まれることの実機確認（API・MCP） | [クラウドAPI本体](cloud-api.md)・[MCP](mcp.md) |
| Nextcloud の自作アプリ | 証明書は発行済み。App Store への登録が未確認 | [Nextcloud](nextcloud.md) |
| 出たままの警告 | apps-01 の `eufy-camera-watch`（HTTP 404 で一時停止中）、tarakoserver の `smartmontools`（USB の HDD が見えない） | [M02](../development/M02-touch-panel.md) |
| `10-platform` の未適用差分 | 使用中のVMの `initialization`、`access.yaml` の SSH 鍵、説明文。使用中のVMに触れるので全体 apply はしていない | [Terraform](terraform.md) |
| android-01 の環境スクリプト | VM 上にしか無く、作り直すと失われる。Ansible 化が未了 | [android-01](android-01.md) |
| Renovate 👤 | GitHub App を入れるまで PR は作られない。`compose.lock.yaml` の digest は対象外 | `renovate.json` |
| AWX のジョブ | ジョブテンプレート・プロジェクトの整備が未着手 | [I06](../development/I06-awx.md) |

## 4. 未決事項

| 項目 | いま | 決める材料 |
| --- | --- | --- |
| 無料ドメインの継続性 | DigitalPlat の更新・取り消しの規則が分からない | 取り上げられたら名前の付け替え。困るなら有料ドメインへ |
| 端末台帳 | NetBox に Pixel 8a が残り、家族の Galaxy が未登録 | 機種名を確かめて `platform/netbox/devices.yaml` を直す |
| サービスの state 用キー | `services.sops.yaml` は作成済みだが、キーの有効性・権限は未確認 | `tools/tf services/<name> plan` が通るか |
| ボリュームの種類（SSD⇔HDD） | 変える API が無い。win-01 のデータは手で HDD へ移し、管理DBを合わせた | 要るなら API に足す |
| Nextcloud MCP の実データ確認 | 人のアカウントでのタグ編集〜Navidrome 反映などが未確認 | 確認までは動作確認済みと書かない（[A06](../development/A06-nextcloud-mcp.md)） |

## 5. 引き継ぐ人のアクセス

アクセス手段は dev-02 の1か所に集まっています。もう1人分を作る方法は[秘密値の管理 §7](secrets.md#where)にあります。
