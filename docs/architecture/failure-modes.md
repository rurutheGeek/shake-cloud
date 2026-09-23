---
title: 障害モードと単一障害点
updated: 2026-09-19
section: 設計
audience: 管理者・開発者
tags:
  - design
  - failure
---

# 障害モードと単一障害点

> **更新日** 2026-09-19 ・ **区分** 設計 ・ **読む人** 管理者・開発者

**何が止まると、何が使えなくなるか。** 停止・再起動の判断と、復旧の順番を決めるための表です。各所に1行ずつ散っていた「これを止めると◯◯も止まる」をここへ集めました。

実機の稼働状況は[配備台帳](../operations/handover.md)、症状ごとの対処は[確認と、はまりどころ](../operations/verify.md)が正本です。

## 1. 単一障害点

**冗長化していません。** 意図的にそうしています（2人の家庭内利用で、冗長化の手間に見合わないため）。ただし**どこが単一点かは把握しておく**必要があります。

| 単一点 | 落ちると | いまの受け止め方 |
| --- | --- | --- |
| **物理ホスト `apextox`** | すべて。VM・クラウド・認証・家電・監視・復旧経路のTailscaleまで全部 | 受け入れている。`net-01` の subnet router も同じホスト上なので、**カバーできるのはVM単位の故障まで** |
| **SSD 1台** | すべてと、復元元 | 別ディスク・別機器へのバックアップが要る。**管理DBの外部コピーは未着手**（[O01](../development/O01-cloud-backup.md)） |
| **ルーター・LAN** | 名前解決と全サービスへの到達 | 受け入れている。LANが死ぬと手元からも入れない |
| **Garage（storage-s3、単一ノード）** | S3バケットとオブジェクト | **stateとバックアップの唯一の保管先にしない。** Terraform state は外部のS3互換に置く |
| **Cloudflare（DNS）** | 名前解決と、証明書のDNS-01更新 | 外部依存。既存証明書は期限まで有効なので即死はしない |
| **ドメイン `apextox.dpdns.org`** | 全サービスの名前 | 無料ドメインの継続性は未確認。取り上げられたら名前の付け替え（[配備台帳 §6](../operations/handover.md)） |
| **外部SMTPリレー** | 招待メールと、パスワード復旧メール | 新規招待と復旧が止まる。既存ログインは影響なし |

## 2. VMごとの停止の影響

| 止まるVM | 使えなくなるもの | 生き残るもの |
| --- | --- | --- |
| `identity` | **ブラウザからの全ログイン。** Homarr・Nextcloud・Kavita・Grafana・ポータル・Forward Authのアプリ | **アクセスキーを使うTerraform・CLIは動く**（認証を分けているため）。Vaultwardenはマスターパスワードで開ける |
| `cloud-01` | VMの作成・電源操作・削除、ポータル、容量と上限の確認 | **既存のVMは動き続ける。** Proxmoxの画面からは操作できる |
| `services-01` | NetBox（台帳）・このドキュメントサイト・Homarr・Vaultwarden・**Home Assistant（家電）**・CUPS（印刷）・Eufy中継 | 他VMのサービス。**ただしAnsibleのNetBox動的インベントリが引けなくなるので配備が止まる** |
| `media-01` | Nextcloud・**Calendar・Tasks**・Kavita・Navidrome・FreshRSS・MeTube・LocalSend受信機 | 原本ファイルはディスク上に残る |
| `storage-s3` | S3バケット、そこを使うバックアップ | 他は影響なし |
| `monitor-01` | 監視・アラート・Grafana。**監視の停止自体は誰も検知しない** | 他は影響なし |
| Kubernetes（cp・worker） | **クラウドの database と function の2機能**、AWX | VM・S3の2機能は動く。既に作ったDBは止まる |
| `game1` | ゲーム、RomM、将来のローカルAIとBot | 他は影響なし |
| `net-01` | 宅外からの復旧経路 | LAN内からは全部使える |
| `dev-a` / `dev-b` | 配備の実行環境（dev-bが自動化の実行ホスト） | 稼働中のサービスは影響なし |

