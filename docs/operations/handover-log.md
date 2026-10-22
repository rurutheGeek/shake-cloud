---
title: 配備の記録
updated: 2026-10-22
section: 運用手順
audience: 管理者
tags:
  - ops
  - handover
---

# 配備の記録

> **更新日** 2026-10-22 ・ **区分** 運用手順 ・ **読む人** 管理者

**いまの状態の正本は[配備台帳](handover.md)です。** ここは日付つきの出来事を残す場所で、書いた時点の事実です。あとから状態が変わっても書き直しません。新しい出来事は、その節の末尾に足します。

## 2026-10-22 まで（台帳の「いまの実機」に書き足していた記録）

2026-09-22に、Proxmoxホスト直結の6TB USB HDD（`/srv/bulk`、ext4、ラベル `bulk6tb`）を、media-01（`/srv/media-stack/library`）とgame1（ROM原本・セーブ）へNFS共有しました。Tier1 VMの週次vzdumpは毎週日曜06:00・snapshot・zstd・keep-last=4で `/srv/bulk/backups` へ取り、game1のセーブは `tools/game1-saves-backup.sh` で別途取ります。対象VMIDは 2026-09-22 時点では 101・110・130・140・150・401・5001・5002 で、**2026-10-03 に 101・120・140・150・401・5001・5005 へ更新しました**。手順と限界は[共有バルクストレージ](bulk-storage.md)・[バックアップ](backup.md)が正本です。

2026-10-22に、PHPの遠隔コード実行の脆弱性 php2shell（CVE-2026-109618／109619）への対応として、PHPで動く4つのイメージを修正版のPHPを含むものへ上げました。Nextcloud 33.0.8→33.0.10（PHP 8.4.25→8.4.27）、FreshRSS 1.30.4（8.4.24→8.4.27）、Adminer 6.1.1→6.1.2（8.4.26→8.4.27）、LibreSpeed 6.2.0→6.3.1（8.5.8→8.5.12）です。Nextcloud の更新前に、DBの控えを media-01 の `/var/backups/nextcloud/` に取りました。

