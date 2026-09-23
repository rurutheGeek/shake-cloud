---
title: 設計と決定の入口
updated: 2026-09-18
section: 設計
audience: 管理者・開発者
tags:
  - design
---

# 設計と決定の入口

> **更新日** 2026-09-18 ・ **区分** 設計 ・ **読む人** 管理者・開発者

**この節は「なぜそう作ったか」を残す場所です。** 手順は[運用手順](../operations/index.md)、実機の状態は[配備台帳](../operations/handover.md)、これからの作業は[開発計画](../development/index.md)が正本で、食い違ったらそちらが正しいと考えてください。

いま何がどのVMで動いているかを1枚で知りたいときは[ホームラボの全体像](overview.md)を先に読んでください。このページは、その形になるまでに決めた前提と選択の記録です。

**状態**: Proxmox・Kubernetes・クラウドAPI・identity・メディア・家電・監視は構築済み。ゲーム（Wolf・Azahar）とVLANの実機切替、VPN、既存環境からのメディアデータ移行は未完了。

## この節のページ

| ページ | 内容 |
| --- | --- |
| [ホームラボの全体像](overview.md) | 役割ごとのVMと、何を自作しているかの詳細版 |
| [決定ログ](decisions.md) | **すでに決まっていること**と、その理由。蒸し返す前にここを読む |
| [信頼境界とセキュリティ方針](security.md) | 何を信頼し、何を信頼しないか。守らないと決めたことも書く |
| [障害モードと単一障害点](failure-modes.md) | 何が止まると何が使えなくなるか。復旧の順番 |
| [IaCの所有境界](iac.md) | Terraform・NetBox・Ansible・FluxとクラウドAPIの担当範囲、VMIDとプール、ロールとACL |
| [最小クラウドとProvider](cloud.md) | 4機能、SSOとアクセスキー、Proxmox側の制約、実装境界 |
| [ネットワーク・公開範囲・SSO](network-auth.md) | 既存機器、VPN、公開Web、スマートフォン、認証の使い分け |
| [VPNの比較と併用](vpn.md) | 候補の比較、対応OS、復旧経路、認証依存 |
| [ゲーム・開発VM](gaming.md) | 2人で使う構成、通信プレイ、性能確認、軽量開発環境 |
| [配備・Git管理・ストレージ・復旧](operations.md) | VM配分、Kubernetes運用、永続データ、段階的移行 |

初回構築の手順そのものは[Proxmox VE導入後の進め方](../operations/bring-up.md)へ移しました（設計ではなく実行する手順のため）。

## 前提と合意した範囲

- 現有のK11（Ryzen 9 8945HS、8コア16スレッド、Radeon 780M、公称RAM 64GB、SSD 1TB）へ機能別VMを追加する。増設はVMの追加を指し、ハードウェアの増設提案は含めない。
- 新しいルータ・スイッチは購入しない。**ルータは K11 上の OpenWrt VM `router-01` として自作し、2026-09-20 に切替済み**（[N06](../development/N06-router.md)・[router-config](../operations/router-config.md)）。Aterm は AP モードの Wi-Fi 専用機、スイッチは既存の TL-SG605 をそのまま使う。宅外の復旧経路はラズパイではなく cloud VM `net-01`（Tailscale subnet router）に置く。
- サービスは原則VPNからアクセスする。既存の公開Webと、セルフホストVPNの制御・認証に必要な入口は、対象を明示して公開を設計する。
- 常用KubernetesのAWX・CloudNativePGによるDB提供・Knativeによる関数提供を維持する。Homarr・Vaultwarden・Home Assistantはservices-01、メディアはmedia-01、監視はmonitor-01、ゲーム・AI一式はgame1へ配置する。
- ゲームは1つのVMへ2人が接続し、Wolfで画面と入力を分ける。3DSのポケモンを各自のAzaharで遊び、対応作品で交換・対戦を行う。画質よりカクつきの少なさを優先する。
- 自分ともう一人に、軽量なインフラ開発用VMを1台ずつ用意する。
- 自作Terraform Providerが扱うクラウド機能は、**VM、サーバレス実行、S3互換オブジェクトストレージ、DBアプライアンス**の4つを最小範囲とする。**4機能とも実装済み・実機確認済み**（後者2つは Kubernetes 構築後に追加した）。
- **変更**: クラウドの利用者管理と利用者ポータルを初期範囲に**含める**。Authentikユーザー1人が1アカウント。クォータと所有権を成立させるために必要だったため。組織・プロジェクト・課金は引き続き含めない。
- **変更（2026-09-11）**: **VMの一覧は全員に見せる。**当初は「自分のリソースだけが見える」としていましたが、2人で1台のホストを分け合うので、誰が何を動かしているかが見えないと容量の判断ができません。見えるのは所有者名・イメージ・割り当てリソース・状態までで、**操作（電源・削除・大きさの変更）は所有者と管理者だけ**です。
- **変更**: Authentikをクラウドの統合認証にも使う。ブラウザはOIDCでポータルへログインし、そこで発行したアクセスキーをTerraformとCLIが使う。キーをSSOと分けるので、**Authentikが停止していてもTerraformは動く**。

