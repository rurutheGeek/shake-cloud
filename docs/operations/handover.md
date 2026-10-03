---
title: クラウド開発の引き継ぎとTODO
updated: 2026-10-02
section: 運用手順
audience: 管理者
tags:
  - ops
  - handover
---

# クラウド開発の引き継ぎとTODO

> **更新日** 2026-10-02 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: **Phase 1〜7（VM・S3・ボリューム/SG・セルフサービス・CLI/Provider）に加え、Kubernetes クラスタ（kubeadm + Cilium + Flux/SOPS）と、その上の AWX 24.6.1・CloudNativePG 1.30.0（database）・Knative 1.23（function）まで実機で構築・確認済み。クラウドの4機能（VM・S3・database・function）が API・Provider・CLI・ポータルで揃った。identity は招待・メール復旧・Email OTP・パスキー（パスワードレス）まで実装済み。**`main` と cloud 機能のブランチは `e2fb0d9` で統合済み。以後の router・NetBox・AdGuard・監視・ストレージ・LibreSpeed の追補はブランチ `feat/ops-monitoring-storage` にあり、origin の旧ブランチより先行している。**media-01 は新規cloud VMとして作成し、Nextcloud・Kavita・Navidrome等を配備済み。既存環境からのデータ移行（W03〜W06。RomMはgame1でW07）が残る。残りは Phase 8（VLAN 分離の実機切替。**TL-SG605 がアンマネージドのため、マネージドスイッチを調達するまで着手できない**）、DB の外部バックアップ、既存環境からのメディアデータ移行。**2026-09-12のI01実測を反映し、k8s-cp-01・k8s-worker-01・probe-01は停止中、dev-a/dev-bの宣言RAMは6GiB。Homarrはservices-01へ新規配備済み（`https://homarr.apextox.dpdns.org`、identityのOIDC）。2026-09-13にNextcloudの「…」→「印刷」からservices-01のCUPSへ送る自作アプリをmedia-01へ配備した（D08）。2026-09-12に監視スタック（Prometheus・Alertmanager・Grafana・exporter）をmonitor-01へ配備した（M01）。2026-09-12〜13にHome Assistant（services-01）へAuthentik SSO・Eufy（イベント・スナップショット）・SwitchBot Cloudを設定した（H01/H02/H04。Eufyのライブ映像は公開ソフトでは不可のため H05 で自前実装中、Alexaは見送り）。2026-09-14に復旧経路のTailscale subnet routerをcloud VM `net-01`（`i-88933be43f442c6f4`、`192.168.10.103`）として作成し、tailnetへ参加した（N02。2026-10-01にルート承認とtailnet DNS（AdGuard Home）を適用。宅外端末での実機検証が未了）。****2026-09-30（午後）: H05 のライブ配信を android-01 VM から services-01（HA と同じホスト）へ移した。** `stacks/eufy-leo-rtc/` を独立 Compose（`mediamtx`＋`leo-live`、両方ホストネットワーク、イメージは digest 固定）にし、`platform/ansible/eufy-leo-rtc.yml` で配備する（秘密値は `platform/sops/eufy-security.sops.yaml` の EUFY_SN/DID/LICENSE/ACCOUNT/CONTACT）。RTSP は docker ゲートウェイ `172.31.254.1:8554` だけに開き、HA のカメラは `rtsp://172.31.254.1:8554/eufy`＋`http://172.31.254.1:8888/snapshot.jpg`。VM のパイプラインは停止した（アプリ捕捉が要る解析のときだけ使う）。 **2026-09-30: H05 のライブ映像を Home Assistant へ反映した。** eufyCam S4 のネイティブ leo_rtc クライアント（`stacks/eufy-leo-rtc/`、android-01 VM `192.168.10.104`）が映像（P 平文＋IDR AES-GCM 復号）と音声（ADTS AAC 16kHz）を復号し、`tools/live_supervisor.sh` がセッションを繰り返して Mediamtx (`:8554`) へ RTSP 配信する。HA（services-01）は Generic Camera `camera.eufycam_s4_leo_rtc`（`rtsp://192.168.10.104:8554/eufy`）として表示できる（`manage.py ensure-camera` で `.storage` へ登録、Ansible タスク化）。HA 用は**映像のみ**（go2rtc の MJPEG スナップショットは音声トラックがあると失敗するため）、録画用に `eufy_av`（映像＋音声）も出す。カメラはバッテリー機で 1 wake あたり数十秒〜数分しか流れず、切れている間は HA が「ストリームなし」になる（現状の制約）。上流 mega-yfue/eufy-sdk への移植は `feat/leo-rtc-s4`（ローカル・push なし）で wire 層 13 モジュール、`npm run verify` green。 2026-09-21〜23: LibreSpeed（`https://speed.apextox.dpdns.org`）をservices-01へ配備し、Proxmoxホスト直結の6TB USB HDDをext4・NFSでmedia-01とgame1へ共有、Tier1 VMの週次vzdumpとgame1セーブ、Proxmoxホストのnode_exporter・SMART/NVMe、Grafanaのホスト・ストレージ・VMメモリ・ゲーム使用量ダッシュボード、storage health（journald上限・root noatime・Dockerログ上限）、AdGuardのHaGeZi's Pro Blocklistを追加した。2026-10-02: media-01 へ UrBackup（Windows のイメージ・ファイルの世代バックアップ）を配備し、Android はポータルの WebUSB ボタン（USB直結）で担保する W08 を追加した（詳細は下の W08 行）。 2026-10-02: AdGuard の HaGeZi's Pro Blocklist が Xbox 実績用ドメイン（`vortex-win.data.microsoft.com`・`vortex.data.microsoft.com`・`pipe.aria.microsoft.com` など）を遮断し、Minecraft / Minecraft Dungeons の実績が解除されない症状を実測。`user_rules` に HaGeZi の Microsoft 一覧ぶんの除外を追加し、DNS 側の遮断は解消した。その後、**MCD2（Minecraft Dungeons II）の Steam 版は Xbox 実績が記録されない既知の不具合**（[feedback.minecraft.net 2026-09-30](https://feedback.minecraft.net/hc/en-us/community/posts/49272314358413-BROKEN-Steam-version-doesn-t-earn-Xbox-achievements)、Switch 2 でも報告）で、AdGuard・PC 側は無関係と判明。ゲーム内実績は出るが Xbox プロフィールはプレイ時間のみになる。Mojang の修正待ち（除外は他タイトル用に残す）。**

**この文書が、クラウドの実機配備状態と既存TODOの正本です。** 2026-09-12に[機能別の並列開発計画](../development/index.md)を追加しました。各作業IDの仕様・進捗は個別計画書を正本とし、実機配備後にこの台帳へ結果を記録します。2026-09-12に media-01 を新規cloud VMとして作成し、Nextcloud・Kavita・Navidrome等を配備しました（I02。既存環境からのデータ移行は未完）。2026-09-12に Home Assistant Container を services-01 へ配備し、AuthentikのOIDC（SSO）・Eufy（イベント/スナップショット）・SwitchBot Cloud まで設定しました（H01/H02/H04。バックアップと復元試験は未完、Eufyのライブ映像は新方式のため不可）。 途中で担当が変わっても、ここを読めば「何が決まっていて、どこまでできていて、次に何をやるか」が分かるようにします。作業を終えたら表の状態と更新日を直してください。チャットや個人の作業メモにだけ残さないこと。

## 1. 何を作っているか

Proxmox VE の上に、**広く使われているクラウドAPIと同じ語彙で操作できる小さなプライベートクラウド**を作っています（揃える理由は[最小クラウドとProvider](../architecture/cloud.md)）。

到達点は次のとおりです。

1. 利用者が Authentik（共通ログイン）のアカウントでポータルに入る
2. ポータル・Terraform・CLI のどれからでも自分のVMを作る
3. Webコンソールで入り、要らなくなったら消す

v1 の範囲は **VM・S3互換ストレージ（Garage）・database（CloudNativePG）・function（Knative）** です。オートスケール、冗長化、ネットワークのAPI化は作りません。一覧は[最小クラウドとProvider](../architecture/cloud.md)にあります。**サービスを載せるVMの置き場所と作り方は[サービスの置き場所とクラウドVMでの作り方](services.md)、接続先は[URL一覧](../reference/urls.md)。**

## 2. 読む順番

| 順 | 文書 | 何が分かるか |
| --- | --- | --- |
| 1 | この文書 | 実機の状態・入口とログイン情報の置き場所・進捗・TODO・引き継ぎ方法 |
| 2 | [最小クラウドとProvider](../architecture/cloud.md) | 設計と、Proxmox の権限制約に対する答え |
| 3 | [IaCの所有境界](../architecture/iac.md) | 誰が何を作るか、宣言ファイルの置き場所 |
| 4 | [クラウドAPIの構築](cloud.md)（[API本体](cloud-api.md)・[リソース](cloud-resources.md)・[プローブ](cloud-verify.md)） | 実機で行った手順・実測値・確認結果 |
| 5 | `cloud/openapi/shakecloud.yaml` | API の正本。エンドポイント・フィールド・エラーコード |
| 6 | [shakecloud CLI](cli.md) | コマンドからの操作。アクセスキーの使い方とサブコマンド |
| 7 | [shakecloud Terraform Provider](terraform-provider.md) | Terraform から操作。リソースと例 |
| 8 | [Terraformの実行](terraform.md) | plan/apply の方法と、中断時の回収 |
| 9 | [秘密値の管理](secrets.md) | SOPS と age の扱い |
| 10 | [決定ログ](../architecture/decisions.md) | すでに決まっていることと、その理由 |
| 11 | [確認と、はまりどころ](verify.md) | 変更後に流す検査と、実際に踏んだ落とし穴 |

## 3. いまの実機

Proxmox ホストは `apextox`（`https://192.168.10.10:8006`、PVE 9.2.2）です。

| VMID | 名前 | IP | 役割 | 状態 |
| --- | --- | --- | --- | --- |
| 100 | game1 | 192.168.10.127 | ゲームサーバ（Bazzite、GPUパススルー hostpci0/1）。`cloud` プール | 稼働。2026-09-11 にクラウドAPIへ引き取り済み（owner `shunyazhiyuan97`、instance `i-bec54e3a0169b3660`、既定SG） |
| 101 | router-01 | 192.168.10.1 | **家庭内ルータ（OpenWrt）。** WAN=vmbr1 / LAN=vmbr0。AdGuard Home（DNS・広告遮断）と dnsmasq（DHCP） | 稼働。2026-09-20 に Aterm から切替（N06）。`https://router.apextox.dpdns.org`（LuCI。**SSOなし**＝復旧経路）、`https://adguard.apextox.dpdns.org`（Forward Auth）。起動順1・遅延30秒。[router-01](router.md) |
| 110 | identity | 192.168.10.204 | Authentik | 稼働。`https://auth.apextox.dpdns.org`（`:9000`・`:9443` は 127.0.0.1 に閉じた）。**2026-09-26 18:30頃、メモリ枯渇（OOM）でゲストがハングし、SSO配下の全サイトが停止。ACPIに応答せず、PVE APIのハードリセットで復旧（Authentik healthy、SSO各サイト302を確認）。同日、`hosts.yaml` のballoon下限を identity 3GiB・cloud-01 1GiB へ引き上げて `10-platform` を適用（実機のballoonを確認）。スワップは未設定のままなので、必要なら追加を検討** |
| 130 | storage-s3 | 192.168.10.206 | Garage（S3互換オブジェクトストア、単一ノード） | 稼働。S3 `:3900`、管理API `:3903`。データは専用ディスク32GiB（`/srv/garage`） |
| 140 | cloud-01 | 192.168.10.205 | クラウドAPI（Phase 1〜7 + database/function）と管理DB | 稼働。`https://cloud.apextox.dpdns.org`（`:8080` は 127.0.0.1 に閉じた）。メモリ使用 約0.4GiB / 2GiB（2026-09-12） |
| 150 | services-01 | 192.168.10.200 | NetBox と入口の Caddy（netbox・adguard・router）。アプリは 2026-10-03 に apps-01（192.168.10.105）へ移した | 稼働。`https://netbox.apextox.dpdns.org`（`:8000` も開いている）、`https://docs.apextox.dpdns.org`（`:8090` も開いている）、`https://homarr.apextox.dpdns.org`（`:7575` は 127.0.0.1）、`https://vault.apextox.dpdns.org`（`:8222` は 127.0.0.1）、`https://cups.apextox.dpdns.org`、`https://ha.apextox.dpdns.org`（`:8123` は 127.0.0.1）、`https://speed.apextox.dpdns.org`（`:8300` は 127.0.0.1。LibreSpeed）。ゲストOSの時刻は手動でJST（コード側は `Etc/UTC`。後述） |
| 200 | k8s-cp-01 | 192.168.10.207 | Kubernetes control plane・etcd | **停止中（2026-09-12 12:46にrootが正常停止）**。kubeadm 1.36.4、Cilium 1.20.1 |
| 210 | k8s-worker-01 | 192.168.10.209 | Kubernetes worker（AWX・クラウドなど） | **停止中（同日12:46）**。join 済み |
| 211 | k8s-worker-02 | 192.168.10.208 | Kubernetes worker（予備） | **停止のまま**。`tools/k8s up --all` で起動し `--limit k8s-worker-02` で join |
| 400 / 401 | dev-a / dev-b | .202 / .203 | 開発VM。dev-b が自動化の実行ホスト | 稼働。RAMは各6GiB（下限2GiB。2026-09-12に宣言を実機へ同期） |
| 900 | probe-01 | 192.168.10.201 | 検証用 | **停止中**。未使用時は停止対象（2026-09-12時点） |
| 5000 | i-a086e5d5c8d7fa02a（win11pro） | 192.168.10.100 | クラウド利用者VM（`ruruthegeek`、Windows 11、ISOインストール検証） | **停止中** |
| 5002 | monitor-01（i-2193bd70bacdd1602） | 192.168.10.102 | Prometheus・Alertmanager・Grafana・exporter（M01） | 稼働。`https://grafana.apextox.dpdns.org`（`:3000`・`:9090` は 127.0.0.1） |
| — | net-01（i-88933be43f442c6f4） | 192.168.10.103 | Tailscale subnet router（N02。宅外から管理LANへの復旧経路） | 稼働。**Tailscale参加済み**（tailnet `100.91.7.69`）。**ルート承認済み・tailnet DNS=AdGuard Home（`overrideLocalDNS`、2026-10-01）**。宅外端末での実機検証が未了。[net.md](net.md) |
| 5997 | shakecloud-volumes | — | ボリュームのホルダー（デタッチしたディスクの待機先）。起動しない | 停止。API が初回のボリューム作成時に作る |

I01（2026-09-12）の実測・軽量化の結果は[配分と運用設計](../architecture/operations.md#measured-budget)にあります。この表の停止状態は再開すると変わります。通常の再開は容量確認後に `tools/k8s up` でcp・worker-01を起動します。`--all` は停止中のworker-02も含むため、追加の容量確認と配置計画が必要です。

2026-09-22に、Proxmoxホスト直結の6TB USB HDD（`/srv/bulk`、ext4、ラベル `bulk6tb`）を、media-01（`/srv/media-stack/library`）とgame1（ROM原本・セーブ）へNFS共有しました。Tier1 VM（101・110・130・140・150・401・5001・5002）の週次vzdumpは毎週日曜06:00・snapshot・zstd・keep-last=4で `/srv/bulk/backups` へ取り、game1のセーブは `tools/game1-saves-backup.sh` で別途取ります。手順と限界は[共有バルクストレージ](bulk-storage.md)・[バックアップ](backup.md)が正本です。

ゲストのタイムゾーンは**`Asia/Tokyo` に統一します**。`platform/ansible/roles/common/defaults/main.yml` の `common_timezone` を `Asia/Tokyo` へ修正しました（2026-09-17）。services-01・identity・cloud-01・storage-s3・dev-a・media-01 は JST です。dev-b は次回の配備、停止中の k8s ノード・probe-01 は次回起動時の配備で揃います。**`eufy-security-ws` のアプリログ行だけは UTC 表示です**（アプリ実装のため。コンテナの `TZ` は `Asia/Tokyo`）。

`cloud` プールにあるのは、ボリュームのホルダー（5997）と、引き取った game1（VMID 100。プール所属はVMIDの範囲に依らない）です。利用者VMを新規作成すると 5000–5999 から採番し、game1 の 100 は使いません。IP の帯は `platform/terraform/network.yaml` が正本で、機器帯 `.2`–`.19`（ルータ・AP・プリンタ・Proxmoxホスト）、DHCP `.20`–`.99`（router-01 の dnsmasq が配る）、クラウド用 `.100`–`.180`、管理用 `.201`–`.239`、MetalLB `.240`–`.249` に分けています。game1 の `.127` は NetBox に予約登録してあり、新規VMには払い出されません。

## 4. サービスの入口とログイン情報の置き場所

**パスワードそのものはここに書きません。** 置き場所と、取り出し方だけを書きます。

| サービス | 入口 | ログイン名 | 資格情報の置き場所 |
| --- | --- | --- | --- |
| Proxmox の画面 | `https://pve.apextox.dpdns.org:8006`（証明書は Let's Encrypt。IP `192.168.10.10:8006` でも入れるが、名前が一致しないので警告が出る） | `root`（Realm: Linux PAM） | `platform/sops/proxmox-root.sops.yaml` の `PROXMOX_VE_PASSWORD`（ACME アカウントの作成に要るので入れた） |
| Proxmox の画面（開発者） | 同上 | `dev-a@pve` / `dev-b@pve`（Realm: Proxmox VE） | `platform/sops/pve-users.sops.yaml` |
| Proxmox ホストへの SSH | `root@192.168.10.10` | 鍵のみ | **dev-b の鍵は登録されていない**（2026-09-10 に拒否を確認）。入れる鍵は人が管理している。API なら root トークン（`proxmox-root.sops.yaml`）で届く |
| NetBox | `https://netbox.apextox.dpdns.org` | `admin` | services-01 の `/opt/netbox-stack/secrets/superuser_password` |
| NetBox API | `http://192.168.10.200:8000/api/`（ツールの接続先。`https://netbox.apextox.dpdns.org/api/` でも届く） | トークン | 書き込み: `netbox.sops.yaml`、読み取り: `netbox-inventory.sops.yaml`、クラウドAPI用: `cloudapi.sops.yaml` |
| Authentik | `https://auth.apextox.dpdns.org` | `akadmin` | identity の `/opt/identity-stack/secrets/bootstrap_password` |
| Homarr | `https://homarr.apextox.dpdns.org` | Authentik（`users`は閲覧、`admins`は編集） | SSO。ローカル復旧は services-01 の `/opt/homarr-stack/secrets/admin_password` |
| Grafana | `https://grafana.apextox.dpdns.org` | Authentik（`admins`=Admin、`users`=Viewer） | SSO。ローカル復旧は monitor-01 の `/opt/monitoring-stack/secrets/grafana_admin_password` |
| LibreSpeed | `https://speed.apextox.dpdns.org` | 不要（LAN内） | 履歴の統計ページ（`/results/stats.php`）は services-01 の `/opt/services/librespeed/secrets/stats_password` |
| クラウドのポータル | `https://cloud.apextox.dpdns.org` | Authentik のアカウント（`users` か `admins`） | Authentik 側。`akadmin` は `admins` に入っている |
| クラウドAPI（Terraform・CLI・curl） | `https://cloud.apextox.dpdns.org/v1/` | アクセスキー | 利用者の分はポータルで発行（表示は一度だけ）。管理用ブートストラップキーは 2026-09-11 に無効化（§5 Phase 5）。緊急時は cloud-01 で `manage.py rotate-bootstrap-key` |
| 開発VM への SSH | `debian@192.168.10.202` / `.203` | パスワードまたは鍵 | `.local/devvm-passwords.yml`（**devbox の playbook を実行した作業機の手元にだけある平文**。dev-b には無い） |
| 基盤VM への SSH（services-01、identity、cloud-01、probe-01） | `debian@<IP>` | 鍵のみ | 鍵は `platform/terraform/access.yaml`。dev-b からは `~/.ssh/id_ed25519_pve` |
| Terraform の state | Cloudflare R2 | アクセスキー | `platform/sops/s3.sops.yaml` |
| DNS（`apextox.dpdns.org`） | Cloudflare ダッシュボード（ゾーンID `112734e967c919ddd9ec1fa5c4f2a320`） | 所有者の Cloudflare アカウント | 証明書用のトークン（このゾーンの DNS 編集だけ）: `platform/sops/cloudflare-dns.sops.yaml` |
| ドキュメントサイト | `https://docs.apextox.dpdns.org` | 不要（LAN 内に公開） | 資格情報なし。原稿は Git の `docs/`、配備は `platform/ansible/docs-site.yml` |
| Home Assistant | `https://ha.apextox.dpdns.org` | Authentik（`users` / `admins`）または緊急用のローカルオーナー | HA 自身の config（`/srv/services/home-assistant/config`）。**`manage.py backup` は sudo で実行**。長期アクセストークンは `platform/sops/home-assistant.sops.yaml` |
| Eufy Security（eufy-security-ws 3.1.0） | `eufy-security-ws:3000`（HA の Docker ネットワーク内だけ。LAN 非公開） | Eufy アカウント | `platform/sops/eufy-security.sops.yaml`（`EUFY_USERNAME`・`EUFY_PASSWORD`・`EUFY_COUNTRY`・`EUFY_TRUSTED_DEVICE_NAME`・`EUFY_STATION_IP_ADDRESSES`）。セッションは `/srv/services/eufy-security-ws/data`。「No houses」が出たら `manage.py reset-session` |
| SwitchBot Cloud（Hub Mini 経由） | HA の「設定 → デバイスとサービス」 | SwitchBot アカウント | トークンとシークレットは HA の config entry にだけ保存（Git・SOPS には置かない） |

VM の中にある値の取り出し方（dev-b で実行）:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.200 sudo cat /opt/netbox-stack/secrets/superuser_password
```

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.204 sudo cat /opt/identity-stack/secrets/bootstrap_password
```

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.205 sudo cat /opt/cloud-stack/secrets/bootstrap_admin_key
```

**cloud-01 の `bootstrap_admin_key` は 2026-09-11 に無効化済みで、通常は空です**（緊急時は `manage.py rotate-bootstrap-key`。[決定ログ](../architecture/decisions.md)・[cloud-api.md 3-8](cloud-api.md)）。

SOPS の値の取り出し方:

```bash
sops --decrypt platform/sops/pve-users.sops.yaml
```

## 5. 進捗とTODO

✅ 済み ⬜ 未着手 🟨 途中 👤 人の手が要る

### Phase 0 — 土台

| 状態 | 作業 | メモ |
| --- | --- | --- |
| ✅ | `00-bootstrap` 適用（`cloudapi@pve`、ロール4種、ACL、`cloud-images` ストレージ） | [クラウドAPIの構築](cloud.md) |
| ✅ | 実機プローブ4つ（空き容量、ISO の上げ下ろし、プール境界、noVNC） | すべて PASS。`tools/verify-cloud.py` |
| ✅ | `10-platform` 適用（identity、cloud-01、NetBox の IP Range） | 再 plan で差分なし |
| ✅ | NetBox の書き込みアイデンティティ `cloudapi` | `virtualization` と `ipam` にだけ書ける。実測済み |
| ✅ | NetBox の LAN 公開 | `platform/ansible/roles/netbox` |
| ✅ | Authentik の新規構築、`users` / `admins`、OIDC クライアント `cloud` | `stacks/identity/`、`platform/ansible/identity.yml`。再実行で変更ゼロ |
| ✅ | ドメイン `apextox.dpdns.org` を取得し、DNS を Cloudflare へ委任 | 2026-09-10。ゾーンは有効、レコードはまだ無い。DNS 編集トークンは SOPS に格納し、動作を確認済み |
| ✅ | 名前を決めて HTTPS にする（Authentik・ポータル・API・NetBox・ドキュメントサイト） | 2026-09-10。Terraform `20-dns` と各ホストの Caddy。証明書は Let's Encrypt。Authentik と API の平文ポートは 127.0.0.1 に閉じた。[cloud.md 3-9](cloud.md) |
| ✅ | Proxmox 本体の証明書（`pve.apextox.dpdns.org`） | 2026-09-10 に取得（Let's Encrypt、`CN=pve.apextox.dpdns.org`、期限 12/9）。ACME アカウント・Cloudflare プラグイン・証明書のすべてを `00-bootstrap` の `acme.tf` が作る。**ACME アカウントの作成だけ API トークンでは通らない**（root のトークンでも `user != root@pam`）ので、`proxmox-root.sops.yaml` の `root@pam` のパスワードで ticket 認証に切り替えて流す（`tools/tf` が自動で判断）。**画面での手作業は無い** |
| ⬜ | NetBox を使うツール（Terraform・Ansible・クラウドAPI）の接続先を `https://netbox.apextox.dpdns.org` へ移し、`:8000` と `:8090` を閉じる | `netbox.sops.yaml`・`netbox-inventory.sops.yaml`・`cloudapi.sops.yaml` の URL を変える |
| 🟨 | 外出先（Tailscale）から名前で使えるようにする | **2026-09-14: 復旧経路の subnet router `net-01`（`192.168.10.103`）を作成し、Tailscaleへ参加済み（`100.91.7.69`）**（N02・[net.md](net.md)）。**2026-10-01: ルートを承認し、tailnet DNS を AdGuard Home（`192.168.10.1`）+ `overrideLocalDNS` に設定**（`tools/tailscale-net.py`）。SERVFAIL の原因は global nameserver 未設定だった。dev-b で公開名・内部名・遮断・MagicDNS を実測済み。**宅外のスマホ実機での確認が未了** |
| ✅ | OIDC クライアントの秘密値を cloud-01 へ渡す | SOPS へ入れる予定だったが、identity VM から直接写す方式に変えた（[決定ログ](../architecture/decisions.md)） |
| ✅ | Authentik での利用者の作り方（招待フロー） | identity サービスの `stacks/identity/invitations.py`（`configure`/`invite`/`list`/`revoke`、標準ライブラリのみ）。**招待専用フロー・1回限り・24時間・`users` へ**。**メール送信に対応**（`smtp.sops.yaml` の `SMTP_*` を `.env` 経由で読み、現在は Gmail。無ければリンクを 0600 で保存）。配備（`identity.yml`）で `configure` が走る。実機確認済み（[identity.md](identity.md)・[cloud-resources.md 3-17](cloud-resources.md#3-17)・[smtp.md](smtp.md)） |
| ✅ | データセンターのファイアウォール有効化 | Phase 4 の前提。`platform/terraform/00-bootstrap/firewall.tf` で安全に自動化し、**2026-09-11 に適用済み**（再 plan は No changes）。ノードFWは無効、DC FWは有効・既定ACCEPT、`nf_conntrack_allow_invalid=1`。既存の基盤VM・game1 への通信に影響がないこと、`nf_conntrack_allow_invalid=1` が入っていることを実機で確認。次に触る場合は物理コンソール/IPMI を用意する |
| 🟨 👤 | VLAN 工事（ルータ、スイッチ、`vmbr0` を VLAN 対応に） | 物理機器の作業を含む。**宣言と安全装置・手順書は用意済み**（`network.yaml` の `vlan`、`managed-host` と `site.Validate` の precondition、[vlan.md](vlan.md)）。実機切替は人の物理作業待ち |

### Phase 1 — Go の足場、認証、監査ログ

| 状態 | 作業 | メモ |
| --- | --- | --- |
| ✅ | `cloud/openapi/shakecloud.yaml`（API の正本） | ルート表との一致を `routes_test.go` が検査 |
| ✅ | `cloud/api/`: HTTP、設定、PostgreSQL 接続とマイグレーション、`/healthz` | マイグレーションは `internal/db/migrations/`。起動時に advisory lock 下で適用 |
| ✅ | OIDC ログイン（Authentik）と、アクセスキーの発行・一覧・失効 | state のブラウザ束縛・nonce・PKCE。偽の OIDC プロバイダで本物のコードを通すテストあり |
| ✅ | 監査ログ | 追記専用（トリガーで UPDATE/DELETE/TRUNCATE を拒否）。`GET /v1/audit-events` |
| ✅ | 開発用のブートストラップ管理キー | `manage.py rotate-bootstrap-key` / `disable-bootstrap-key` |
| ✅ | Phase 1 の最小ページ（ログイン、キーの発行・削除、操作履歴） | `html/template` と素の JS。ビルド基盤なし。Phase 5 で置き換える |
| ✅ | `cloud/compose.yaml` と `cloud/manage.py`（既存スタックと同じ作法） | API のイメージは cloud-01 でビルド。ベースイメージは Dockerfile で digest 固定 |
| ✅ | Ansible ロール `cloud_api` と `platform/ansible/cloud.yml` | 2026-09-10 に配備。再実行で変更ゼロ |
| ✅ | CI に Go を追加（`gofmt -l`、`go vet`、`go test ./...`、PostgreSQL サービス） | `validate.yml`。2026-09-11 に push して GitHub 上で初めて実行し、`push` と `pull_request` の両方で成功した |
| ✅ | 実際のブラウザで Authentik ログインを1回通す | 2026-09-10 に `akadmin` で確認。監査ログに `CompleteLogin`（アカウント作成、管理者）、`CreateAccessKey`、`DeleteAccessKey` が残った |

実機で確かめたこと（2026-09-10、dev-b から）:

| 確認 | 結果 |
| --- | --- |
| `/healthz` | 200 |
| `/auth/login` | Authentik の authorize へ 302。`redirect_uri`・PKCE（S256）・scope が正しく、Authentik はエラーでなくログイン画面へ進んだ |
| ブートストラップ管理キーで `GET /v1/caller-identity` | 200、`bootstrap-admin`（管理者） |
| アクセスキーで `POST /v1/access-keys` | 403 `UnauthorizedOperation` |
| 秘密値だけ違うキー | 401。監査ログに `AuthFailure`（`secret_mismatch`） |
| セッションなしの一覧、クロスサイトの POST | 401、403 `CrossOriginRequestBlocked` |
| `cloud.yml` の再実行 | `changed=0` |

### Phase 2 以降

| 状態 | Phase | 内容 |
| --- | --- | --- |
| ✅ | 2 | **VMが1台できる縦串**。2026-09-10 に実機で確認（作成 → SSH でログイン → 削除 → 残骸なし）。冪等性（`client_token`）、クォータと空き容量、VMID の採番と隔離、NetBox での IP 採番、seed ISO、一覧・電源操作・Terminate、差分リコンサイラを含む。[cloud.md 3-10](cloud.md) |
| ✅ | 2 の追加 | **上限を管理者が変えられるようにし、容量が見えるようにした。**`GET /v1/capacity`（CPU・メモリ・ストレージ・配った合計・アカウント別）、`GET`/`PUT /v1/limits`、ポータルの「容量」と「上限」。16GiB の `2xlarge` を追加。2026-09-10 に実機で確認（上限の上書きと復帰、16GiB の VM が `balloon=4096` で起動 → 削除して残骸なし、監査ログに記録）。[cloud-api.md 3-11](cloud-api.md#3-11) |
| ✅ | 2 の追加 | **大きさを自由に指定できるようにし、GUI に一覧と編集を出した。**`vcpus`・`memory_mib`・`memory_min_mib`・`ballooning`・`root_disk_gib` を直接指定（`instance_type` は任意の近道）。`PATCH /v1/instances/{id}`（管理者のみ）。ポータルの「インスタンス」で作成・電源・削除・編集ができ、**クラウドの全VMが所有者名つきで並ぶ**。2026-09-11 に実機で確認（バルーニングなしで `balloon=0`、稼働中のディスク拡大、縮小の拒否、停止後の vCPU・メモリ・バルーニング変更が実物に反映、削除して残骸なし）。[cloud.md 3-10](cloud.md) |
| ✅ | 3 | **イメージのアップロード、SSH鍵ペア、Webコンソール。**2026-09-11 に実機で確認。本物の qcow2 が入って消え、フィンガープリントは `ssh-keygen -lf` と一致し、`user_data` なしで SSH ログインできた（`meta-data` の `public-keys`）。コンソールは API を通した WebSocket の最初のフレームが VM の VNC サーバからの `RFB 003.008` だった（noVNC 1.7.0 を同梱、中継は API）。**ブラウザで画面が描かれるところは、人がポータルから開いて確かめる**。[cloud-api.md 3-12](cloud-api.md#3-12)・[3-13](cloud-api.md#3-13) |
| ✅ | 4 | **ボリュームとセキュリティグループを実装し、2026-09-11 に実機で確認。** `cloud/api/internal/compute/{volumes,volume_worker,securitygroups,firewall}.go`、DBマイグレーション `0006`、API エンドポイント、ポータル画面、Terraform の DC FW 有効化まで含む。実機では `volume_reassign`・`vm_firewall` プローブが PASS、ボリュームの作成→アタッチ→ゲストで `/dev/disk/by-id/virtio-<serial>` 認識→拡張→デタッチ→削除が通り、SSH のみ許可した SG で 8000 番と ICMP が遮断・許可ルール追加で回復した。残骸なし。**検証中に見つけた「ルール変更で Proxmox が live ruleset を再構築しない」バグを修正**（`setFilteredOptions` を毎回書く。[はまりどころ](verify.md)参照）。再現は `tools/verify-volumes.py`（`tests/test_verify_volumes.py` が判定を検査） |
| ✅ | 5 | **セルフサービスポータルを完成させ、ブートストラップ管理キーを無効化（2026-09-11）。** ポータルはVM・ボリューム・SG（受信/送信ルール）・イメージ・SSH鍵・アクセスキー・容量・上限・操作履歴を扱え、古い文言も直した。既存VMの引き取りも実装し、**game1（VMID 100）を `shunyazhiyuan97` として引き取り済み**（`i-bec54e3a0169b3660`、IP `192.168.10.127` を NetBox に予約）。ブートストラップ管理キーは無効化し、以後はポータル発行のアクセスキーを使う（緊急時は `manage.py rotate-bootstrap-key`） |
| ✅ | 6 | **CLI と Terraform Provider を実装・実機確認（2026-09-11）。** CLI（`cloud/client`・`cloud/cli`）は identity・capacity・limits・events・instance・volume・sg・image・key・access-key を操作。Provider（`cloud/provider`、`terraform-plugin-framework`）は `shakecloud_instance`・`shakecloud_volume`・`shakecloud_volume_attachment`・`shakecloud_security_group`・`shakecloud_security_group_rule`・`shakecloud_key_pair` と `shakecloud_caller_identity`。実機で apply/plan‑no‑changes/import/destroy を確認。[CLI](cli.md)・[Provider](terraform-provider.md) |
| ✅ | 7 | **Garage を storage-s3 VM（VMID 130、.206）へ単一ノードで構築し、バケット・S3キーを扱うクラウドAPIを実装（2026-09-11）。** データは専用32GiBディスク。API の `POST /v1/buckets`・`POST /v1/s3-keys`・権限の付与/剥奪で Garage の管理API v2 を操作する。CLI に `bucket`・`s3-key`、**Terraform Provider に `shakecloud_bucket`、ポータルに「S3バケット」画面**（作成・キー権限・S3キー発行）を追加。**実クライアント（awscli）で、APIが発行した鍵を使い PUT/LIST/GET/削除まで確認**。Garage 自体は [garage.md](garage.md)、APIは [cloud-resources.md 3-16](cloud-resources.md#3-16) |
| 🟨 | 8 | **切替の宣言・安全装置・手順書を用意（2026-09-11）。** `network.yaml` の `vlan`、`10-platform` がそこから管理VLANを読む形、`managed-host` と `site.Validate` の「bridge が vlan-aware でないのに vlan_id を設定したら止める」precondition、API が作るVMへのタグ付け、[vlan.md](vlan.md) の段階手順とロールバック。**実機切替は物理スイッチ/ルータと Proxmox bridge の作業待ち** |
| ✅ | Windows | **Windows 11 Pro の VM をポータルから作れるようにした（2026-09-12）。** 2経路ある。(1) **ISO方式**: `POST /v1/isos` で `.iso` をアップロード（`os: windows` 対応、`GET`/`DELETE /v1/isos`）、`RunInstances` の `install_iso_id`／`driver_iso_id` で空ディスク＋CD-ROM起動し、コンソールでインストール。(2) **共有イメージ方式**: `images.yaml` の `os: windows`・`provided: true` で、API が UEFI（OVMF）・TPM 2.0・q35 の VM を作る。どちらも Windows なら SSH鍵欄を隠しコンソールを案内。Proxmox 実機の `windows_devices` プローブと既存プローブは全 PASS。`go test ./...`（dev-b PostgreSQL）・ポータルの実ブラウザ検証も通過し、**cloud-01 へ配備済み**。**2026-09-12 に Proxmox `local` のISO 5本を `cloud-images` へ移動して台帳へ登録**（`mv` なので複製なし）。ポータルの「ISO」に全員共有で並び、アップロードしたものは誰でも削除できる。`local` に後から置いたISOも宣言なしで自動一覧される | [windows.md](windows.md) |
| 🟨 | K8s | **スライス①〜⑦を実機で確認（2026-09-12）。** cp-01 と worker-01 が **Ready**、Cilium 1.20.1 が kube-proxy を置換、PVC 永続化・MetalLB・cert-manager・Flux 2.9.5 + SOPS の GitOps 同期まで動作。**AWX 24.6.1 を Flux で配備し `https://awx.apextox.dpdns.org/`（Let's Encrypt）で公開**。**CloudNativePG（`database`）と Knative（`function`）を API・Provider・CLI まで実装し、作成〜Ready/healthy〜削除を実機確認**（SA `databases/cloud-api` の最小 RBAC）。k8s ノードのバルーニングは無効化。**クラウドの4機能（VM・S3・DB・関数）が API・Provider・CLI・ポータルまで揃った**。関数 URL は DNS・**HTTPS**（namespace ワイルドカード証明書）済み。次は CNPG バックアップと VLAN | [kubernetes.md](kubernetes.md) |
| ✅ | media | **media-01 を cloud VM として作成し、実機確認済み（2026-09-12、I02）。** `i-a06df9a2dfd1ce6db`・`192.168.10.101`、データディスクは `/srv/media-stack` へマウントし、Nextcloud・Kavita・Navidrome・MeTube・Picard を Caddy（HTTPS・SSO）経由で配備・応答確認済み（[I02](../development/I02-media-vm.md#handover-log)）。Nextcloud は Notes を追加し、旧Androidカレンダー884件を移行済み（[W03](../development/W03-nextcloud.md#handover-log)）。音楽は全曲レビュー（`https://navidrome.apextox.dpdns.org/review/`）を配備し、作曲者・アルバム・東方本編・カバーのタグ整備を進行中で、日付つきの作業ログは[W06](../development/W06-music-tools.md#handover-log)にある。**未完**: 既存環境からのデータ移行とブラウザでのログイン実測（W03〜W06。RomMはgame1側でW07）、アルバムカバー未設定の8枚（KHに該当リリースなし）、タグ未整備の音楽（自己名義・未確認の約70曲ほか。東方の曲名の残りは W06 の作業記録を参照）。 | [I02](../development/I02-media-vm.md)・[W03](../development/W03-nextcloud.md)・[W05](../development/W05-navidrome.md)・[W06](../development/W06-music-tools.md) |
| 🟨 | H01 | **Home Assistant Containerをservices-01へ配備（2026-09-12）。** `stacks/home-assistant/`（Compose・`manage.py`・テスト）と `platform/ansible/home-assistant.yml`、イメージはdigest固定。`/opt/services/home-assistant`・`/srv/services/home-assistant/config`、`127.0.0.1:8123`、既存Caddyで `https://ha.apextox.dpdns.org`（Let's Encrypt、未認証は302）。HA 2026.9以降はHTTP設定が `.storage/http` の `stable` で、YAML取り込みはUI承認待ちの`pending`（5分で撤回）にしかならないため、`manage.py ensure-http-proxy` で `trusted_proxies`（compose固定サブネットのゲートウェイ `172.31.254.1`）を直接反映。コンテナ再起動後のhealthy復帰を確認。**SSO（2026-09-12）**: identityが公開OIDCクライアント `home-assistant`（`redirect_uri https://ha.apextox.dpdns.org/auth/oidc/callback`、`sub_mode user_uuid`、`users`/`admins`バインド）を冪等に作成し、HAは `hass-oidc-auth` v1.2.1をdigest固定で導入、`configuration.yaml` の `auth_oidc` 管理ブロックでAuthentikログインを併設（discovery 200・authorize 302を確認）。**Eufy（H04）**: `stacks/eufy-security-ws/`（3.1.0）と `platform/ansible/eufy-security-ws.yml` を services-01 へ配備し、`platform/sops/eufy-security.sops.yaml` の資格情報でログイン・デバイス一覧・Push まで動作。`eufy_security` v8.2.4 も HA へ導入済み。**ライブ映像は S4 の新 WebRTC 方式のため不可**（詳細は H04 行）。**SwitchBot Cloud（H02）**: Hub Mini 経由のクラウド統合を追加し、鍵・ドアセンサー・赤外線家電のエンティティを確認。**Alexa/Echo（H03）は見送り（2026-09-12）**。サービス（HA・eufy-security-ws）の `TZ` は `Asia/Tokyo`。バックアップと復元試験は未完 | [H01](../development/H01-home-assistant.md) |
| ✅ | H02 | **SwitchBot Cloud 統合（Hub Mini 経由）を追加（2026-09-12）。** HA の「設定 → デバイスとサービス → 統合を追加 → SwitchBot Cloud」で設定し、鍵・ドアセンサー・赤外線家電のエンティティを確認。資格情報（トークン・シークレット）は **HA の config entry にだけ保存**し、Git・SOPS には置かない。ローカル Bluetooth は未使用（USB ドングル未装着） | [H02](../development/H02-switchbot.md) |
| ✅ | H03 | **Echo/Alexa 連携は見送り（2026-09-12 決定）。** Home Assistant Cloud の契約も独自 Skill の公開入口も作らない。SwitchBot・Eufy は各社の Alexa スキルで操作できる。材料は計画書に残す | [H03](../development/H03-echo.md) |
| 🟨 | H04 | **Eufy S4のライブ映像は現行の公開ソフトでは不可能と実機で確定（2026-09-13。リバースエンジニアリング）。** イベント・push・スナップショットは配備済みの `eufy-security-ws` + `eufy_security` で維持し、人物・動体イベントがHA（`binary_sensor.rihinku_person_detected`/`_motion_detected`）まで届くことを2026-09-23に実機確認した。S4（T8172）のライブは新 leo_rtc WebRTC バックエンド専用で、公開実装は未対応。イベント画像は単体S4では取得不可。**未完**: ライブ映像は単体ライブの自前実装として H05 へ切り出して継続中（根拠・検証経路・追試の詳細は[H04の作業記録](../development/H04-eufy.md#handover-log)）。 | [H04](../development/H04-eufy.md) |
| 🟨 | H05 | **単体S4のライブをネイティブ leo_rtc で自前実装中（2026-10-02 更新）。** services-01 の `stacks/eufy-leo-rtc/`（mediamtx＋leo-live、HA と同ホスト）。HA は Generic Camera `camera.eufycam_s4_leo_rtc`（`rtsp://172.31.254.1:8554/eufy`＋`http://172.31.254.1:8888/snapshot.jpg`）と MJPEG `camera.eufycam_s4_mjpeg`。**2026-10-02 の修正: KCP ワイヤ形式（32B接頭辞＋20Bヘッダ）と ICE-CONTROLLED の compose 渡し漏れ**で 1 セッション 20〜24 秒（修正前は 4〜13 秒）。同一セッション内の映像復帰は 1003 再送（メディア/KCP・60 秒粘り）でも不可、並行セッションは可能でも短間隔の連続起床はカメラに無視される（バックオフ必須）。relay が合間を最終フレームで埋める。**未完**: アプリの「何時間でも」の連続性（直結は 20 秒で停止。詳細は H05-ha-live-request §9）。 欠落ゼロの全編クリーンな実映像のデコードと、音声（AAC）を含む Mediamtx への RTSP 配信を実現し、HA には Generic Camera として反映済み（HA 用は音声なし、`eufy_av` に映像＋音声）。`tools/live_supervisor.sh` がセッションを繰り返し、オンデマンド wake と夜間（1〜6 時 JST）の間引きを入れている。**未完**: 捕捉ストールの除去、セッション維持（0xce レポートの自前生成）、Mediamtx 配備（カメラ側の都合で数十秒〜数分で止まる）。上流移植は `feat/leo-rtc-s4`（ローカル・push なし）。既存イベント・Push は維持。実測・鍵とフレームの詳細は[H05の作業記録](../development/H05-eufy-leo-rtc.md#handover-log) | [H05](../development/H05-eufy-leo-rtc.md) |
| ✅ | W02 | **Vaultwardenをservices-01へ新規構築（2026-09-12）。** 実データが無いため移行せず、`stacks/vaultwarden/` の独立Compose（`vaultwarden/server:1.37.3`・digest固定・`127.0.0.1:8222`・`/srv/services/vaultwarden/data`・`secrets/admin_token` 0400）として配備。`https://vault.apextox.dpdns.org`（Let's Encrypt）で受け、identityにOIDCクライアント `vaultwarden`（redirect `https://vault.apextox.dpdns.org/identity/connect/oidc-signin`、`users` binding）を作成。`/alive` 200、一般登録は無効（登録APIが400、usersは0件）。Web UIに「Create account」が出る件は、Vaultwardenの`is_signup_disabled()`が`INVITATIONS_ALLOWED`既定trueだとfalseになるためで、`INVITATIONS_ALLOWED=false`を追加して非表示にした（`/api/config`の`disableUserRegistration=true`を実測）。**2026-09-14: ブラウザーSSOで保管庫作成まで実測。** 「毎回マスターパスワード設定の新規登録画面」は、①ブラウザーに残った管理用`akadmin`のAuthentikセッションでSSOしていた（`auth_via=session`・Vaultwardenの`users`に`shake.notify@gmail.com`/`password_hash`空）②1.37.1/1.37.2のマスターパスワード設定422（`missing field newMasterPasswordHash`）が原因。**1.37.3へ更新**し、不要な`akadmin`保管庫を削除（以後`ruru2028@gmail.com`の1件）。本人はAuthentikからサインアウトかプライベートウィンドウで自分のメールを入れてSSOする | [W02](../development/W02-vaultwarden.md) |
| ✅ | I03 | **クラウドVMをAnsibleの配備対象にした（2026-09-12）。** `platform/ansible/inventory.cloud.py`（実行のたびに `GET /v1/instances` を読む読取専用の動的inventory、`--list`/`--host`、失敗時は非0でキャッシュ不使用）と `cloud-inventory.yml`（account_idとID→グループの宣言）。実キー（管理者ではない）で `account_id=934162309796` を確認。`ansible-inventory --graph` は `media` 群へ `i-a06df9a2dfd1ce6db` だけを出し、`ansible -m ping` は `pong`、`docker --version` は成功。`ansible_user=debian` を付与。**基盤NetBox inventoryと併用しない**（`media` 群が和集合になる）。AWX組込みはI06 | [I03](../development/I03-cloud-inventory.md) |
| ✅ | D08 | **Nextcloudのファイル一覧から直接印刷できるようにした（2026-09-13）。** ストアの印刷アプリはNC33非対応でNextcloudコンテナへのCUPSクライアント追加が前提のため、自作アプリ `shake_print`（Filesの「…」→「印刷」。PDF・PNG・JPEG・テキスト、今は1部・カラー固定）を `stacks/media/nextcloud/apps/shake_print/` に作り、イメージ固定のままhtmlボリュームの `custom_apps` へ配備（`platform/ansible/media-nextcloud.yml`。`occ config:app:set` でURLとトークンを設定）。services-01には `stacks/print-api/`（`print_api.py`・systemdユニット、`:6320`、トークン認証＋media-01のみ、最大50MiB）をCUPSロールが配備。トークンは `platform/sops/print-api.sops.yaml`。実機で `print-api` active・`/healthz` 200・キューidle、`occ app:list` に自作3アプリ（`shake_print`・`shake_localsend`・`shake_tags`）の `1.0.5`、**media-01→API→CUPSで `ts8430-2` が完了し1枚印刷**。**ブラウザー実測で `/books` のPDFに「印刷」「LocalSendで送る」、`/music` のMP3に「タグを編集」「LocalSendで送る」が出て、「タグを編集」はエディタ起動＋タグAPI 200まで確認（一般ユーザー）**。途中、`info.xml` の `<namespace>` 欠落（二重include）に加え、NC33の `@nextcloud/files` v4 グローバルレジストリ未使用・`extension` のドット込み・`#[NoAdminRequired]` 欠落（一般ユーザー403）を修正しテスト化 | [D08](../development/D08-nextcloud-print.md) |
| ✅ | M01 | **monitor-01 を cloud VM として作成し、監視スタックを配備（2026-09-12）。** Prometheus・Alertmanager・Grafana・blackbox/node/pve/nut exporter を `stacks/monitoring/`・`platform/ansible/monitoring.yml`・`platform/terraform/services/monitor` で構築。`https://grafana.apextox.dpdns.org`（identity OIDC。`admins`=Admin / `users`=Viewer）、全24ターゲットup・UPS取得・メール通知1通を実機確認。**2026-09-16〜23: HomarrのProxmox/PeaNUT連携、node資源・バックアップ・UPSのアラート、dead man's switch、低電池シャットダウンまで実機確認。VMメモリ・ゲーム使用量・ホスト（I/O・温度・SMART）・ストレージ（6TB HDD・NVMe）のダッシュボードとアラートを追加し、Proxmoxホストへnode_exporterとSMART/NVMeのtextfile collectorを導入した。** | [M01](../development/M01-monitoring.md) |
| ✅ | LibreSpeed | **端末↔services-01の実効速度テストをservices-01へ配備（2026-09-21）。** `stacks/librespeed/`（単独Compose・digest固定・`127.0.0.1:8300`・`/srv/services/librespeed`・`secrets/stats_password` 0400）、ロール `librespeed`・`librespeed.yml`、`dns.yaml` の `speed` レコード、Homarrタイル、blackbox監視。統計パスワードは `manage.py init` が一度だけ生成 | [librespeed.md](../services/librespeed.md) |
| ✅ | ストレージ | **6TB USB HDD（WD60EZAX）をProxmoxホストでext4にし、media-01とgame1へNFS共有（2026-09-22）。** ホスト側は `pve_bulk_storage` ロール（`/srv/bulk`、`/etc/exports.d/bulk.exports`、all_squash）。media-01は `/srv/media-stack/library` へマウントし、マウント完了までDockerを起動しない。既存ライブラリ2812ファイル・12GiBをNFS経由で移行し、ファイル数とバイト数の一致を確認。**単一ディスクで冗長性は無い** | [bulk-storage.md](bulk-storage.md) |
| ✅ | HDDティア | **クラウドAPIに `disk_tier`（`ssd`＝既定 / `hdd`）を追加し、実機で確認（2026-10-03）。** HDD側は `pve_bulk_storage` ロールが `/srv/bulk/disks` を作り dir ストレージ `bulk-disks`（`content=images`、マウント確認後に登録）として追加。`00-bootstrap` が `CloudApiStorage` のACLを `/storage/bulk-disks` へ付与（`moved` で既存SSD ACLは作り直さず）。APIはインスタンスroot（WindowsのEFI/TPM含む）とボリュームの両方で `disk_tier` を受け、未知の値とHDD未設定デプロイは400、`GET /v1/capacity` の storage に `disk_tier` が付く。OpenAPI・client・CLI（`--disk-tier`）・Provider・ポータル・MCP・migration `0013`。**実機確認**: HDD VMが `virtio0: bulk-disks:5005/vm-5005-disk-0.qcow2` で起動し、HDDボリュームが holder 5997 の `unused0: bulk-disks:...raw` に作成、両方削除して残骸なし。**HDDは単一ディスク・USB・バックアップ/メディアと同居なので、`vm_disk_max_used_percent` はHDD全体の使用率で判定する。常用VM・DBにはssdを推奨** | [bulk-storage.md](bulk-storage.md)・[cloud-api.md](cloud-api.md) |
| ✅ | バックアップ | **Tier1 VMの週次vzdumpとgame1セーブを追加（2026-09-22）。** `pve_backup` ロールが `bulk-backup`（`/srv/bulk/backups`）を登録し、毎週日曜06:00・snapshot・zstd・keep-last=4。未マウント時は止まる。game1は `/home` 全体を取らず `tools/game1-saves-backup.sh` でセーブのみ。**同じ筐体・単一ディスクなので外部コピーは未着手** | [backup.md](backup.md) |
| 🟨 | W08 | **クライアント端末のバックアップを配備（2026-10-02）。** media-01 に `stacks/media/urbackup/`（`uroni/urbackup-server` digest固定、Web UI `127.0.0.1:55414`、クライアント `192.168.10.101:55413`、自動発見 `35623/udp`）を追加。6TB HDD の `/srv/bulk/client-backups` を `all_squash,anonuid=101` で media-01 だけへ export し、`/srv/media-stack/client-backups` へ NFS マウント（`RequiresMountsFor` に追加）。サーバー設定は `settings.json`＋`manage.py configure`（Web API）で冪等適用（`server_url`・`default_dirs=C:\Users`・`image_letters=C`・`internet_mode_enabled=false`）、管理者パスワードは `secrets/urbackup_admin_password`。SG に TCP 55413・UDP 35623、DNS に `backup`（ポータル）と `urbackup`（管理画面）、identity に Forward Auth プロバイダを追加（HTTPS は Authentik へ302）。**バックアップポータル**（`portal.py`＋`portal-web/`。UrBackup の状態・端末手順・USB接続のGalaxyをブラウザーから直接バックアップする WebUSB ボタン。保存先は HDD の `android/`）を追加。`media-verify` は全ユニット green、LAN から 55413 到達・55414/55415 閉を実測。**未完**: Windows実端末の初回バックアップとファイル/イメージ復元、Galaxy実端末での WebUSB バックアップ（写真・書類・APKの完走と2回目のスキップ）の実測、HDDの2次コピー | [W08](../development/W08-client-backup.md)・[client-backup.md](client-backup.md) |
| ✅ | storage | **journald上限・root noatime・Dockerログ上限を `storage_health` ロールで配備（2026-09-23）。** `storage-health.yml` がpve・サービスVMへ適用する。再実行してもnoatimeを重複追加しない | — |
| 🟨 | API | **アクセスキーに読み取り専用スコープを追加（2026-09-23）。** `access_keys.scope`（migration `0012`）とOpenAPIの `x-shakecloud-scope`、ポータルの権限選択、CLIの `SCOPE` 列。読み取り専用キーの書き込みは 403 `AccessDenied` として監査ログに残る。**cloud-01へ `cloud.yml` で配備済み（2026-09-23、failed=0）。** 実機の `GET /v1/caller-identity` が `access_key_scope` を返すこと（migration `0012` 適用）を確認。**ReadOnlyキーでの拒否確認はキー発行後** | [cloud-api.md](cloud-api.md) |
| 🟨 | MCP | **読み取り専用のMCPサーバ `cloud/mcp` を実装（2026-09-23）。** 22ツール（VM・ボリューム・SG・S3・DB・関数・監査の参照）。OpenAPIの `x-shakecloud-scope: read` との被覆をテストで検査し、DB資格情報と書き込みは公開しない。**dev-bでビルドし、opencode（`~/.config/opencode/opencode.jsonc`）へ `{file:}` 参照で登録済み。stdioの実機疎通（initialize・tools/list 22件・`get_caller_identity`）も確認済み。ReadOnlyキーでの拒否確認はキー発行後** | [mcp.md](mcp.md) |
| ✅ | mail-view | **Gmail通知メールの読み取り専用ビューアをservices-01へ配備（2026-09-26）。** `stacks/mail-view/`（標準ライブラリのみ・`python:3.13-alpine` digest固定・`127.0.0.1:8310`・read_only・cap_drop ALL）。IMAPは `imap.gmail.com:993` にアプリパスワードで入り `EXAMINE`（readonly）で**既読を付けない**。入口はCaddy Forward Auth（identityの `mail-view` プロバイダ、`users` 全員）で、未認証は `https://auth.apextox.dpdns.org` へ302。`mail-view.apextox.dpdns.org` をDNS登録、Homarrタイル追加、blackboxプローブup。実機で `/healthz` 200・IMAP取得50件を確認。資格情報は `platform/sops/smtp.sops.yaml` のアプリパスワードをIMAPと共用（IMAP有効化済みを実測）。**配備中にAnsibleの `copy` が `{{ "\n" }}` をリテラル2文字で書く問題を発見し、改行を書かない形へ修正・テスト化** | `stacks/mail-view/README.md`・[SMTPとメール送信](smtp.md) |
| ✅ | ポケモン翻訳 | **ポケモン用語を公式名に固定する翻訳サイトとブラウザ拡張機能を作り、翻訳サイトをservices-01へ配備（2026-09-27）。** **実装は同日に公開リポジトリ [rurutheGeek/poke-translate](https://github.com/rurutheGeek/poke-translate)（MIT、v1.0.0）へ切り出し**、ここはロール既定値の `poke_translate_version`・`_sha256` でリリースの `poke-translate-site-vX.Y.Z.tar.gz` を固定し、`get_url`（checksum）で取って `manage.py install` が `/srv/services/poke-translate/site` へ展開する方式（変わったファイルだけ置換、リリースに無いファイルは削除。初回方式の `pokeapi.json` と旧コードはロールが片付ける）。本体は `core/poketr.js` の1つで、翻訳サイトと拡張機能（Manifest V3、サーバ不要）が共用。辞書はPokéAPI（commit固定）＋`custom-terms.json`から公開リポジトリのリリースCIが生成する。翻訳は閲覧者のブラウザからGoogle翻訳の**非公式**エンドポイント（`client=dict-chrome-ex`）へ直接送るので、サーバは静的配信だけ（`python:3.13-alpine` digest固定・`127.0.0.1:8320`・read_only・cap_drop ALL、認証なし＝LAN内）。`poke.apextox.dpdns.org` をDNS登録、Homarrタイル・blackboxプローブを追加。実機で再実行 `changed=0`、HTTPSでページ・辞書・拡張機能zipの200、ブラウザで英→日の翻訳（じしん・まもる・ようき・エスパー無効）を確認。**配備中、identity VMのSSHホスト鍵が2026-09-26のハードリセット後に再生成されていたことを検出**し、ゲストエージェント経由でVM内の鍵と指紋一致を確認してから known_hosts を更新。非公式エンドポイントが遮断されたら `core/poketr.js` のエンジンを差し替える | [ポケモン翻訳](../services/poke-translate.md)・`stacks/poke-translate/README.md` |
| 🟨 | Nextcloudアプリ | **自作の印刷・LocalSend送信を公開リポジトリへ切り出し、App Store公開の準備をした（2026-09-26）。** `cups_print`（[nextcloud-cups-print](https://github.com/rurutheGeek/nextcloud-cups-print)）と `localsend_share`（[nextcloud-localsend](https://github.com/rurutheGeek/nextcloud-localsend)）を作成し、各 `v1.0.2` をGitHub Releaseで配布。media-01は `manage.py custom-apps` で導入し旧 `shake_print`・`shake_localsend` を撤去（残る自作は `shake_tags` のみ）。中継は `stacks/print-api`・`stacks/localsend-send` を同じ実装へ更新。**実機確認（NC33）**: 印刷はPDFとMarkdown、ダイアログ（部数・カラー・ページ範囲）、LocalSendは実端末へ送信成功。LocalSendはmulticast応答がSG（22/80/443/53317のみ）で戻らないため、`LOCALSEND_SEND_SCAN` の外向き走査（HTTP legacy discovery）を追加。**プリンターはDHCPで `192.168.10.9`→`192.168.10.3` へ移動しており、キューをmDNS名 `ipp://cA5E9FB00000.local/ipp/print` に変更**（`cups_printer_uri`）。トークンはSOPS・実機・アプリ設定をローテーション済み。**外部レビューを受けて1.0.2で修正（Content-Length明示・中継エラー本文の表示・devicesのLANアドレス許可・トークン比較）。証明書は[PR #1272](https://github.com/nextcloud/app-certificate-requests/pull/1272)・[#1273](https://github.com/nextcloud/app-certificate-requests/pull/1273)を提出済み（署名待ち）。常用はNC33のまま（NC35は使い捨てコンテナで有効化・ルート・設定画面・JS配信のみ確認）** | [nextcloud.md](nextcloud.md)・[printer.md](../services/printer.md)・[D06](../development/D06-localsend.md)・[D08](../development/D08-nextcloud-print.md) |
| ✅ | Nextcloud MCP | **Nextcloud MCPサーバを公開リポジトリへ切り出し、media-01をリリース取得方式へ移行（2026-09-26）。** [nextcloud-mcp](https://github.com/rurutheGeek/nextcloud-mcp) を作成して `v1.0.0` を公開、外部レビューを受けて `v1.0.1` に更新（tools/call前のwhoami必須化・タグreadのstat・write-denyの祖先拒否と展開メンバー検査・max_bytes検証・アーカイブ事前サイズ検査・Origin検証。標準ライブラリのみ・16ツール・テスト139件・Docker/GHCR対応）。呼び出し元の資格情報でNextcloudのACLに従うパススルー認証は不変。音楽ルートと追加の書き込み禁止プレフィックスをenv化し、tag-api連携はURLとトークンの両方があるときだけタグ3ツールを公開するようオプション化した。media-01は `group_vars/media.yml` の `nextcloud_mcp_version`/`_sha256` で固定したリリース資産をプレイが取得する。実機で `/healthz`（`version: 1.0.1`・`tag_tools: true`）とMCP接続からの `whoami`・MusicBrainz検索を確認。**2026-09-28: `v1.1.0`へ更新し、CalDAVカレンダー3ツール（`nextcloud_list_calendars`・`nextcloud_list_events`・`nextcloud_create_event`）を追加。** 繰り返し予定（`DAILY`/`WEEKLY`/`MONTHLY`/`YEARLY`、`COUNT`/`UNTIL`/`BYDAY`/`EXDATE`・上書き）の展開、既存の予定と重なる場合は競合を列挙して拒否（`allow_overlap=true`で強制追加）するため候補ごとにスキップできる。読み取り専用・VTODO専用カレンダーへの追加は拒否し、Calendarアプリ未有効（capabilitiesに`calendar`なし）なら明示エラーを返す。`NEXTCLOUD_MCP_TIMEZONE`（既定はホストのローカル）を追加（テスト182件・ruff通過）。media-01へ配備し、`/healthz`が`version: 1.1.0`、公開MCPの`tools/list`に3ツール、`list_calendars`が6カレンダー（読み取り専用共有の判別含む）を返すことを確認。予定の変更・削除は未対応 | [nextcloud-mcp.md](nextcloud-mcp.md)・[A06](../development/A06-nextcloud-mcp.md) |
| ✅ | NetBox 資産台帳 | **ネット接続の無い機器も含めて物理機器を NetBox で管理できるようにした（2026-09-27）。** `tools/netbox-dhcp-sync.py` は `interface`/`interfaces`（複数可）・`address`・`dhcp: false` を扱え、`serial`・`asset_tag`・`status`・型番（`part_number`）・`comments`・購入/保証（`custom_fields` の `purchase_date`/`purchase_from`/`price_jpy`/`warranty_until`）を同期（宣言が無い項目は画面側の値を消さない）。address の無い MAC は dnsmasq に名前だけ付ける（重複は畳む）。`power_ports`/`power_outlets` と `cables`（端点は interface / power_port / power_outlet、type は `cat6a`・`power` など）で接続図を作れる。`platform/netbox/devices.yaml` に役割20種・製造元・型番を追加し、購入品と家電から管理価値のある機器を登録（開発ボード、UPS×2、HDD/SSD、PC周辺、モニター、マイク、カメラ、ガジェット、工具、SDカード5枚、ONU、ヘルシオ/ホットクック/洗濯機/エアコン/REGZA、家族のスマホ3台、SwitchBot 開閉センサー、Eufy SmartTrack。計70台）。ケーブル11本（ネット幹線6＋UPS1 バッテリー口5。UPS2 は予備）。aterm は PA-WG1200HP、Redmi は Xiaomi、Echo は Amazon へ修正。PC3台はスペックを記録し役割を Desktop/Laptop へ。`ensure` は冪等、`pull`/`push` も通過。ケーブル・電源タップ・充電器・電子部品は載せない方針（主要な幹線と UPS 接続だけ接続図にする）。**残りは各機器のシリアル、PC3台のメーカ・型番、Wi-Fi 家電の MAC、TL-SG605 の port 番号確認、unknown-43/84 の正体** | [netbox.md](netbox.md#assets) |
| ✅ | パスキー | **パスワードレスの自動入力が出ない原因を特定し、discoverable（resident key）を必須化（2026-09-27）。** サーバー側（識別ステージの `passkey_challenge`・`autocomplete="username webauthn"`・パスワード/検証段を飛ばす既定ポリシー）は正常で、原因は登録済みBitwardenパスキーが2要素専用（非discoverable）だったこと。MFAでは使えており（`last_t`＝2026-09-26 09:51の本人ログインと一致）、`allowCredentials: []` の自動入力にだけ出ない症状だった。WebAuthn setupステージ `default-authenticator-webauthn-setup` を `resident_key_requirement: required` へ変更し、`configure.py` が冪等に適用（実機にも適用済み）。**2026-09-27より前に登録したパスキーは削除して登録し直しが必要。** Firefoxはユーザー名欄のパスキー自動入力に非対応（Chrome/Edge/Safariを使う） | [identity.md](identity.md#パスキーだけでログインするパスワードレス) |
| ✅ | セッション | **再ログイン頻度を下げた（2026-09-27）。** 実機DBで、認証セッションがブラウザー終了＋サーバー側24時間（tenant `default_token_duration: days=1`）で切れていた。`configure.py` が `default-authentication-login` の `remember_me_offset` を `days=30` にし、ログイン最後の「Stay signed in?」で **Yes** のときだけ30日保持（Noは従来どおり）。実機にも適用済み。常時30日にする場合は同ステージの `session_duration: days=30` | [identity.md](identity.md#再ログインを減らすセッション保持) |

各 Phase の詳しい中身と完了条件は[最小クラウドとProvider](../architecture/cloud.md)にあります。

## 6. 未決事項と後回しにしたこと

| 項目 | 現状 | 決めるときの材料 |
| --- | --- | --- |
| パスキー | **復旧を実装（2026-09-12）**: `configure.py` が **メール確認コード**（`default-authenticator-email-setup`）と**パスワード再設定フロー**（`default-recovery-flow`）を作る。`akadmin` の復旧先は `SMTP_FROM`＝`shake.notify@gmail.com`。復旧メールの送信を実機確認済み。ログインの検証段階は `email` ほかを受け付けるので、パスキーを失ってもメールコードで通過できる。パスキーと併せて登録するのは運用。手順は [identity.md](identity.md)。**パスキーだけのパスワードレスも有効化済み（2026-09-12）。2026-09-27にWebAuthn setupステージを `resident_key_requirement: required` へ変更し、新規登録はdiscoverable（resident key）に限定した（登録済みは再登録が必要）** | 名前（`auth.apextox.dpdns.org`）を変えると登録し直しになる。Firefoxはユーザー名欄のパスキー自動入力に非対応（Chrome/Edge/Safari）。[認証基盤（identity・Authentik）](identity.md)・[ネットワーク・SSO](../architecture/network-auth.md) |
| 無料ドメインの継続性 | DigitalPlat の更新・取り消しの規則は確認できていない | 取り上げられたら名前の付け替えになる。困るようなら有料ドメイン（候補 `ruruthegeek.org`）へ移す |
| メディア系の認証 | **media-01 は identity の OIDC / Forward Auth に統合済み（2026-09-12）** | 既存環境からのデータ移行の完了後に扱いを決める |
| public-edge | N04で公開要件を検討。新規cloud VMとして追加予定 | VMIDはAPIの通常採番。game1の100は使わない |
| `05-seed` の SSH 鍵 | **解決済み（2026-09-12）**: `access.yaml` の `seed_ssh_public_keys` へ移した。実機（VMID 150 の `sshkeys`）の順序＝admin 先頭2鍵の逆順と一致。`05-seed/main.tf` が access.yaml を読む（`tests/test_platform_inventory.py` が検査） | — |
| cloud-01 のサイズ | `small`（2GiB）。2026-09-12の実測でゲスト使用 約0.4GiB（API 11MiB、PostgreSQL 26MiB）。ディスクは軽量化で40GiB中6.2GiB使用 | Phase 2 以降の負荷を見て、足りなければ `medium`。その分、利用者VMに回せる余白が減る |
| ポータルのフロント | `html/template` と素の JS。**2026-09-12 に[Web GUI監査・改善案](../audits/webgui-2026-09-12.md)を作成**（P1 6件・P2 10件）。同じ監査の指摘どおり、送信ロックとVMの `client_token`、ID単位の一覧更新と入力保持、選択IDの保持、日本語のエラーと操作箇所への表示、用途別ナビ、検索・絞り込み、履歴の検索・ページ送り・詳細、アップロードの段階表示と中断、S3権限の用途選択と owner 既定オフ、上限の差分確認を `index.html`・`portal.js`・新規 `portal-ui.js`・`portal.css` へ実装 | 模擬APIと実ブラウザ（Chrome Headless Shell 153）で機能28項目とキーボード操作、axe-coreの自動検査（一般利用者／管理者・ライト／ダークの3画面、違反0件）を確認し、**dev-bのPostgreSQLを使って`go vet ./...`と`go test ./...`（cloud/api全パッケージ）も通した**（連打・入力保持・選択保持・320/390px・コントラスト・502/401・S3権限・上限差分・雛形・アップロード段階／中断とサーバー側の接続断）。結果は監査の「改修後の確認」と[確認結果JSON](../audits/webgui-2026-09-12/after-results.json)に残した。**2026-09-12 に `cloud.yml` で cloud-01 へ配備**し、`/healthz` 200 と新規 `/static/portal-ui.js`・`portal.js`・`portal.css` の配信を確認。未確認は、Authentikログインで確立する認証済みポータルでの画面操作、実VM／実S3の作成・変更、実機のスクリーンリーダー。新しい JS ビルド基盤は増やさない前提 |
| 管理DBのバックアップ | **定期実行を実装（2026-09-12）**: cloud-01 の `cloud-backup.timer` が毎日 `manage.py backup --keep 14` を `/var/backups/cloud-api` へ。**2026-09-22にTier1 VMの週次vzdump（`bulk-backup`、keep-last=4）を追加**（[backup.md](backup.md)）。**別ホスト／別機器へのコピーは未着手**（Garage は単一ノードなので唯一の控えにしない） | 別ディスク／外部へのコピー先を決める（[cloud-resources.md 3-18](cloud-resources.md#3-18)） |
| クライアント端末バックアップの2次コピー | media-01 の UrBackup は6TB HDDの `/srv/bulk/client-backups` へ取る。同じHDDには vzdump・メディア・Nextcloud も載る単一障害点で、HDDの故障・ランサムで全部を失う | 別ディスク・別機器へのコピーを O01 系とまとめて決める（[W08](../development/W08-client-backup.md)） |
| `poke` のDNS | `poke.apextox.dpdns.org` は 20-dns の state に残っているが `dns.yaml` に無く、次の一括 apply で削除される（翻訳サイトは services-01 の `127.0.0.1:8320` で稼働中）。2026-10-02 の `backup` 追加はレコード単体のターゲット適用で回避した | poke を残すなら `dns.yaml`・配備コードとセットで戻す。消すならサービス停止と一緒に判断する |
| 端末台帳 | **Pixel 8a をやめて家族全員 Galaxy になった（2026-10-02、利用者判断）。** NetBox（`platform/netbox/devices.yaml`）には Pixel 8a が残っており、新しい Galaxy の機種・シリアルが未登録 | 新機種名を確認して台帳を更新する（[W08](../development/W08-client-backup.md)） |
| state の置き場 | Cloudflare R2。基盤は `shake-cloud/<module>/…`、サービスは `shake-cloud/services/<name>/terraform.tfstate`（I05で`tools/tf services/*`分岐とロックを実機確認済み） | 資格情報は`s3.sops.yaml`と`services.sops.yaml`（`services.sops.yaml` は作成済み。キーの有効性・権限は未確認）。Garageは復旧時にstateの唯一の保管先にしない |
| AWX | **配備済み（2026-09-12）**: 24.6.1 を Flux で配備（[kubernetes.md](kubernetes.md)・[AWXの使い方](awx.md)） | ジョブテンプレート・プロジェクトの整備はこれから |
| Terraform の版 | **解決済み（2026-09-12）**: `.terraform-version`＝`1.15.8` が唯一の出所。CI は同ファイルを読み、`devbox` ロールも同版のバイナリを入れる（`tests/test_terraform_version.py` が検査） | — |
| 構成監査の残り指摘 | 2026-09-16の監査で残っている指摘は[構成監査の未対応指摘](../audits/config-audit-2026-09-16.md)にまとめた（2026-10-02） | 優先順は ①age受信者を3本に（30分）→ ②既定SGのingressを閉じる／管理CIDRへのegress DROP → ③NetBox・print-apiのHTTPS化／127.0.0.1束縛 → ④`mem_limit`と`retention.size` → ⑤復元ドリルの月次化と最終復元成功日の記録 |
| android-01 の環境 | 環境スクリプト（`/opt/leo/persist.sh`・`ui-loop.sh`・`recover.sh`・`verify.sh`・`hook.js`・`android-env.service`）は VM 上にしか無く Git に入っていない。VM を作り直すと失われる | Ansible 化が未了（[android-01](android-01.md)） |
| Nextcloud MCP の実データ確認 | 人間の Nextcloud アカウントでの実データ確認（タグ編集→同期タイマー→Navidrome 反映、大きい zip の解凍、MOVE での fileid 維持、tag-api のトークン付き呼び出し）は未了 | 確認までは動作確認済みと書かない（[A06](../development/A06-nextcloud-mcp.md#design-decisions)） |
| 依存更新の自動化 | **設定を追加（2026-10-02）**: `renovate.json`（週次・自動マージなし）とCIの `govulncheck`・`ruff`・`shellcheck`。👤 RenovateのGitHub Appをリポジトリへ入れるまでPRは作られない | `compose.lock.yaml` のdigestはRenovateの対象外。更新はリポジトリのlockを書き換えて配り直す |
| イメージのdigest固定 | **monitoring・home-assistant・eufy-security-ws の配備先lockをリポジトリへ取り込んだ（2026-10-02。稼働中のdigestと同一で、実機は変更していない）。** 残る例外は `romm`（game1へ構成管理の鍵で入れない）と `pokemon-ai/ollama`（配備先を未確認） | 例外は `tests/test_image_locks.py` の `UNPINNED`。増やさない |
| インベントリの統一 | **実機を切り替えた（2026-10-03）。** cloud-01 を main の版で配備してクラウドAPIが台帳への登録を始め、`10-platform` は NetBox のタグ3つと services-01 の台帳**だけ**を `-target` で適用した（順番が逆になり、タグを作るまでの数分、台帳同期が警告を出した）。**`10-platform` の全体 apply はしていない**: plan に dev-a・dev-b・k8s・probe-01・storage-s3 の `initialization` の差分（in-place）が出ており、使用中のVMに触れるため。コードは 2026-10-02 に追加。 クラウドAPIが自分のVMをNetBoxの仮想マシンとして登録し（`cloud/api/internal/compute/ledger.go`。状態が変わったらすぐ、加えて15分ごと。稼働中だけ `active`）、Ansibleは NetBox の動的インベントリ1本で対象を見つける。グループは `cloud.yaml` の `ledger.tags_by_name`（VM名→タグ）で決め、VM自身のタグでは決めない。services-01 は `10-platform` が台帳へ載せ、共有サービスのPlaybookは `hosts: services` に変えた | 切替は ①`tools/tf 10-platform apply` ②`cloud.yml` ③`ansible-inventory --graph` で確認（[サービスの置き場所](services.md#inventory)）。**`10-platform` の plan には今回と無関係の未適用差分が9件ある**（`access.yaml` に足したSSH鍵が6台へ未反映、dev-b のballoon下限、k8sの説明文）。切替後に `inventory.cloud.py`・`cloud-inventory.yml`・`monitor.ini` を削除する。`pve.ini` は残る |
| HTTPSの入口 | **入口を core-01 の1台にまとめた（2026-10-03）。** `dns.yaml` の `edge.backends` は monitor-02・media-01・apps-01・cloud-01。Caddy が受ける名前はすべて core-01（192.168.10.200）を指し、core-01 が各ホストの内部CAを確かめて中継する。**Cloudflare のDNS編集トークンを持つのは core-01 だけ**（4台とも `secrets/` が空で、設定に `dns cloudflare` が無いことを確認）。Authentik が入口と同じホストに居るので、中継するサイトの `/outpost.goauthentik.io/*` は入口が Authentik へ直接渡す。確認: 24サイトすべてが入口経由で応答（Forward Auth のサイトはログインへ302）、クラウドAPIも入口経由で応答。コードは 2026-10-02 に追加 | ①各ホストの内部CAは `platform/ansible/files/backend-ca/`。ホストを作り直したら取り直す（[手順](edge.md)）②初めて後ろへ移すホストでは、アプリのロールの「公開名で確かめる」タスクが、DNSを切り替えるまで失敗する（入口を配備してDNSを切り替えたあと、もう一度流す）③クラウドVMの SG は 443 を LAN 全体に開けたまま。入口（192.168.10.200）だけに絞れる ④トークンは入口のほかに Proxmox ホストと k8s の cert-manager に残る |
| Playbookの整理 | **共通ロール `compose_stack` を追加し、media系6本（Kavita・Navidrome・FreshRSS・LocalSend・Nextcloud・music-tools）を載せ替えた（2026-10-02〜03）。** `manage.py` を呼ぶタスクが毎回「changed」と報告していたのを、実際に変わったときだけ報告するよう直した。秘密値を読むだけのタスク（20件）は `check_mode: false` にし、**どのPlaybookも `--check --diff` で事前確認できる**ようにした。media-01 に対する `--check --diff` で、載せ替えた部分に差分が無いことを確認した（実機へは未配備） | 残りは Home Assistant・eufy-security-ws（`.env` を行単位で収束させる形なので載せ替えない）と、ロール側（librespeed・vaultwarden など）の共通化、`manage.py` 19本の共通部分の集約。**同じ確認で実機とリポジトリのずれが見つかった**: ①Navidrome が `deluan/navidrome:latest`（0.64.0）のまま動き、実機の lock は古い（`media-navidrome.yml` で固定される）②media-01 の Nextcloud の `manage.py` に `custom-apps` が無い（2026-09-26 の「custom-apps方式への移行」がPlaybookで配備されていない）③LocalSend 送信スクリプトが実機で手直しされている（`.bak` あり）④リポジトリに無い `media-urbackup` が動いている |
| 配置と命名の再編 | **方針を決めた（2026-10-03）。実機の移行は未着手。** 基盤は router-01（Tailscale込み）・core-01・cloud-01・monitor-01・k8s、アプリと開発VMはクラウドVM。正本は[配置と命名の再編](../architecture/placement-naming.md) | apps-01 の作成と services-01 のアプリ移設から（services-01 のメモリが 3.5GB / 3.9GB で逼迫）。順番は同ページの4章。**dev-a・dev-b・game1・win11pro は使用中のため、指示があるまで触らない** |
| クラウドポータルのUI改善 | **ファビコン、タグの表示・絞り込み・作成時の指定、作成後の名前・タグの変更（`PUT /v1/instances/{id}/tags`）を cloud-01 へ配備（2026-10-03）。** 実機で確認: `win11pro` を `win-01` へ改名（Proxmox のVM名も変わった。VMは停止中のまま）、`android-01`・`win-01` に `Purpose=dev`、`media-01` に `Purpose=service` を Terraform で追加（作り直しなし）。手元の Terraform Provider（`~/.terraform.d/plugins`）を作り直した（古いままだと `tags` の変更がインスタンスの作り直しになる）。計画は [I07](../development/I07-portal-ui.md) | ①ポータルの「名前・タグを編集」はブラウザーで未確認 ②`game1` → `game-01` の改名と `Purpose` は、使用中のため未実施 ③メニューのまとまりの採否 |
| apps-01 | **作成済み（2026-10-03）。192.168.10.105、2 vCPU・4GiB、データ16GiBを `/srv`。** クラウドのメモリ予算を 32→48GiB に上げた（32GiBでは作成が断られた）。**LibreSpeed・ドキュメントサイト・mail-view・Homarr・Vaultwarden・CUPS（印刷API込み）を移設済み**。CUPS は apps-01 からプリンター本体（mDNS名で解決）へ届くことと、media-01 から印刷APIへ届くことを確認（実際の印刷は未確認）。**プリンターを `192.168.10.200:631` で登録している端末は `192.168.10.105:631` で登録し直す**。（Vaultwarden は停止してからDBと鍵をコピーし、新旧で利用者2・項目547件と整合性を照合。切替前のバックアップは services-01 の `/srv/backups/vaultwarden-pre-move-20261003.tgz`）（Homarr はDBと秘密値をコピーして、同じボード・同じSSOのまま起動）（`/opt/<アプリ名>`・`/srv/<アプリ名>`。LibreSpeed は計測履歴もコピー。DNSを切替、services-01 側は停止して入口から外した。mail-view は SSO へのリダイレクトまで確認）。services-01 の旧ディレクトリ（`/opt/services/librespeed`・`/srv/services/librespeed`・`/opt/docs-site`・`/opt/services/mail-view`・`/opt/homarr-stack`・`/srv/homarr-stack`・`/opt/services/vaultwarden`・`/srv/services/vaultwarden`）は戻せるよう残してある。**Vaultwarden の旧データは、新側で数日使って問題が無ければ消す**（古いコピーを起動すると新しい変更を失う） | ポケモン翻訳、Home Assistant・eufy-security-ws・eufy-leo-rtc も移設済み（2026-10-03）。**services-01 に残るのは NetBox と入口の Caddy（netbox・adguard・router）だけ。** Home Assistant は設定ごとコピーして `https://ha.…` が 200。eufy-security-ws は push 接続まで確認（カメラへの P2P は移設前から失敗しており、カメラ 192.168.10.4 は services-01 からも応答なし）。切替前のバックアップは services-01 の `/srv/backups/home-eufy-pre-move-20261003.tgz`。apps-01 はバルーニングで約2.2GiBまで絞られて余裕が無くなったため、下限を 3GiB に上げた。次は core-01（Authentik と NetBox の統合）。移すたびに Playbook の `hosts`・`dns.yaml` の `host`・配備先のパスを切り替える。apps-01 は監視の対象に入れた（node_exporter。2026-10-03、38ターゲットすべて up）。**`20-dns` は全体 apply しない**: plan が `poke`（poke-translate。実機にあるが `dns.yaml` に無い）のレコードを消そうとするため、`-target` で1件ずつ適用している |
| core-01（Authentik の統合） | **Authentik を identity から services-01 へ移した（2026-10-03）。** services-01 を 4→6GiB にし、identity 側を停止 → PostgreSQL・メディア・秘密値をコピー → `auth` のDNSを切替 → services-01 で起動（利用者5・アプリ22件を確認）。NetBox のタグ `identity` を services-01 へ付け替えたので、Ansible の `identity_provider` グループは services-01 を指す。Authentik のコンテナにメモリ上限を入れた。確認: Forward Auth のサイト（navidrome・metube・khinsider・cups・mail-view・adguard・urbackup）はログインへ302、OIDC のサイト（homarr・grafana・vault・netbox・cloud・ha）は応答。**実際のログインはブラウザーで未確認。** 切替中に Forward Auth が約15分 502 になった: identity のVMで入口の Caddy だけが動き続け、他のホストが張ったままの接続で古い側へ問い合わせていた（identity の Caddy を止めて解消）。入口には知らない SNI へ auth の証明書を返す設定（`fallback_sni`）も足した | ①identity のVMは起動したまま、コンテナは全部停止・自動起動なし。数日後に VM を止めて消す（戻すなら `auth` のDNSを戻してコンテナを起動）②NetBox のコンテナにもメモリ上限を入れる ③**改名済み（2026-10-03）**: Proxmox のVM名・ゲストのホスト名・NetBox のVM名とタグ（`services` → `core`）・`dns.yaml`・インベントリのグループ（`core`）・`group_vars/core.yml`。**この台帳と各設計文書の本文には、改名前の `services-01` という表記が履歴として多数残っている（同じVM＝192.168.10.200 を指す。アプリの記述は apps-01 へ移っている）**。手元の `seed.ini`（Git管理外）の名前も直す必要がある ④`/opt/identity-stack`・`/opt/netbox-stack` の命名は未統一 ⑤core-01 に再び作られていた eufy-leo-rtc のコンテナは停止・削除した（2026-10-03。eufy は apps-01 だけで動く） |
| Garage の合流 | **Garage を storage-s3 から cloud-01 へ移した（2026-10-03）。** 旧側はバケット0・キー0（メタデータ4.6MB）だったのでデータは移さず、cloud-01 に 32GiB のデータディスクを足して `garage.yml` で新規構築。`cloudapi.sops.yaml` の `GARAGE_ADMIN_URL`・`GARAGE_S3_ENDPOINT`・`GARAGE_ADMIN_TOKEN` を cloud-01 のものへ更新し、`cloud.yml` で反映。クラウドAPI経由でバケットの作成・一覧・削除を確認。**S3 のエンドポイントは `http://192.168.10.205:3900` に変わった** | storage-s3 のVMは起動したまま Garage を停止・無効化。数日後に VM を消し、`hosts.yaml`・監視の対象（192.168.10.206）・バックアップ対象（VMID 130）から外す |
| 監視の基盤への移行 | **監視を基盤側の monitor-02（VMID 120、192.168.10.210）へ移した（2026-10-03）。** `hosts.yaml` で宣言し、旧 monitor-01（クラウドVM）の監視を止めて `/opt/monitoring-stack` と `/srv/monitoring`（Prometheus 768MB・Grafana 508MB）をコピー、`grafana`・`peanut` のDNSと apps-01 の SG（9100）を切替、`monitoring.yml` で配備。確認: 39ターゲットすべて up、過去2日分の時系列が残っている、UPS は OL、Watchdog 発火中、Grafana・PeaNUT が応答。失敗している外形監視は AWX だけ（Kubernetes 停止中のため、移行前から）。データは OS と同じディスク（48GiB）に置いた。作成時、`10-platform` の apply がゲストエージェント待ちで時間切れになり、state のロック解除とVMの import をした（`guests.yml --limit <名前>` を別シェルで流せば待ちは解ける） | ①旧 monitor-01（`i-2193bd70bacdd1602`）は停止中。数日後に `platform/terraform/services/monitor` を消す（データボリュームは `prevent_destroy`）②そのあと monitor-02 を monitor-01 へ改名する ③`cloud.yaml` の台帳から `monitor-01: [monitoring]` を外した |
| Tailscale のルータ移設 | **subnet router を net-01 から router-01（OpenWrt）へ移した（2026-10-03）。** ルータへ `opkg install tailscale`、ファイアウォールに `tailscale` ゾーンと LAN への転送を `uci` で追加、net-01 の `tailscaled.state` をルータの `/etc/tailscale/tailscaled.state` へ移して同じ端末として起動（管理画面での再承認は不要だった）。確認: ルータが `192.168.10.0/24` の primary route を持つ、fw4 に転送ルールがある、tailnet 経由の ping が通る。**宅外（モバイル回線）から LAN へ入れるかは未確認。** リポジトリ側は `openwrt.yaml` のパッケージと `rootfs/etc/shakecloud/config/` に反映済み | ①宅外から実際に接続して確かめる ②net-01 は停止中。確認できたら `platform/terraform/services/net` を消す ③**ルータのイメージを作り直すと状態ファイルは入らない**（秘密値なのでイメージに含めない）。作り直す前に `/etc/tailscale/tailscaled.state` を退避して戻すか、認証キーで参加し直す ④ルータの実機の `/etc/config/firewall`・`network` とリポジトリの `config/` は、**設定の中身は一致している**（2026-10-03 に、コメントと並び順を除いて比較して確認。`uci commit` がコメントを落とすので、ファイルとしては差分が出る） |
| 再編の片付け | **2026-10-03 に実施。** ①削除: net-01・旧 monitor-01（クラウドVM。`tools/tf services/* destroy`）、identity・storage-s3（基盤VM。`hosts.yaml` から外して `10-platform` を `-target` で適用）②改名: monitor-02 → monitor-01（state を `state mv` で移してから適用。ゲスト内のホスト名は `common` ロールが台帳の名前に揃える）③core-01 の旧データ（`/opt/services`・`/srv/services`・`/opt/homarr-stack`・`/srv/homarr-stack`・`/opt/docs-site`・`/opt/print-api`）と未使用イメージ（9.6GB）を削除。切替前のバックアップ（`/srv/backups/*-pre-move-20261003.tgz`）は残した ④**週次バックアップの対象を直した**: 101・120・140・150・401・5001・5005。**apps-01（Vaultwarden・Home Assistant）が対象に入っていなかった**ので足し、消したVMを外した ⑤クラウドVMの 80/443 を入口（192.168.10.200）からだけ受けるようにした（apps-01・media-01。直接つなぐと応答しないことを確認）⑥`win-01` のデータボリューム（200GiB）を SSD から HDD へ移した（下の行） | 基盤VMの cloud-01・monitor-01 は Proxmox のファイアウォールを使っておらず、443 は LAN 全体に開いたまま |
| win-01 のデータボリューム | **SSD（local-lvm）から HDD（bulk-disks）へ移した（2026-10-03）。** `qm disk move 5000 virtio1 bulk-disks --format raw`（VMは停止中）。HDD 上の実使用は 82GiB（raw のスパースファイル）。**これは API を通さない手作業**: クラウドAPIにボリュームの種類を変える操作が無いため、Proxmox で移したあと管理DBの `volumes.volid` と `disk_tier` を合わせた | ①見かけの大きさは 200GiB のまま。100GiB へ縮めるには Windows 側でパーティションを縮める必要があり、やっていない（HDD 上で使うのは書き込んだ分だけ）②ボリュームの種類を変える API（SSD⇔HDD）は未実装 |

## 7. 引き継ぐ人のアクセス

今は**アクセス手段が dev-b の1か所に集まっています。** 引き継ぐときは、同じものをもう1人分作ります。どれも既存の保持者が1回操作すれば済み、秘密値そのものを受け渡す必要はありません。

| 必要なもの | 今どこにあるか | 新しい人の分を作る方法 |
| --- | --- | --- |
| SOPS の復号（age 鍵） | dev-b の `~/.config/sops/age/keys.txt` | 新しい人が自分の age 鍵を作り、**公開鍵だけ**を渡す。保持者が `.sops.yaml` へ足し、`sops updatekeys platform/sops/*.sops.yaml` を実行する（[秘密値の管理](secrets.md)） |
| 基盤VMへの SSH | `platform/terraform/access.yaml` の公開鍵 | 公開鍵を `admin_ssh_public_keys` の**末尾に**足す（順序を変えない）。新しく作るVMにはこれで入る。既にあるVMには、入れる人が `ssh-copy-id` か Ansible で足す |
| Proxmox ホストへの SSH | 人が管理（dev-b の鍵は未登録） | ホストの `authorized_keys` へ公開鍵を足す |
| クラウドの管理者権限 | Authentik の `admins` グループ | 新しい人の Authentik アカウントを `admins` に入れる。ブートストラップ管理キーは共有しない |
| 手元にしか無い設定 | `platform/ansible/pve.ini`、`seed.ini`、`.local/pve-readonly.env` | `.example` から作る。`pve-readonly.env` は `site.yaml` を作り直すときだけ要る |
| Go のツールチェーン | dev-b の `~/.local/go`（1.27.1。apt の版は古い） | `https://go.dev/dl/` から取得して `PATH` に足す。版は `cloud/api/go.mod` に合わせる |

VM の中にある秘密値は、次の場所で自動生成されています。Git には入りません。

| 場所 | 中身 |
| --- | --- |
| services-01 `/opt/netbox-stack/secrets/` | NetBox の DB・鍵、各トークン（`inventory` / `terraform` / `cloudapi`） |
| identity `/opt/identity-stack/secrets/` | Authentik の DB・鍵、`akadmin` の初期パスワード、ブートストラップトークン、`oidc-cloud.json` |
| cloud-01 `/opt/cloud-stack/secrets/` | 管理DBのパスワード、`oidc_credentials`（identity の `oidc-cloud.json` の写し）。`bootstrap_admin_key` は 2026-09-11 に無効化して空 |
| services-01 `/opt/services/`・`/opt/print-api/` | Home Assistant の config、Eufy の `.env`、Vaultwarden の `secrets/admin_token`、LibreSpeed の `secrets/stats_password`、print-api のトークン。状態は `/srv/services/...` |
| monitor-01 `/opt/monitoring-stack/secrets/` | Grafana の管理者パスワード、Grafana の OIDC 秘密値（identity の `oidc-grafana.json` の写し）、NUT のパスワード、`game_metrics_token`（Prometheusだけが読む0444）など。状態は `/srv/monitoring/...` |
| identity・cloud-01・services-01・media-01・monitor-01 の `/opt/tls-proxy/secrets/` | Cloudflare の DNS 編集トークン（`cloudflare-dns.sops.yaml` の写し）。証明書は `/srv/tls-proxy/storage/data` |

リポジトリ側の暗号化済みファイルは次のとおりです。

| ファイル | 中身 |
| --- | --- |
| `platform/sops/proxmox-root.sops.yaml` | `root@pam` トークン（`00-bootstrap` 専用） |
| `platform/sops/proxmox.sops.yaml` | `terraform@pve` トークン |
| `platform/sops/cloudapi.sops.yaml` | `cloudapi@pve` と NetBox `cloudapi` のトークン（Phase 2 で API が使う） |
| `platform/sops/netbox.sops.yaml` | NetBox 書き込みトークン（Terraform 用） |
| `platform/sops/netbox-inventory.sops.yaml` | NetBox 読み取りトークン（Ansible インベントリ用） |
| `platform/sops/s3.sops.yaml` / `cloudflare.sops.yaml` | Terraform state の置き場 |
| `platform/sops/cloudflare-dns.sops.yaml` | `apextox.dpdns.org` の DNS 編集トークン（証明書の DNS-01 用）。state 用の `cloudflare.sops.yaml` とは別 |
| `platform/sops/eufy-security.sops.yaml` | Eufy アカウント（`EUFY_USERNAME`・`EUFY_PASSWORD`・`EUFY_COUNTRY`・`EUFY_TRUSTED_DEVICE_NAME`・`EUFY_STATION_IP_ADDRESSES`）。`eufy-security-ws.yml` が `.env` へ写す。投入済みで WS は稼働 |
| `platform/sops/home-assistant.sops.yaml` | Home Assistant の長期アクセストークン（`HA_TOKEN`） |
| `platform/sops/monitoring.sops.yaml` | monitor-01 用の Proxmox 読み取りトークン（`PVE_TOKEN_VALUE`）、NUT 監視ユーザーのパスワード（`NUT_MONITOR_PASSWORD`）、ゲームポータルの指標トークン（`GAME_METRICS_TOKEN`。Prometheusの `game` ジョブだけが使う） |
| `platform/sops/k8s.sops.yaml` | database/function 用 ServiceAccount `databases/cloud-api` の接続情報（`K8S_API_URL`・`K8S_CA_BASE64`・`K8S_TOKEN`） |
| `platform/sops/print-api.sops.yaml` | Nextcloud 印刷アプリ → services-01 `print-api` のトークン |
| `platform/sops/smtp.sops.yaml` | Gmail（`shake.notify@gmail.com`）のアプリパスワード。identity の招待・復旧メール用 |
| `platform/sops/services.sops.yaml` | サービスVM（`services/*`）のstate用 shakecloud アクセスキー（作成済み。有効性・権限は未確認） |
| `platform/sops/pve-users.sops.yaml` | 開発VM用の Proxmox ユーザー |