同じ日に、固定したイメージの脆弱性の毎日の点検を tarakoserver に入れました（`platform/ansible/image-scan.yml`、[監視](monitoring.md#image-scan)）。Trivy（OSパッケージ・ライブラリ）と、ソースから入った PHP・Node.js・Python の版の比較で、結果は Grafana の「Shake Lab イメージの脆弱性」とアラートで見ます。

2026-10-22 に、core-01・cloud-01 の受信を Proxmox の VM ファイアウォールで絞りました（既定は拒否、正本は `platform/terraform/firewall.yaml`、[区画](vlan.md)）。05-seed の `terraform.tfvars` は作業機に無かったため、state の値から作り直しました（gitignore 対象）。

同じ日に、中継（negitoroserver）の ufw をコード化しました（`roles/relay`）。手で入れてあった規則と同じ形で、80 番も Cloudflare だけにしました。

同じ日に、公開サイトのゾーン（ruruthegeek.dpdns.org）の守りを Terraform（`25-edge`）にしました。暗号化をフル（厳密）・TLS 1.2 以上・HTTPS へ転送にし、走査を止める WAF の独自ルールとレート制限を足しました（[公開サイト](web.md)）。

## 2026-10-03 まで（台帳の冒頭の「状態」欄に書き足していた記録）

**Phase 1〜7（VM・S3・ボリューム/SG・セルフサービス・CLI/Provider）に加え、Kubernetes クラスタ（kubeadm + Cilium + Flux/SOPS）と、その上の AWX 24.6.1・CloudNativePG 1.30.0（database）・Knative 1.23（function）まで実機で構築・確認済み。クラウドの4機能（VM・S3・database・function）が API・Provider・CLI・ポータルで揃った。identity は招待・メール復旧・Email OTP・パスキー（パスワードレス）まで実装済み。**`main` と cloud 機能のブランチは `e2fb0d9` で統合済み。以後の router・NetBox・AdGuard・監視・ストレージ・LibreSpeed の追補はブランチ `feat/ops-monitoring-storage` にあり、origin の旧ブランチより先行している。**media-01 は新規cloud VMとして作成し、Nextcloud・Kavita・Navidrome等を配備済み。既存環境からのデータ移行（W03〜W06。RomMはgame1でW07）が残る。残りは Phase 8（VLAN 分離の実機切替。**TL-SG605 がアンマネージドのため、マネージドスイッチを調達するまで着手できない**）、DB の外部バックアップ、既存環境からのメディアデータ移行。**2026-09-12のI01実測を反映し、k8s-cp-01・k8s-worker-01・probe-01は停止中、dev-a/dev-bの宣言RAMは6GiB。Homarrはservices-01へ新規配備済み（`https://homarr.apextox.dpdns.org`、identityのOIDC）。2026-09-13にNextcloudの「…」→「印刷」からservices-01のCUPSへ送る自作アプリをmedia-01へ配備した（D08）。2026-09-12に監視スタック（Prometheus・Alertmanager・Grafana・exporter）をmonitor-01へ配備した（M01）。2026-09-12〜13にHome Assistant（services-01）へAuthentik SSO・Eufy（イベント・スナップショット）・SwitchBot Cloudを設定した（H01/H02/H04。Eufyのライブ映像は公開ソフトでは不可のため H05 で自前実装中、Alexaは見送り）。2026-09-14に復旧経路のTailscale subnet routerをcloud VM `net-01`（`i-88933be43f442c6f4`、`192.168.10.103`）として作成し、tailnetへ参加した（N02。2026-10-01にルート承認とtailnet DNS（AdGuard Home）を適用。宅外端末での実機検証が未了）。****2026-09-30（午後）: H05 のライブ配信を android-01 VM から services-01（HA と同じホスト）へ移した。** `stacks/eufy-leo-rtc/` を独立 Compose（`mediamtx`＋`leo-live`、両方ホストネットワーク、イメージは digest 固定）にし、`platform/ansible/eufy-leo-rtc.yml` で配備する（秘密値は `platform/sops/eufy-security.sops.yaml` の EUFY_SN/DID/LICENSE/ACCOUNT/CONTACT）。RTSP は docker ゲートウェイ `172.31.254.1:8554` だけに開き、HA のカメラは `rtsp://172.31.254.1:8554/eufy`＋`http://172.31.254.1:8888/snapshot.jpg`。VM のパイプラインは停止した（アプリ捕捉が要る解析のときだけ使う）。 **2026-09-30: H05 のライブ映像を Home Assistant へ反映した。** eufyCam S4 のネイティブ leo_rtc クライアント（`stacks/eufy-leo-rtc/`、android-01 VM `192.168.10.104`）が映像（P 平文＋IDR AES-GCM 復号）と音声（ADTS AAC 16kHz）を復号し、`tools/live_supervisor.sh` がセッションを繰り返して Mediamtx (`:8554`) へ RTSP 配信する。HA（services-01）は Generic Camera `camera.eufycam_s4_leo_rtc`（`rtsp://192.168.10.104:8554/eufy`）として表示できる（`manage.py ensure-camera` で `.storage` へ登録、Ansible タスク化）。HA 用は**映像のみ**（go2rtc の MJPEG スナップショットは音声トラックがあると失敗するため）、録画用に `eufy_av`（映像＋音声）も出す。カメラはバッテリー機で 1 wake あたり数十秒〜数分しか流れず、切れている間は HA が「ストリームなし」になる（現状の制約）。上流 mega-yfue/eufy-sdk への移植は `feat/leo-rtc-s4`（2026-10-16 から Forgejo の `archive/eufy-sdk-leo-rtc`。解析記録は `archive/eufy-leo-rtc-re`、Ghidra 等の成果は `archive/eufy-re-analysis`）で wire 層 13 モジュール、`npm run verify` green。 2026-09-21〜23: LibreSpeed（`https://speed.apextox.dpdns.org`）をservices-01へ配備し、Proxmoxホスト直結の6TB USB HDDをext4・NFSでmedia-01とgame1へ共有、Tier1 VMの週次vzdumpとgame1セーブ、Proxmoxホストのnode_exporter・SMART/NVMe、Grafanaのホスト・ストレージ・VMメモリ・ゲーム使用量ダッシュボード、storage health（journald上限・root noatime・Dockerログ上限）、AdGuardのHaGeZi's Pro Blocklistを追加した。2026-10-02: media-01 へ UrBackup（Windows のイメージ・ファイルの世代バックアップ）を配備し、Android はポータルの WebUSB ボタン（USB直結）で担保する W08 を追加した（詳細は下の W08 行）。 2026-10-02: AdGuard の HaGeZi's Pro Blocklist が Xbox 実績用ドメイン（`vortex-win.data.microsoft.com`・`vortex.data.microsoft.com`・`pipe.aria.microsoft.com` など）を遮断し、Minecraft / Minecraft Dungeons の実績が解除されない症状を実測。`user_rules` に HaGeZi の Microsoft 一覧ぶんの除外を追加し、DNS 側の遮断は解消した。その後、**MCD2（Minecraft Dungeons II）の Steam 版は Xbox 実績が記録されない既知の不具合**（[feedback.minecraft.net 2026-09-30](https://feedback.minecraft.net/hc/en-us/community/posts/49272314358413-BROKEN-Steam-version-doesn-t-earn-Xbox-achievements)、Switch 2 でも報告）で、AdGuard・PC 側は無関係と判明。ゲーム内実績は出るが Xbox プロフィールはプレイ時間のみになる。Mojang の修正待ち（除外は他タイトル用に残す）。** **2026-10-03: 配置と命名の再編を実機へ適用済み。** identity・storage-s3・net-01・旧 monitor-01（クラウドVM）を削除し、Authentik・NetBox・入口の Caddy は core-01、Garage は cloud-01、監視は基盤VMの monitor-01（120）、Tailscale は router-01、アプリは apps-01（5005）へ集約した。リポジトリ側も旧インベントリ（`inventory.cloud.py`・`cloud-inventory.yml`・`monitor.ini.example`）を削除し、文書を現状へ合わせた。詳細と残作業は §6 の各再編行。

**この文書が、クラウドの実機配備状態と既存TODOの正本です。** 2026-09-12に[機能別の並列開発計画](../development/index.md)を追加しました。各作業IDの仕様・進捗は個別計画書を正本とし、実機配備後にこの台帳へ結果を記録します。2026-09-12に media-01 を新規cloud VMとして作成し、Nextcloud・Kavita・Navidrome等を配備しました（I02。既存環境からのデータ移行は未完）。2026-09-12に Home Assistant Container を services-01 へ配備し、AuthentikのOIDC（SSO）・Eufy（イベント/スナップショット）・SwitchBot Cloud まで設定しました（H01/H02/H04。バックアップと復元試験は未完、Eufyのライブ映像は新方式のため不可）。 途中で担当が変わっても、ここを読めば「何が決まっていて、どこまでできていて、次に何をやるか」が分かるようにします。作業を終えたら表の状態と更新日を直してください。チャットや個人の作業メモにだけ残さないこと。
