# 機能別VMと並列開発計画

更新日: 2026-09-12。状態: **計画書・開発用READMEを整備。並行作業のI01で実測・軽量化、I02でmedia-01作成、I05でサービスstateの資格情報境界、W01でHomarr新規スタック、H01でHome Assistant Container（HA 2026.9.2）をservices-01へ配備し、ローカルオーナー作成とAuthentik SSO（hass-oidc-auth）ログインまで確認（バックアップ復元試験・未認証拒否・テスト自動化は未完）。H02でSwitchBot Cloud統合を追加し鍵・ドアセンサー・赤外線家電のエンティティを確認（実機操作は未確認）。H04はeufy-security-ws 3.1.0＋eufy_security v8.2.4でログイン・デバイス一覧・Pushまで動作（イベント取り込みは確認中、ライブ映像は新WebRTC方式のため未対応）。H03は見送り決定。M01はmonitor-01へ監視スタック（Prometheus・Alertmanager・Grafana・blackbox・pve/nut exporter）を配備済み（24/24 targets、UPS取得、通知確認）、D06 LocalSendとD08 Nextcloud印刷は配備済みで実機確認が残る**。

作業環境は既存dev-a／dev-bです。[開発参加ガイド](../onboarding.md)から接続し、下のIDから担当する機能を選びます。**W01・A01などの番号は識別用で、優先度や実施順ではありません。** 同じVMへ載せる機能でも独立して着手・完了できるものを別文書にしています。

## 正本と今回の範囲

- 配置方針・ID一覧・共有作業の調整はこの文書、各作業の仕様・依存・進捗は個別計画書を正本とします。
- 稼働状態と実機検証結果は[配備台帳](../operations/handover.md)に記録します。計画の作成を配備済みと扱いません。
- この資料整備の成果物は42件の計画書、開発ディレクトリのREADME、既存資料・図の整合です。並行する実装・実機作業の成果はI01・I02などの個別文書へ記録し、資料整備による実行と区別します。
- **増設は現有ホストへのVM追加を指します。ハードウェアの増設提案は含めません。** 容量測定・軽量化と各機能のコード・設定作成は並行します。

## 配置とサイズの開始案