初回構築の経緯は[Proxmox VE導入後の記録](../operations/bring-up.md)に残しています。今後は[作業ID一覧](../development/index.md)から独立した作業を選び、必要な切替条件だけを調整して並列に進めます。実機状態は[配備台帳](../operations/handover.md)、配置計画は[VM配分](operations.md)で区別します。

## 採用候補

以下はこの条件に対する推奨案です。導入バージョンや実機互換性は構築時に固定・検証します。

| 用途 | 推奨案 | 配置 |
| --- | --- | --- |
| 仮想化・VM提供 | Proxmox VE | K11 |
| 常用Kubernetes基盤 | kubeadm + containerd + Cilium（構築済み） | control plane×1、worker-01。worker-02は必要量から起動判断（2026-09-12時点でcp・worker-01は停止中） |
| アプリの配備 | VMはCompose・Ansible、クラスタはFlux | services-01・media-01・monitor-01・game1・常用Kubernetes |
| サーバレスHTTP実行 | Knative Serving + Kourier | Kubernetes |
| S3互換ストレージ | Garage（当初は単一ノード） | 小型ストレージVM |
| DBアプライアンス | CloudNativePG + PostgreSQL、必要時pgvector | Kubernetes |
| 自作クラウド | Go API・ジョブ・管理DB、Terraform Provider | APIはcloud-01のCompose、Providerは開発VM |
| ブラウザ認証 | Authentik + 専用PostgreSQL | Kubernetes外の認証VM |
| VPN・宅外からの監視 | Tailscale（復旧経路は cloud VM `net-01`）。セルフホストVPNはN01で継続検討 | K11 の外に出られないため、net-01 は cloud プールのVM。対象VMへagent |
| DNS | **AdGuard Home（広告遮断・DoH）＋ dnsmasq（DHCP・`*.lan`）** | **router-01（K11 上の OpenWrt VM）**。2026-09-20 に dnsmasq から移行 |
| 公開入口 | Caddy（各ホストでTLS終端） | 各VM（identity・services-01・media-01・monitor-01・cloud-01）。公開用VMはN04 |
| 家電・自動化 | Home Assistant Container（配備済み） | services-01。Authentik OIDCでSSO。SwitchBot Cloud（Hub Mini）とEufy中継を連携。Eufyのライブ映像は不可、Alexa連携は見送り |
| 監視 | Prometheus + Grafana + Alertmanager（配備済み） | monitor-01（新規cloud VM）。UPS・証明書・資源を監視。ラズパイはDNSと復旧経路 |
| 印刷 | CUPS（services-01）＋Nextcloud印刷アプリ（media-01） | 配備済み。API経由の印刷は確認済みで、ブラウザー操作は未確認（D08） |
| ポケモンRDB・図鑑VDB | PostgreSQL＋pgvector | game1。WebUI・agent・推論と一式移行。汎用RAG・Botも同居 |
| 音楽タグの編集 | Nextcloudの自作アプリ `shake_tags` とタグAPI | media-01。MeTubeの取込とNextcloudのmusicをNavidrome向けに整える（専用GUIコンテナは2026-09-13に撤去） |
| LocalSend | 各端末アプリ＋media-01の受信機 | 専用VM不要。受信機はmedia-01（D06。実送受信は未確認） |
| OpenHome | 製品・リポジトリ確認待ち | ゲームVMへの同居候補 |
| ゲーム | Wolf + Azahar×2 + 非公開ルーム | 780Mを割り当てるゲームVM |