**再起動の前に確認すること**: `services-01` を再起動すると家電の操作と印刷が同時に止まります。`media-01` を止めるとカレンダーと同期も止まります。どちらも他の人が使っている時間帯を避けてください。

## 3. 止まり方の種類

| 種類 | 例 | 気づき方 |
| --- | --- | --- |
| VMが落ちる | OOM、ゲストのpanic、電源操作の誤り | 監視のtargetが落ちる。Homarrのタイルが赤くなる |
| コンテナが落ちる | 設定ミス、イメージ更新、ディスク満杯 | 入口のCaddyが502を返す |
| **入口だけ落ちる** | 証明書の更新失敗、Cloudflareトークンの権限不足 | ブラウザが証明書エラー。中身は動いている |
| **黙って成功する** | 動的インベントリで対象0件、パイプで終了コードが隠れる | 気づけない。[はまりどころ](../operations/verify.md)に既知のものを列挙している |
| 認証だけ落ちる | Authentikの停止、Forward Authの設定崩れ | ログイン画面が出ない、404、空の200 |
| ネットワークが被る | DHCPの配布範囲とクラウドIPレンジの重複（2026-09-14に解消） | ARPは解決するのにSSHもHTTPも応答しない |

**「入口だけ落ちる」と「黙って成功する」が最も厄介**です。前者は中身が正常なので監視が通り、後者は終了コードが0になります。配備の確認は必ず `PLAY RECAP` と実際の応答まで見てください。

## 4. 停電

UPSが付いています。手順は[電源とUPS](../operations/power.md)が正本です。

| 段階 | いまの状態 |
| --- | --- |
| 停電の検知 | NUT経由でPrometheusが取得。Grafanaに表示 |
| 低電池での自動シャットダウン | **未整備**（[M01](../development/M01-monitoring.md)の残件） |
| 復電後の起動 | 停電時に動いていたゲストを起動時に戻す（`onboot` は常時基盤だけ。Kubernetesは状態復元に任せる） |

## 5. 復旧の順番

上から順です。**下のものは上のものに依存します。**

1. **物理ホスト** — Proxmoxが上がること。画面は `https://pve.apextox.dpdns.org:8006`
2. **`services-01`** — NetBoxが要る。これが無いとAnsibleの動的インベントリが引けず、他の配備が進まない
3. **`identity`** — ブラウザからのログインが戻る
4. **`cloud-01`** — VMの操作が戻る。**アクセスキーは identity に依存しないので、2と3を待たずにTerraformは動かせる**
5. **`storage-s3`・Kubernetes** — S3・database・function
6. **サービスVM**（`media-01`・`monitor-01`・`game1`・`net-01`） — 利用者向けの機能

**Terraform state は外部に置いてあります。** ホストが丸ごと失われても宣言と state は残るので、作り直しは宣言から始められます。ただし**原本・アプリのDB・秘密値は state に入っていません**。復元手順は[O03](../development/O03-restore.md)で整備中です。

## 6. まだ確かめていないこと

| 項目 | 状態 |
| --- | --- |
| アプリ横断の隔離復元 | ツールはあるが合格していない（[O03](../development/O03-restore.md)） |
| 管理DBの外部コピー | ローカルに14世代。外部コピーは未着手（[O01](../development/O01-cloud-backup.md)） |
| CloudNativePGのバックアップ | 未整備（[O02](../development/O02-cnpg-backup.md)） |
| Home Assistantの復元試験 | 未完（[H01](../development/H01-home-assistant.md)） |
| 低電池での自動シャットダウン | 未整備（[M01](../development/M01-monitoring.md)） |
| 原本ライブラリのバックアップ | 状態のバックアップに含まれない。別途必要 |

## 関連

- [信頼境界とセキュリティ方針](security.md) — 何を信頼していないか
- [配備台帳](../operations/handover.md) — 実機の稼働状況
- [確認と、はまりどころ](../operations/verify.md) — 症状ごとの対処
- [電源とUPS](../operations/power.md) — 停止順と復電