数値は配備前に使用量・データ量を確認する仮予算で、現状の割当や動作保証ではありません。[配分表](../architecture/operations.md#resource-budget)には既存基盤も載せています。

| 配置先 | 機能群 | vCPU / RAM | ディスク・停止単位 |
| --- | --- | --- | --- |
| services-01（既存） | NetBox・MkDocs・Home Assistant Container・VPN・Homarr・Vaultwarden | 4 / 8GiB | 現行容量と実データを確認。常時VM内で別Compose・別保存先 |
| game1（既存） | ゲーム・RomM・Ollama・ポケモンAI一式・汎用RAG・Discord Bot | 8 / 現行12GiB、実測後16GiB候補 | 現行ディスクを維持しAI・ROM容量を測定。VM停止中はAI・Bot・ライブラリも停止 |
| media-01（VM作成済み） | Nextcloud・Calendar・Tasks・Kavita・Navidrome・MeTube・Picardと依存DB | 4 / 6GiB | OS32＋データ64GiBを仮予算。原本・索引・WAL・復元領域から確定 |
| 既存Kubernetes | AWX・DB提供（CNPG）・関数提供（Knative） | cp 2 / 3GiB、worker-01 4 / 8GiB | 固定RAM。worker-02は必要量から起動・join判断 |
| public-edge（条件成立後） | 外部公開Webの入口 | 1 / 1GiB | OS16GiB。公開要件が揃った時点でVM追加 |

AI専用VMは作りません。Homarr・VaultwardenをKubernetesへ移す計画もありません。Kubernetesは既存のOperator・関数実行の仕組みに価値がある用途に残します。identity・cloud-01・storage-s3と既存開発VMの所有・配置は維持します。

services-01のVM再起動では家電・VPNも停止するため、ラズパイの復旧用Tailscaleを維持・検証します。Home AssistantはContainer方式で、HAOSの追加アプリ管理は使いません。game1のゲーム・RomMとAI、ポケモンと汎用RAGのデータ・権限はそれぞれ分けます。media-01を止めるとNextcloudの同期・Calendar・Tasksも止まります。

## 作業ID一覧

詳細な状態・実装範囲・根拠・完了条件はリンク先が正本です。既存コードのある移行、新規開発、実機確認、資料修正、外部条件待ちを区別します。資料のみのDタスクも独立した成果物です。**「状態」列は一覧用の要約**で、正本は各文書の `状態:` 行です（実機の配備結果は[配備台帳](../operations/handover.md)）。

| 計画 | 作業の性質 | 配備先・対象 | 状態（要約） |
| --- | --- | --- | --- |
| [W01 Homarr](W01-homarr.md) | 移行 | services-01 | 一部完了（ブラウザSSO・再起動未確認） |
| [W02 Vaultwarden](W02-vaultwarden.md) | 移行 | services-01 | 一部完了（SSO・復元未確認） |
| [W03 Nextcloud・Calendar・Tasks](W03-nextcloud.md) | 移行 | media-01 | 一部完了（配備済み・移行未了） |
| [W04 Kavita](W04-kavita.md) | 移行 | media-01 | 一部完了（配備済み・移行未了） |
| [W05 Navidrome](W05-navidrome.md) | 移行 | media-01 | 一部完了（配備済み・移行未了） |
| [W06 MeTube・音楽変換・Picard](W06-music-tools.md) | 移行・新規 | media-01 | 一部完了（Picardのみ） |
| [W07 RomM](W07-romm.md) | 新規 | game1 | 一部完了（実装済み・実機未） |
| [A01 ポケモンDB・WebUI・agent](A01-pokemon-ai.md) | 移行・参照元取得待ち | game1 | 外部待ち |
| [A02 Ollama](A02-ollama.md) | 新規・実機検証 | game1 | 一部完了（実装済み・実機未） |
| [A03 汎用RAG](A03-rag.md) | 新規 | game1 | 計画（未着手） |
| [A04 Discord Bot](A04-discord-bot.md) | 新規 | game1 | 外部待ち |
| [A05 OpenHomeの製品・要件調査](A05-openhome.md) | 調査 | game1候補 | 調査・外部待ち |
| [G01 Wolf](G01-wolf.md) | 開発・実機検証 | game1 | 計画（実機未） |
| [G02 Azahar・非公開ルーム](G02-azahar.md) | 開発・実機検証 | game1 | 計画（実機未） |
| [G03 ゲームとAIの負荷調整](G03-game-ai-resources.md) | 実機検証・調整 | game1 | 計画（実機未） |
| [H01 Home Assistant Container](H01-home-assistant.md) | 新規 | services-01 | 一部完了（SSO動作・復元未） |
| [H02 SwitchBot](H02-switchbot.md) | 機器確認・新規 | services-01 | 実機待ち（Cloud統合追加済み） |
| [H03 Echo](H03-echo.md) | 機器確認・新規 | services-01 | 見送り（決定済み） |
| [H04 Eufy](H04-eufy.md) | 機器確認・調査 | services-01 | 実機確認中（ライブ未対応・イベント確認中） |
| [N01 セルフホストVPN](N01-vpn.md) | 選定・新規 | services-01 | 計画（未着手） |
| [N02 Tailscaleの復旧経路・DNS](N02-tailscale.md) | 既存経路の確認・改善 | 既存ラズパイ・端末 | 計画（合格未確認） |
| [N03 VLAN切替](N03-vlan.md) | 宣言済み・実機切替待ち | 既存ネットワーク | 切替待ち（人的作業） |
| [N04 公開Web入口](N04-public-edge.md) | 要件調査・新規 | public-edge候補 | 外部待ち |
| [N05 既存サービスのHTTPS移行完了](N05-https.md) | 残作業 | services-01・接続元 | 一部完了 |
| [I01 容量測定・軽量化](I01-resources.md) | 測定・改善 | 既存ホスト・VM | 一部完了（負荷試験未） |
| [I02 media-01のVM宣言](I02-media-vm.md) | 新規 | media-01 | 完了 |
| [I03 クラウドVMのAnsible連携](I03-cloud-inventory.md) | 新規 | 配備用ツール | 完了 |
| [I04 DNS登録](I04-cloud-dns.md) | 新規 | サービス宣言・DNS | 一部完了（VM連携未） |
| [I05 サービス用state管理](I05-service-state.md) | 未決事項の具体化 | 既存外部state保存先 | 一部完了（キー投入未） |
| [I06 AWXのジョブ整備](I06-awx.md) | 既存基盤への設定追加 | 既存Kubernetes | 一部完了（ジョブ未適用） |
| [M01 監視（Prometheus・Grafana）](M01-monitoring.md) | 新規 | monitor-01 | 配備済み（`grafana.apextox.dpdns.org`。Homarr連携済み。低電池シャットダウンが残り） |
| [O01 管理DBの外部バックアップ](O01-cloud-backup.md) | 既存ローカルバックアップの拡張 | cloud-01・既存外部保存先 | 一部完了（外部保全未） |
| [O02 CNPGバックアップ](O02-cnpg-backup.md) | 新規 | 既存Kubernetes・Garage・外部保存先 | 一部完了（バックアップ未） |
| [O03 VM・アプリ状態の復元](O03-restore.md) | 既存手順の拡張・検証 | 対象VM・隔離復元先 | 一部完了（復元合格未） |
| [D01 オンボーディング](D01-onboarding.md) | 資料更新 | docs | 完了（文書） |
| [D02 配置・配分表・構成図](D02-placement.md) | 資料更新 | docs | 進行中（SVG最終描画未） |
| [D03 サービス配置とIaC所有境界](D03-service-boundaries.md) | 資料更新 | docs | 完了（文書） |
| [D04 実装状況の訂正](D04-status.md) | 資料更新 | docs | 完了（文書） |
| [D05 Picard](D05-picard.md) | 資料のみ | docs・media（音楽導線） | 未着手 |
| [D06 LocalSend](D06-localsend.md) | 実装＋資料 | docs・media-01 | 一部完了（実送受信未） |
| [D07 Tailcat](D07-tailcat.md) | 資料のみ | docs | 未着手 |
| [D08 Nextcloudからの印刷](D08-nextcloud-print.md) | 実装＋資料 | services-01・media-01 | 一部完了（ブラウザー操作のみ未確認） |

## 並列で進めるための依存関係

**容量測定や他機能の配備が終わるまで、全員の開発を止めません。** 各文書には「開発開始の前提」と「実機配備・切替の前提」を分けて記載します。次の表は実機で組み合わせる場面の概要で、個別の前提は各計画書を参照してください。

| 並列に着手できる作業 | 実機で組み合わせる際の条件 |
| --- | --- |
| W01・W02・H01・N01 | services-01の容量と個別保存先・Compose・TLS設定を確認。VM再起動と入口変更を調整 |
| W03–W06とI02 | アプリの設定・テストデータ検証は先行可能。media-01の配備と実データ容量の確認後に切替 |
| A01・A02・A03・A04 | 外部のポケモンAIソース・バックアップはA01の実移行条件。A04は模擬RAG応答で開発し実接続だけA03準備後に確認 |
| G01・G02・W07とA01–A04 | 設定作成は並行。GPUを同時に負荷試験せず、G03で競合・停止切替を確認。RomMの走査はゲーム・推論と重ねない |
| H02・H03・H04とH01 | 機種・接続要件は先行調査。家電の実操作はH01と対象機器の準備後 |
| N01・N02・N03・N04・N05 | 調査・設定を並行。経路・ポート・DNS・TLSを変える実機切替は復旧経路を確認して調整 |
| I03・I04・I05・I06 | API模擬応答・宣言・ジョブ設定は並行。対象VM/stateの管理権限と保存先を確認して実機適用 |
| O01・O02・O03と各アプリ | 復元手順・テストは並行。既存外部保存先の確認と隔離復元合格を本データ切替の条件にする |
| D01–D08 | 実装・配備から独立して更新。未実施の確認を完了扱いにしない |

同じVMに配備すること自体は開発順序の依存ではありません。N05など共通基盤への依存は当該アプリに必要な入口・設定の準備を指し、他アプリを含む計画全体の完了を待つ条件ではありません。認証統合も各アプリで既存コードを再利用し、既存アカウント・subject・権限・クライアント接続を確認してから切り替えます。独立したアプリのDBを一括移行しません。

## 共有ファイルと実機操作の調整

| 共有する対象 | 調整のルール |
| --- | --- |
| 同じVM | Composeプロジェクト名・保存先・ポートを分ける。アプリだけの更新を基本とし、VM再起動は利用中の担当へ影響を確認 |
| GPU、大量走査・取り込み・ビルド | I01で実測しG03等で負荷を調整。並列開発を全処理の同時最大負荷とは扱わない |
| Terraform state | 同じstateへの適用は1担当ずつ。services-01は05-seed、game1は既存cloud API所有。新たなstateに同じVMを重複宣言しない |
| DNS・共通TLS・SSO | 各担当が必要な名前・ポート・認証設定の差分を用意し、I04/N05と調整して共通ファイルへ統合 |
| 既存メディアCompose・同期スクリプト | W03–W06・W02が共有する。編集範囲を事前に分け、統合時に全関連サービスを検証 |
| 文書一覧・配備台帳・構成図 | 個別文書で詳細を更新し、一覧にはID・リンクと配備の確認結果だけを反映。並列編集で他担当の状態を上書きしない |

常用基盤の計画RAMは26GiBで、media-01 6GiB・game1 16GiB・開発VM2台12GiBも上限まで使うと計64GiBになります。ホストの認識RAM59.7GiBは2026-09-12の実測でも同じです。I01では割当上限、ホストの空き、ゲスト・コンテナの使用量、クラウドの実効クォータを別々に測り、軽量化・不要な常駐停止・負荷の調整を行います。worker-02の起動やクォータ変更で物理RAMが増えるとは扱いません。

## コードと計画の入口

- サービスのコード・設定はリポジトリの `stacks/<name>/`。READMEは担当ID・配備先・再利用元を示す開発の入口です。実装が加わった場所は個別計画書の状態を参照してください。
- 新規media-01のVM宣言は `platform/terraform/services/media/`。I02でVMと付属リソースを1 stateで管理する宣言が加わっています。既存コードの正本をコピーして二重管理しません。
- 作業文書は `<ID>-<name>.md`。共通項目は目的、現状の根拠、配置、変更範囲、開発開始の前提、配備・切替の前提、実装手順、共有変更、検証、完了条件です。
- [サービスの置き場所](../operations/services.md)・[IaCの所有境界](../architecture/iac.md)と合わせて確認します。秘密値・実データ・stateは通常のGit本文に入れません。

## この資料整備の検証

文書の厳格ビルド、ローカルリンクと作業IDの対応、公開対象チェック、差分の空白検査を行います。構成図を変えた場合はMermaid原稿と同名SVGを更新します。実機のVM作成・停止・配備・サイズ変更やAPI変更はこの資料整備の検証には含みません。

2026-09-12の検証: 厳格ビルド、当時40件のID・ナビゲーション対応、ローカルリンク、公開対象チェックが通過。D08・M01を加えた42件のID・ナビゲーション対応は再検証が必要。構成図の文字幅・配置の修正は[D02](D02-placement.md)に残っており、この資料整備全体の完了条件は未達です。