KnativeのKourierは、クラスタ内の通常HTTP入口であるCilium Ingressとは別の役割です。[Knativeのネットワーク構成](https://knative.dev/docs/install/)

## 論理構成図

実線は主な通信、点線は設定・管理・認証・バックアップです。線の存在は任意のポートへのアクセス許可を意味しません。**2026-09-20 時点の実機に合わせて更新しています。**

[![ホームラボ全体の論理構成](diagrams/overview.svg)](diagrams/overview.svg)

図を開くと拡大できます。**ネットワーク（回線・ルータ・DNS・IP帯）は[ネットワーク・公開範囲・SSO](network-auth.md)の図**、クラウドの内部経路は[最小クラウドの図](cloud.md)、ゲーム内の分離は[ゲームの図](gaming.md)を参照してください。

[編集用Mermaid](diagrams/overview.mmd)

## ホスト性能の見立て

コード・設定作成は並列に進めます。全VMの上限合計は物理RAMを超え得るため、実機検証では同じCPU・RAM・SSDの使用量を測定し、重い処理と不要な常駐を改善します。VM作成・変更時の容量検査を維持し、作業中のVM停止は利用者と調整します。[初期リソース配分](operations.md#resource-budget)は実測値ではありません。

780MのVRAMはシステムRAMとの共有です。「RAM 64GBにVRAM 16GBが追加される」計算はできません。最初から16GBをBIOSで固定予約せず、実際にProxmoxから利用できるRAMとゲストから使えるGPUメモリを確認します。GPUパススルー時のAPUメモリの見え方も実機検証対象です。

Ollama公式のROCm対応一覧だけでは8945HS／780Mの動作を保証できません。まずCPU、次にVulkanを検証し、2人でゲームをするときは推論を止めます。[Ollamaのハードウェア対応](https://docs.ollama.com/gpu)

現有SSDの実使用量を確認し、使用率80%程度で不要なコピー・保持期間・取り込み範囲を見直します。ゲーム、モデル、S3、VMイメージ、スナップショットをすべて無制限に置きません。単一SSDの故障への復旧には別ディスク・別機器のバックアップが必要です。

## 現在の実装との差

| 項目 | 現状（2026-09-20） |
| --- | --- |
| ネットワーク（ルータ・DNS・DHCP） | **router-01（K11 上の OpenWrt VM）へ切替済み（2026-09-20）。** Aterm は AP モードの Wi-Fi 専用。DNS は AdGuard Home（広告遮断・DoH）＋ dnsmasq（DHCP・`*.lan`）、IPv6 は odhcpd の relay ＋ ndppd。予約・リースは NetBox と同期する。手順は[router-01](../operations/router.md)・[設定まとめ](../operations/router-config.md) |
| メディア・認証 | Homarr・Vaultwarden・Home Assistantはservices-01、Nextcloud・Kavita・Navidromeはmedia-01で配備済み。既存環境からのデータ移行（W03–W06）が残る |
| ドキュメントサイト | `https://docs.apextox.dpdns.org`（LAN 内。直アクセスは `http://192.168.10.200:8090`）。Git の `docs/` から Ansible（`platform/ansible/docs-site.yml`）が生成・配備する |
| Proxmoxの所有境界（プール・ロール・ACL） | Terraform `00-bootstrap` として実装済み。**実機へ適用済み**（2026-09-10 に API で確認） |
| ホストの読み取り | Ansible `survey-pve.yml` として実装済み。読み取りのみ |
| ProxmoxへのVM作成・移行 | `10-platform` として実装済み |
| クラウドAPIの権限とIP採番の枠 | `00-bootstrap` と `10-platform` に実装済み。**実機へ適用済み**（`cloudapi@pve` 作成、ロール割り当て、実機プローブ PASS） |
| 常用Kubernetes・Knative・Garage・CloudNativePG | **構築済み（2026-09-12）**: kubeadm + Cilium、Flux/SOPS、local-path、MetalLB、cert-manager、AWX、CloudNativePG、Knative。2026-09-12時点でcp・worker-01・worker-02は停止中（起動は[配備台帳](../operations/handover.md)）。手順は[Kubernetes クラスタ](../operations/kubernetes.md)、[Garage](../operations/garage.md) |
| 自作クラウドAPI・Terraform Provider・ポータル・CLI | **4機能（VM・S3・database・function）を API・Provider・CLI・ポータルまで実装し、実機確認済み。** VLAN分離は切替の宣言・手順を用意済み（実機切替は物理作業待ち）。利用者の招待・メール復旧・パスキーは identity サービスで実装済み（[認証基盤](../operations/identity.md)）。手順は[クラウドAPIの構築](../operations/cloud.md)・[接続先一覧](../reference/urls.md) |
| Home Assistantと家電連携 | **配備済み（2026-09-12）**: services-01のContainerを `https://ha.apextox.dpdns.org` でHTTPS化（LAN内。本体は `127.0.0.1:8123`）。Authentik OIDCと緊急用ローカルオーナー。SwitchBot Cloud（Hub Mini）とEufy中継を連携。Eufyのライブ映像は不可、Alexa連携は見送り。手順は[利用者向けHA](../services/home-assistant.md)・[H01](../development/H01-home-assistant.md) |
| 監視・印刷・転送 | **監視はmonitor-01へ配備（2026-09-13、M01）**: Prometheus・Alertmanager・Grafana・exporter。**印刷**はCUPS（services-01）とNextcloud印刷アプリ（media-01）を配備（D08。ブラウザー操作は未確認）。**LocalSend受信機**はmedia-01（D06。実送受信は未確認） |
| Wolf・Azahar×2・780Mパススルー | 未検証 |
| 公開Web統合 | N04の独立計画。公開条件成立後にVM追加 |

## 残っている確認項目（2026-09-20）

1. 既存ネットワークのサブネット・VLAN と、TL-SG605 のポート割当（[N03](../development/N03-vlan.md)）。
2. K11のIOMMUグループ、BIOSのGPUメモリ設定、ゲスト再起動後の780M再利用（[G01](../development/G01-wolf.md)–[G03](../development/G03-game-ai-resources.md)）。
3. 対象のポケモン作品と更新版、Azaharの固定版での2人プレイと交換・対戦（[G02](../development/G02-azahar.md)・[A01](../development/A01-pokemon-ai.md)）。
4. S3の利用クライアントと必要API（Garageはバージョニング未対応）。バックアップ保存先と容量（[O01](../development/O01-cloud-backup.md)–[O03](../development/O03-restore.md)）。
5. VPN製品の選定と宅外からの到達経路（[N01](../development/N01-vpn.md)・[N02](../development/N02-tailscale.md)）。

## この文書の管理

Gitの `docs/` が正本です。書き方・置き場所・検証・公開の決まりは[ドキュメントの書き方](../contributing-docs.md)にあります。
