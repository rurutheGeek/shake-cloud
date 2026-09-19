---
title: K11到着後・Proxmox VE導入後の進め方
updated: 2026-09-13
section: 設計
audience: 管理者・開発者
tags:
  - design
  - bootstrap
---

# K11到着後・Proxmox VE導入後の進め方

> **更新日** 2026-09-13 ・ **区分** 設計 ・ **読む人** 管理者・開発者

[構成案トップ](../architecture/index.md) / [VM配分・サービス配置](../architecture/operations.md#resource-budget)

**状態**: 手順の記録。Proxmox・VM・Kubernetes・AWX・クラウドAPI は 2026-09-12 までに実機で構築済みで、この文書はその順番を残すためのものです。現在の状態は[配備台帳](handover.md)を正とします。 64GB／1TBのK11を想定します。以下の章番号は初回構築の経緯で、今後の実施順ではありません。配置変更と未完了作業は[並列開発計画](../development/index.md)に従います。

## 1. ホストの基礎を記録する

Proxmox導入直後、GUIのノード概要・ディスク・ネットワーク・更新画面を確認する。次の読み取りコマンドは**K11のProxmoxホスト上**で実行する。出力に含まれるLAN構成・識別情報は非公開の作業台帳へ保存する。

```bash
pveversion -v
free -h
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
pvesm status
ip -br address
ip route
lspci -nnk
```

同じ内容をAnsibleからまとめて取得できます。読み取りだけを行い、ホストへ書き込みません。出力は管理端末の `.survey/` へ保存され、Gitからは除外されます。ストレージ定義・既存VMID・IOMMUグループも併せて取得するので、後段のTerraformに必要な値がこの1回で揃います。

```bash
cp platform/ansible/pve.ini.example platform/ansible/pve.ini
# 接続先を編集し、先に手動SSHでホスト鍵を確認する
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/survey-pve.yml
```

生成された `.survey/<ホスト名>.md` の冒頭に「Terraformへ転記する値」の表があります。ノード名、VMディスク用ストレージ名、cloud image／ISO置き場（`iso`）、クラウドAPI用イメージ置き場（`iso` と `import`）、SDNゾーン、データセンターFWの状態、bridge名とvlan-awareの有無、既存LANのサブネットとgateway、空きIP範囲、使用済みVMID、iGPUのPCIアドレスとIOMMUグループを埋めてから次へ進みます。**クラウドAPIは任意の user-data を NoCloud の seed ISO（`content=iso`）で渡すため `snippets` は使いません。** このファイル自体は台帳ではありません。必要な値を非公開台帳へ転記し、`.survey/` は作業用の一時出力として扱います。

- BIOSの仮想化／IOMMU、RAM、SSD、冷却とファン動作を確認する。iGPUの固定予約は実測前に16GiBへ増やさない。
- 管理用IP・ホスト名・gateway・DNS・時刻同期を固定／確認する。既存ネットワークと重複しないIPを使い、bridgeの物理NIC割り当てを確認する。
- GUIで導入版に対応する公式リポジトリを選び、契約の有無に合った更新元を使う。更新後に再起動し、管理PCから再接続する。異なるDebian／Proxmox版のapt行を混ぜない。
- SSH鍵とローカル復旧用管理者を確保する。VPN経由の管理も確認する。Proxmox管理画面をインターネットへ直接公開しない。
- インストール済みストレージを台帳へ記録する。`local`／`local-lvm`／ZFSなどの実構成に合わせる。配分表のためにSSDを再初期化しない。

**完了条件:** 再起動後もGUI・SSH・DNS・時刻が正常で、管理LANから復旧できる。GPUをゲストへ渡す前にこの状態を作る。[Proxmox公式管理ガイド](https://pve.proxmox.com/pve-docs/pve-admin-guide.html)

## 2. 管理台帳とバックアップ先を先に作る

非公開台帳へ、VMID・VM名・IP予約・用途・vCPU/RAM・ディスク／保存先・起動順・バックアップ対象・確認日を記録する。初期値は[VM配分表](../architecture/operations.md#resource-budget)を転記し、未作成／検証中／稼働／移行済みを区別する。APIキーやパスワード自体は台帳へ直書きしない。

利用可能な既存の外部バックアップ先を1つ確認する。今回の計画では新規ハード購入を前提にしない。対象デバイスと既存データを確認してから設定する。同じ内蔵SSDの別パーティションやスナップショットだけを故障対策にしない。PBSは後から追加できる。

**完了条件:** バックアップ先への書き込みと容量確認が済み、管理PCにホスト設定の復旧メモと鍵がある。

## 3. Linux VMを1台作り、復元まで試す

公式のDebian／Ubuntu cloud imageを用意し、2vCPU・2GiB・32GiBの検証VMを作る。cloud-initで個別ユーザー・SSH公開鍵・ネットワークを設定し、VirtIO NICとディスク、QEMU Guest Agentを構成する。使うOS版・イメージ・checksum・Proxmox設定を記録する。[Proxmox Cloud-Init](https://pve.proxmox.com/wiki/Cloud-Init_Support)

1. 管理PCからSSH接続し、DNS・外向き通信・再起動後の接続を確認する。
2. 検証用ファイルを置き、別媒体へVMバックアップを取る。
3. 別VMIDへ復元する。同じIP／MACの競合を避けるため、復元VMはNIC切断または隔離ネットワークから起動する。
4. ファイルが戻ることを確認し、復元VMを片付ける。
5. 元VMをテンプレート用に整えるか `dev-a` に割り当てる。テンプレートから複製する場合、ホスト名・IP・machine-id・SSH host keyの重複を確認する。

この手順はコード化してあります。VMの作成は宣言（`platform/terraform/hosts.yaml` の `probe-01`、VMID 900）から行い、復元は補助スクリプトで踏みます。

```bash
# 1. 台帳とVMを作る
tools/tf 10-platform apply

# 2. ゲストOSの共通設定
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/guests.yml --limit probe-01

# 3. 復元ドリル（Proxmoxホスト上でrootとして実行）
tools/pve-restore-drill.sh backup  --vmid 900 --storage <別媒体のストレージ>
tools/pve-restore-drill.sh restore --vmid 900 --target-vmid 901 --archive <出力されたファイル>
# コンソールから検証用ファイルを確認してから
tools/pve-restore-drill.sh cleanup --target-vmid 901
```

`restore` は復元VMの全NICを `link_down=1` にしてから起動します。元VMとIP/MACが衝突しません。復元先VMIDが既に存在する場合は何もせず止まります。`cleanup` だけが破壊的で、確認を求めます。

**完了条件:** バックアップファイルが存在するだけでなく復元できる。ここまでを最初の作業日の到達点にしてよい。あわせて `terraform apply` の2回目が `No changes`、`ansible-playbook --check` の2回目が `changed=0` になることを確認する。

### 開発VMを2台使えるようにする

`dev-a`（VMID 400）と `dev-b`（VMID 401）は `hosts.yaml` に定義済みで、`10-platform` の apply で一緒に作られます。`00-bootstrap` が `dev-a@pve` / `dev-b@pve` と `DevVMOperator` ロールを作るので、あとは各自がパスワードを設定してAPIトークンを作ります。

```bash
# 管理者: 初回パスワードを設定してもらう（Terraformでは管理しない）
pveum passwd dev-a@pve

# 利用者: ゲストOSの初期設定
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/guests.yml --limit dev-a
```

`DevVMOperator` に含まれるのは `VM.Audit` / `VM.PowerMgmt` / `VM.Console` だけです。CPU・RAM・ディスク・NICの正本は `hosts.yaml` のままなので、利用者の操作でIaCと実機が乖離しません。使い方は[開発VMの使い方](../services/devvm.md)を利用者へ渡します。

**完了条件:** 2人がそれぞれ `devvm start` → `ssh` → 作業 → `devvm stop` を一周できる。相手のVMが一覧に出ない。`terraform plan` が `No changes` のまま。

### セルフホストVPNを追加する

専用vpn-01の旧案を変更し、services-01の別Composeへ追加します。[N01](../development/N01-vpn.md)で設定・認証・外部到達を検証し、[N02](../development/N02-tailscale.md)でラズパイの独立した復旧経路を確認します。両方の調査・設定作成は並行し、接続先変更時だけ調整します。

## 4. Home Assistantをservices-01へ追加する

HAOS専用VMの旧案を変更し、Home Assistant Containerを使います。[H01](../development/H01-home-assistant.md)のとおり、**services-01へ配備済みです（2026-09-12）**。入口は `https://ha.apextox.dpdns.org`（Caddy + Let's Encrypt、本体は `127.0.0.1:8123`）。認証はAuthentik OIDC（公開クライアント `home-assistant` と `hass-oidc-auth` v1.2.1）と緊急用のローカルオーナーを併用します。WebSocket・CompanionアプリがあるためCaddyのForward Authは使いません。Kubernetes・game1から分離できますが、services-01再起動時は家電・印刷・Eufy中継も停止します。

SwitchBotはHub Mini経由のSwitchBot Cloud統合を配備済みです。Eufyは `eufy-security-ws`（3.1.0）とHA統合 `eufy_security`（v8.2.4）でログイン・デバイス一覧・Pushまで動作し、イベント取り込みを確認中です。ライブ映像はS4の新しいWebRTC方式のため当面使えません。Alexa連携は2026-09-12に見送りました。家電1台の操作・状態更新、再起動後の復帰、構成・履歴の復元を合格条件にします。

## 5. 既存game1でゲームとAIを検証する

既存game1（Bazzite、8vCPU、現行12GiB、cloud API管理下・引き取り済み）を利用する。GPUは割り当て済みだが、Wolf・Azaharの2人利用は別途検証する。IOMMUグループとGPU／音声機能を調べ、管理NICや必要なUSBを巻き込まないことを確認してからPCIパススルーを設定する。ホストの画面が使えなくなる可能性があるため、手順1のSSH・管理GUI経路を先に確保する。実機のPCIアドレスや起動方式に依存する設定を推測でコピーしない。[PCIパススルー公式](https://pve.proxmox.com/pve-docs/pve-admin-guide.html#qm_pci_passthrough)

Wolf → 1人のAzahar → 2人の独立セッション → 交換・対戦の順に確認する。30〜60分のプレイとVM再起動後のGPU再利用を[ゲームの合格条件](../architecture/gaming.md)で確認する。Ollamaは後から追加し、ゲーム中は推論を止める。

OpenHomeはgame1への同居希望として台帳に残す。製品／リポジトリが未特定なので、Linux対応・常駐要否・音声／GPU・保存先・必要RAMを確認してから追加する。常時必要な機能なら、利用時だけ起動するgame1の運用と両立するかも確認する。

**完了条件:** 2人プレイとセーブ永続化が確認できる。不具合がある間は既存ゲーム環境を残し、Home Assistantや他サービスの導入は進められる。

## 6. 常用Kubernetesを維持し、移行先を機能ごとに選ぶ

identity・cp・worker-01は構築済み。現在の起動状態は配備台帳を参照し、worker-02も含め不要時は停止する。再作成せず必要量から起動を判断する。管理PCからAnsibleを実行できる状態を正とする。**AWX は配備済み**（2026-09-12、[Kubernetes クラスタ](kubernetes.md)）。

1. OS・containerd・kubeadm・Ciliumの互換版を固定し、Pod／Service CIDRとLAN／VPNのアドレス重複を避ける。
2. nodeがReadyになることを確認し、名前解決・Pod間通信・NetworkPolicyを確認する。
3. ローカルPVC、MetalLB用の未使用IP範囲、cert-manager、Flux/SOPSを設定する。**完了（2026-09-12）**。Gateway の代わりに Cilium Ingress を使っている。
4. 軽量HTTPアプリとテストPVCで、内部HTTPS・VM再起動後の永続化・バックアップ復元を確認する。
5. アプリの移行はW01–W07へ分割。Homarr・Vaultwardenはservices-01、メディアはmedia-01へ移す。MkDocsは現行配置を維持する。
6. ポケモンDB・WebUI・agentはA01でgame1へ一式移行し、復元と接続を確認して切り替える。**AWX・Garage・Knative・自作APIは追加済み。NetBoxはservices-01に維持する。**

**完了条件:** worker再起動後もデータを読め、別環境へのDB復元ができる。worker VMが2台でも単一K11の故障には耐えないことを運用へ反映する。

## 7. 自動起動と日常運用を仕上げる

Proxmoxの自動起動順は、identity／storage／services-01（家電・印刷・Eufy中継を同居。VPNは追加予定） → cloud-01／control plane → workers → monitor-01／必要な入口を初期案とする。game・devは利用時起動。順番と待ち時間だけではアプリのreadinessを保証しないので、依存先へのリトライとヘルスチェックも確認する。

初期バックアップ方針は重要DB・HA設定・セーブを日次、VMを週次＋大きな変更前とし、データ変更頻度・容量に応じて見直す。これは日次なら最大約1日分を失い得る目安であり、実際の取得成功を監視する。ゲームの利用時間とバックアップ／大量走査をずらす。復元所要時間を測り、必要な復旧時間に収まるか確認する。

公開Webは内部運用が安定してからpublic-edgeを作成して統合する。動的VM・関数・DBは残余RAMとディスクの上限を設定してから提供する。

**完了条件:** K11再起動後に家電・認証・DB・アプリが戻り、別媒体バックアップの成功と復元手順を確認できる。
