# K11到着後・Proxmox VE導入後の進め方

[構成案トップ](index.md) / [VM配分・サービス配置](operations.md#resource-budget)

状態: **手順の記録**。Proxmox・VM・Kubernetes・AWX・クラウドAPI は 2026-09-12 までに実機で構築済みで、この文書はその順番を残すためのものです。**現在の状態は[配備台帳](../operations/handover.md)を正とします。** 64GB／1TBのK11を想定します。全VMの一括作成や既存サービスの一括移行は行いません。

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
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/site.yml --tags survey
```

生成された `.survey/<ホスト名>.md` の冒頭に「Terraformへ転記する値」の表があります。ノード名、VMディスク用ストレージ名、cloud image置き場、**cloud-init snippetを置けるストレージ**、bridge名とvlan-awareの有無、既存LANのサブネットとgateway、使用済みVMIDを埋めてから次へ進みます。`snippets` を持つストレージが無い場合、cloud-initの追加設定は投入できないため、先にProxmox側でcontent種別を追加します。このファイル自体は台帳ではありません。必要な値を非公開台帳へ転記し、`.survey/` は作業用の一時出力として扱います。

- BIOSの仮想化／IOMMU、RAM、SSD、冷却とファン動作を確認する。iGPUの固定予約は実測前に16GiBへ増やさない。
- 管理用IP・ホスト名・gateway・DNS・時刻同期を固定／確認する。既存ネットワークと重複しないIPを使い、bridgeの物理NIC割り当てを確認する。
- GUIで導入版に対応する公式リポジトリを選び、契約の有無に合った更新元を使う。更新後に再起動し、管理PCから再接続する。異なるDebian／Proxmox版のapt行を混ぜない。
- SSH鍵とローカル復旧用管理者を確保する。VPN経由の管理も確認する。Proxmox管理画面をインターネットへ直接公開しない。
- インストール済みストレージを台帳へ記録する。`local`／`local-lvm`／ZFSなどの実構成に合わせる。配分表のためにSSDを再初期化しない。

**完了条件:** 再起動後もGUI・SSH・DNS・時刻が正常で、管理LANから復旧できる。GPUをゲストへ渡す前にこの状態を作る。[Proxmox公式管理ガイド](https://pve.proxmox.com/pve-docs/pve-admin-guide.html)

## 2. 管理台帳とバックアップ先を先に作る

非公開台帳へ、VMID・VM名・IP予約・用途・vCPU/RAM・ディスク／保存先・起動順・バックアップ対象・確認日を記録する。初期値は[VM配分表](operations.md#resource-budget)を転記し、未作成／検証中／稼働／移行済みを区別する。APIキーやパスワード自体は台帳へ直書きしない。

別USBディスク・既存機器・NAS等のバックアップ先を1つ確保する。対象デバイスと既存データを確認してから設定する。同じ内蔵SSDの別パーティションやスナップショットだけを故障対策にしない。PBSは後から追加できる。

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
sops exec-env platform/sops/proxmox.sops.yaml   'terraform -chdir=platform/terraform/10-platform apply'

# 2. ゲストOSの共通設定
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml   platform/ansible/site.yml --tags guests --limit probe-01

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
.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml   platform/ansible/site.yml --tags guests --limit dev-a
```

`DevVMOperator` に含まれるのは `VM.Audit` / `VM.PowerMgmt` / `VM.Console` だけです。CPU・RAM・ディスク・NICの正本は `hosts.yaml` のままなので、利用者の操作でIaCと実機が乖離しません。使い方は[開発VMの使い方](../services/devvm.md)を利用者へ渡します。

**完了条件:** 2人がそれぞれ `devvm start` → `ssh` → 作業 → `devvm stop` を一周できる。相手のVMが一覧に出ない。`terraform plan` が `No changes` のまま。

### セルフホストVPN用の枠を確保する

`vpn-01`（2vCPU／2GiB／16GiB）を[VPN比較](vpn.md)に沿って準備する。NetBirdを第一検証候補とし、Tailscaleの独立した復旧経路を先に確認する。セルフホストVPNの外部到達・認証入口の条件が揃うまでは、宅内LAN／既存Tailscaleで後続作業を進める。公開用ドメイン・CGNAT・ルータ転送・スマホ対応の確認前に公開しない。

## 4. Home Assistantを単独で立ち上げる

公式のHAOS KVM用イメージを使用し、2vCPU・4GiB・32GiB以上、UEFI構成で専用VMを作る。イメージの元ディスクより小さくしない。公式VM手順に従ってSecure Boot等を設定し、LANへbridge接続する。VMへのインポート先ストレージ名は実機値を使う。[HAOS公式VM手順](https://www.home-assistant.io/installation/alternative/)

1. DHCPの割り当てを確認し、IP予約を設定する。LANの `http://<HAのIP>:8123` から初期設定する。
2. SwitchBotの1台で操作と状態更新を確認する。Bluetooth利用時はVMへのデバイス割り当てと電波到達を先に確認する。
3. 自動化を1つだけ作り、HAOS再起動後にも動くことを確認する。
4. HAバックアップを外部保存し、復号に必要な情報も保管する。
5. EchoのAlexa操作、EufyCam S4連携を[機器別の確認項目](operations.md#home-devices)に沿って追加する。

**完了条件:** 家電1台を操作でき、再起動後も設定・状態が戻る。カメラ互換性の未解決を理由に他の基盤作業は止めない。

## 5. game-01で780Mを先に検証する

Linux VM（8vCPU、CPU type host、12GiB、OS48＋データ96GiB）を用意する。IOMMUグループとGPU／音声機能を調べ、管理NICや必要なUSBを巻き込まないことを確認してからPCIパススルーを設定する。ホストの画面が使えなくなる可能性があるため、手順1のSSH・管理GUI経路を先に確保する。実機のPCIアドレスや起動方式に依存する設定を推測でコピーしない。[PCIパススルー公式](https://pve.proxmox.com/pve-docs/pve-admin-guide.html#qm_pci_passthrough)

Wolf → 1人のAzahar → 2人の独立セッション → 交換・対戦の順に確認する。30〜60分のプレイとVM再起動後のGPU再利用を[ゲームの合格条件](gaming.md)で確認する。Ollamaは後から追加し、ゲーム中は推論を止める。

OpenHomeはgame-01への同居希望として台帳に残す。製品／リポジトリが未特定なので、Linux対応・常駐要否・音声／GPU・保存先・必要RAMを確認してから追加する。常時必要な機能なら、利用時だけ起動するgame-01の運用と両立するかも確認する。

**完了条件:** 2人プレイとセーブ永続化が確認できる。不具合がある間は既存ゲーム環境を残し、Home Assistantや他サービスの導入は進められる。

## 6. 常用クラスタを組み、小さいサービスから移す

`identity`、`k8s-cp-01`、`k8s-worker-01`、`k8s-worker-02`を配分表の値で作成する。管理PCからAnsibleを実行できる状態を正とする。**AWX は配備済み**（2026-09-12、[Kubernetes クラスタ](../operations/kubernetes.md)）。

1. OS・containerd・kubeadm・Ciliumの互換版を固定し、Pod／Service CIDRとLAN／VPNのアドレス重複を避ける。
2. nodeがReadyになることを確認し、名前解決・Pod間通信・NetworkPolicyを確認する。
3. ローカルPVC、MetalLB用の未使用IP範囲、cert-manager、Flux/SOPSを設定する。**完了（2026-09-12）**。Gateway の代わりに Cilium Ingress を使っている。
4. 軽量HTTPアプリとテストPVCで、内部HTTPS・VM再起動後の永続化・バックアップ復元を確認する。
5. Homarr／MkDocs、読み取り中心のメディアを移し、ポケモンDB・WebUI・agentは[移行単位と合格条件](operations.md#pokemon-db)に従って移す。
6. Nextcloud／Vaultwardenを復元テスト後に切り替える。**AWX・Garage・Knative・自作API は追加済み（2026-09-12）。NetBox は services-01 のままで、Kubernetes への移行は未実施。** RAM・SSD・CPUを毎回測る。

**完了条件:** worker再起動後もデータを読め、別環境へのDB復元ができる。worker VMが2台でも単一K11の故障には耐えないことを運用へ反映する。

## 7. 自動起動と日常運用を仕上げる

Proxmoxの自動起動順は、HAOS／identity／storage → vpn-01 → control plane → workers → 必要な入口を初期案とする。game・devは利用時起動。順番と待ち時間だけではアプリのreadinessを保証しないので、依存先へのリトライとヘルスチェックも確認する。

初期バックアップ方針は重要DB・HA設定・セーブを日次、VMを週次＋大きな変更前とし、データ変更頻度・容量に応じて見直す。これは日次なら最大約1日分を失い得る目安であり、実際の取得成功を監視する。ゲームの利用時間とバックアップ／大量走査をずらす。復元所要時間を測り、必要な復旧時間に収まるか確認する。

公開Webは内部運用が安定してからpublic-edgeを作成して統合する。動的VM・関数・DBは残余RAMとディスクの上限を設定してから提供する。

**完了条件:** K11再起動後に家電・認証・DB・アプリが戻り、別媒体バックアップの成功と復元手順を確認できる。
