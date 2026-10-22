---
title: 機能別VMと並列開発計画
updated: 2026-10-22
section: 開発計画
audience: 開発者
tags:
  - plan
---

# 機能別VMと並列開発計画

> **更新日** 2026-10-22 ・ **区分** 開発計画 ・ **読む人** 開発者

**進捗と残りの作業は [GitHub Issues](https://github.com/rurutheGeek/shake-cloud/issues) が正本です。** ここに並ぶ計画書は、作業ごとの仕様（目的・変更範囲・完了条件）と作業記録です。計画書の中に進捗を書き足さず、Issue へ書きます。

作業環境は dev-01／dev-02 です。[開発参加ガイド](../onboarding.md)から接続し、下のIDから担当する機能を選びます。同じVMへ載せる機能でも、独立して着手・完了できるものは別の計画にしています。

## 作業ID一覧

**W01・A01などの番号は識別用で、優先度や実施順ではありません。** 記号は W（Web・メディア）・A（AI）・G（ゲーム）・H（家電）・N（ネットワーク）・I（基盤）・M（監視）・O（復旧・運用）・D（資料のみ）で、Issue のラベルと同じです。

| 計画 | 配備先・対象 | 進捗 |
| --- | --- | --- |
| [W01 Homarr](W01-homarr.md) | apps-01 | [#178](https://github.com/rurutheGeek/shake-cloud/issues/178) |
| [W02 Vaultwarden](W02-vaultwarden.md) | apps-01 | [#179](https://github.com/rurutheGeek/shake-cloud/issues/179) |
| [W03 Nextcloud・Calendar・Tasks](W03-nextcloud.md) | media-01 | [#180](https://github.com/rurutheGeek/shake-cloud/issues/180) |
| [W04 Kavita](W04-kavita.md) | media-01 | [#181](https://github.com/rurutheGeek/shake-cloud/issues/181) |
| [W05 Navidrome](W05-navidrome.md) | media-01 | [#182](https://github.com/rurutheGeek/shake-cloud/issues/182) |
| [W06 MeTube・音楽変換・タグ編集](W06-music-tools.md) | media-01 | [#183](https://github.com/rurutheGeek/shake-cloud/issues/183) |
| [W07 RomM](W07-romm.md) | game1 | [#184](https://github.com/rurutheGeek/shake-cloud/issues/184) |
| [W08 クライアント端末のバックアップ](W08-client-backup.md) | media-01・Windows PC・Android | [#185](https://github.com/rurutheGeek/shake-cloud/issues/185) |
| [W09 Smart Switchの非公式クライアント（解析）](W09-smartswitch-re.md) | media-01・Galaxy | [#186](https://github.com/rurutheGeek/shake-cloud/issues/186) |
| [W10 Nextcloudの画像OCR検索](W10-ocr-search.md) | media-01 | 完了 |
| [A01 ポケモンDB・WebUI・agent](A01-pokemon-ai.md) | DBは apps-01、他は game1 | [#187](https://github.com/rurutheGeek/shake-cloud/issues/187) |
| [A02 Ollama](A02-ollama.md) | game1 | [#188](https://github.com/rurutheGeek/shake-cloud/issues/188) |
| [A03 汎用RAG](A03-rag.md) | game1 | [#189](https://github.com/rurutheGeek/shake-cloud/issues/189) |
| [A04 Discord Bot](A04-discord-bot.md) | game1 | [#190](https://github.com/rurutheGeek/shake-cloud/issues/190) |
| [A05 OpenHomeの製品・要件調査](A05-openhome.md) | game1候補 | [#191](https://github.com/rurutheGeek/shake-cloud/issues/191) |
| [A06 NextcloudファイルAIエージェント](A06-nextcloud-mcp.md) | media-01 | [#192](https://github.com/rurutheGeek/shake-cloud/issues/192) |
| [G01 Wolf](G01-wolf.md) | game1 | [#193](https://github.com/rurutheGeek/shake-cloud/issues/193) |
| [G02 Azahar・非公開ルーム](G02-azahar.md) | game1 | [#194](https://github.com/rurutheGeek/shake-cloud/issues/194) |
| [G03 ゲームとAIの負荷調整](G03-game-ai-resources.md) | game1 | [#195](https://github.com/rurutheGeek/shake-cloud/issues/195) |
| [H01 Home Assistant Container](H01-home-assistant.md) | apps-01 | [#196](https://github.com/rurutheGeek/shake-cloud/issues/196) |
| [H02 SwitchBot](H02-switchbot.md) | apps-01 | [#197](https://github.com/rurutheGeek/shake-cloud/issues/197) |
| [H03 Echo](H03-echo.md) | apps-01 | 見送り |
| [H04 Eufy](H04-eufy.md) | apps-01 | [#198](https://github.com/rurutheGeek/shake-cloud/issues/198) |
| [H05 Eufy leo_rtc クライアント](H05-eufy-leo-rtc.md) | dev-b | [#199](https://github.com/rurutheGeek/shake-cloud/issues/199) |
| [H05 HAライブ反映の依頼書](H05-ha-live-request.md) | apps-01 | [#199](https://github.com/rurutheGeek/shake-cloud/issues/199)（H05 と同じ） |
| [N01 セルフホストVPN](N01-vpn.md) | apps-01 | [#200](https://github.com/rurutheGeek/shake-cloud/issues/200) |
| [N02 Tailscaleの復旧経路・DNS](N02-tailscale.md) | router-01（旧cloud VM `net-01`）・端末 | [#201](https://github.com/rurutheGeek/shake-cloud/issues/201) |
| [N03 VLAN切替](N03-vlan.md) | 既存ネットワーク | [#202](https://github.com/rurutheGeek/shake-cloud/issues/202) |
| [N04 公開Web入口](N04-public-edge.md) | public-edge候補 | [#203](https://github.com/rurutheGeek/shake-cloud/issues/203) |
| [N05 既存サービスのHTTPS移行完了](N05-https.md) | core-01・接続元 | [#204](https://github.com/rurutheGeek/shake-cloud/issues/204) |
| [N06 ルータ自作（OpenWrt）](N06-router.md) | K11（OpenWrt VM）・既存ルータ | 完了 |
| [I01 容量測定・軽量化](I01-resources.md) | 既存ホスト・VM | [#205](https://github.com/rurutheGeek/shake-cloud/issues/205) |
| [I02 media-01のVM宣言](I02-media-vm.md) | media-01 | 完了 |
| [I03 クラウドVMのAnsible連携](I03-cloud-inventory.md) | 配備用ツール | 完了 |
| [I04 DNS登録](I04-cloud-dns.md) | サービス宣言・DNS | [#206](https://github.com/rurutheGeek/shake-cloud/issues/206) |
| [I05 サービス用state管理](I05-service-state.md) | 既存外部state保存先 | [#207](https://github.com/rurutheGeek/shake-cloud/issues/207) |
| [I06 AWXのジョブ整備](I06-awx.md) | 既存Kubernetes | [#208](https://github.com/rurutheGeek/shake-cloud/issues/208) |
| [I07 クラウドポータルのUI改善](I07-portal-ui.md) | cloud-01 | [#209](https://github.com/rurutheGeek/shake-cloud/issues/209) |
| [M01 監視（Prometheus・Grafana）](M01-monitoring.md) | monitor-01 | [#210](https://github.com/rurutheGeek/shake-cloud/issues/210) |
| [M02 監視のタッチパネル](M02-touch-panel.md) | tarakoserver | [#211](https://github.com/rurutheGeek/shake-cloud/issues/211) |
| [O01 管理DBの外部バックアップ](O01-cloud-backup.md) | cloud-01・既存外部保存先 | [#212](https://github.com/rurutheGeek/shake-cloud/issues/212) |
| [O02 CNPGバックアップ](O02-cnpg-backup.md) | 既存Kubernetes・Garage・外部保存先 | [#213](https://github.com/rurutheGeek/shake-cloud/issues/213) |
| [O03 VM・アプリ状態の復元](O03-restore.md) | 対象VM・隔離復元先 | [#214](https://github.com/rurutheGeek/shake-cloud/issues/214) |
| [D01 オンボーディング](D01-onboarding.md) | docs | 完了 |
| [D02 配置・配分表・構成図](D02-placement.md) | docs | [#215](https://github.com/rurutheGeek/shake-cloud/issues/215) |
| [D03 サービス配置とIaC所有境界](D03-service-boundaries.md) | docs | 完了 |
| [D04 実装状況の訂正](D04-status.md) | docs | 完了 |
| [D05 Picard](D05-picard.md) | docs・media（音楽導線） | 見送り |
| [D06 LocalSend](D06-localsend.md) | docs・media-01 | [#216](https://github.com/rurutheGeek/shake-cloud/issues/216) |
| [D07 Tailcat](D07-tailcat.md) | docs | [#217](https://github.com/rurutheGeek/shake-cloud/issues/217) |
| [D08 Nextcloudからの印刷](D08-nextcloud-print.md) | apps-01・media-01 | [#218](https://github.com/rurutheGeek/shake-cloud/issues/218) |

## 共有ファイルと実機操作の調整

| 共有する対象 | 調整のルール |
| --- | --- |
| 同じVM | Composeプロジェクト名・保存先・ポートを分ける。アプリだけの更新を基本とし、VM再起動は利用中の担当へ影響を確認 |
| GPU、大量走査・取り込み・ビルド | I01で実測しG03等で負荷を調整。並列開発を全処理の同時最大負荷とは扱わない |
| Terraform state | 同じstateへの適用は1担当ずつ。core-01（旧services-01）は05-seed、game1は既存cloud API所有。新たなstateに同じVMを重複宣言しない |
| DNS・共通TLS・SSO | 各担当が必要な名前・ポート・認証設定の差分を用意し、I04/N05と調整して共通ファイルへ統合 |
| 既存メディアCompose・同期スクリプト | W03–W06・W02が共有する。編集範囲を事前に分け、統合時に全関連サービスを検証 |
| 文書一覧・配備台帳・構成図 | 進捗は Issue、配備の結果は配備台帳、仕様は計画書。並列編集で他担当の状態を上書きしない |

## コードと計画の入口

- サービスのコード・設定はリポジトリの `stacks/<name>/`。READMEは担当ID・配備先・再利用元を示す開発の入口です。
- 新規media-01のVM宣言は `platform/terraform/services/media/`。I02でVMと付属リソースを1 stateで管理する宣言が加わっています。既存コードの正本をコピーして二重管理しません。
- 作業IDを持たない検討メモもこの節に置きます。[Navidromeの改造案](navidrome-ideas.md)は、本体でできないことと代替手段の控えです（W05の配備そのものとは別）。
- 新しい作業は Issue を立て、仕様を書き残す価値があるときだけ計画書 `<ID>-<name>.md` を足して Issue からリンクする。共通項目は目的、現状の根拠、配置、変更範囲、開発開始の前提、配備・切替の前提、実装手順、共有変更、検証、完了条件です。
- [サービスの置き場所](../operations/services.md)・[IaCの所有境界](../architecture/iac.md)と合わせて確認します。秘密値・実データ・stateは通常のGit本文に入れません。
