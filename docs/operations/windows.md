# Windows 11 Pro の VM をポータルから作る

更新日: 2026-09-12。状態: **API・ポータル対応を実装。ゴールデンイメージの作成は管理者の一度きりの作業**。

Linux の cloud image は `images.yaml` の URL から自動取得しますが、Windows のインストールメディアとプロダクトキーは配布元から自動取得できません。そのため **Windows 11 Pro を一度だけ Proxmox 上へインストールして「ゴールデンイメージ」を作り、`cloud-images` へ置く**。以降はポータルの「インスタンスを作成」でそのイメージを選ぶだけで作れます。

## 仕組み（何が自動か）

イメージに `os: windows` を宣言すると、API は Linux の VM と次の点だけ変えて作ります。

| | Linux（既定） | Windows（`os: windows`） |
| --- | --- | --- |
| `ostype` | `l26` | `win11` |
| ファームウェア | SeaBIOS（既定） | `bios=ovmf` + `machine=q35` |
| TPM | なし | `tpmstate0`（v2.0）、EFI ディスクは `pre-enrolled-keys=1` |
| 初回設定 | cloud-init（NoCloud、network config v2） | cloudbase-init（NoCloud、network config v1） |
| SSH鍵 | seed の `meta-data` へ | 使わない（ポータルでも入力を隠す） |
| ディスク/NIC/seed | `virtio0`・virtio NIC・CIDATA の seed ISO | 同じ（イメージに virtio ドライバが要る） |

ホスト名と固定 IP（NetBox が採番）は、Linux と同じ seed ISO から cloudbase-init が読みます。**管理用パスワードは API から渡しません。** Windows のローカル管理者はイメージ作成時に決め、初回ログインで変更してください。

## 管理者の作業（一度きり）

### 1. メディアを用意する

- Windows 11 Pro の ISO（Microsoft の公式サイト。プロダクトキーは各自のライセンス）
- `virtio-win.iso`（<https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso>）
- `cloudbase-init` のインストーラー（<https://cloudbase-init.readthedocs.io/en/latest/intro.html>）

Proxmox の `local` ストレージへ ISO を置きます（Web UI か `qm` でアップロード）。

### 2. ビルド用 VM を作ってインストールする

クラウドのプールの外（管理者の VMID）で作ります。例:

```bash
qm create 9001 --name win11-golden --memory 8192 --cores 4 --cpu host \
  --bios ovmf --machine q35 \
  --efidisk0 local-lvm:0,efitype=4m,pre-enrolled-keys=1 \
  --tpmstate0 local-lvm:4,version=v2.0 \
  --scsihw virtio-scsi-single \
  --scsi0 local-lvm:64,iothread=1,discard=on \
  --net0 virtio,bridge=vmbr0 \
  --ide2 local:iso/Win11.iso,media=cdrom \
  --ide3 local:iso/virtio-win.iso,media=cdrom \
  --ostype win11 --boot order=scsi0
qm start 9001
```

コンソール（noVNC）で Windows 11 Pro をインストールします。**インストール先が見えないときは「ドライバーの読み込み」から `vioscsi\w11\amd64` を選びます**（`virtio-win` の CD 内）。Windows のセットアップが終わったら、`virtio-win` の CD から次を入れます。

- `NetKVM\w11\amd64`（ネットワーク）
- `vioscsi` / `viostor`（ストレージ。インストール時に入れていれば不要）
- `guest-agent\qemu-ga-x86_64.msi`（QEMU Guest Agent）

### 3. cloudbase-init を入れて NoCloud 用に設定する

`cloudbase-init` をインストールし、`C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf\cloudbase-init.conf` と `cloudbase-init-unattend.conf` の `metadata_services` を NoCloud だけにします。

```ini
[DEFAULT]
username=Administrator
metadata_services=cloudbaseinit.metadata.services.nocloudservice.NoCloudConfigDriveService
plugins=cloudbaseinit.plugins.common.sethostname.SetHostNamePlugin,
        cloudbaseinit.plugins.common.networkconfig.NetworkConfigPlugin
allow_reboot=false
stop_service_on_exit=false
```

NoCloud の ISO は API がインスタンスごとに作る `CIDATA` ラベルの CD-ROM です。ネットワークは **cloud-init の network config v1**（cloudbase-init が解釈できる唯一の形式）で渡します。

### 4. sysprep してシャットダウンする

`sysprep /oobe /generalize /shutdown /unattend:<unattend.xml>` を実行します。unattend では `specialize` パスで cloudbase-init（unattend 用 conf）を起動し、`oobeSystem` で OOBE を最小化してください。cloudbase-init 付属のサンプル unattend と手順をそのまま使うのが確実です（[cloudbase-init Tutorial](https://cloudbase-init.readthedocs.io/en/latest/tutorial.html)）。

シャットダウン後、**ビルド用 VM を起動しないでください**（起動すると sysprep が無効になります）。

### 5. ゴールデンイメージを cloud-images へ置く

ビルド用 VM のディスクを qcow2 へ変換し、Proxmox の `/srv/cloud-images/import/win11pro.qcow2` へ置きます（`cloud_images_path` の既定。`platform/terraform/site.yaml`）。

```bash
# Proxmox ホストで
qemu-img convert -O qcow2 /dev/pve/vm-9001-disk-0 /srv/cloud-images/import/win11pro.qcow2
chown root:root /srv/cloud-images/import/win11pro.qcow2
chmod 0644 /srv/cloud-images/import/win11pro.qcow2
```

### 6. 宣言して配備する

`platform/terraform/images.yaml` のコメントアウトした `win11pro` を有効にします。

```yaml
  win11pro:
    file_name: win11pro.qcow2
    os: windows
    provided: true
    content_type: import
    shared_with_cloud: true
```

`provided: true` は「URL が無いので 00-bootstrap は取得しない。管理者が置いたものを使う」という意味です。編集したら配備します。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/cloud.yml'
```

## 利用者の作業（ポータル）

1. 「インスタンス」→「インスタンスを作成」。
2. イメージで `win11pro（Windows 11）` を選ぶ。SSH鍵の欄は消え、コンソールでセットアップする案内が出ます。
3. 名前・vCPU・メモリ・ディスク（Windows 11 は **64 GiB 以上**）とセキュリティグループを決めて「作成内容を確認」→作成。
4. 起動したら一覧の「コンソール」を開き、Windows の初期設定（地域・アカウント・プロダクトキー）を行います。

ホスト名と IP は起動時に自動で設定されます。RDP を使う場合は 3389 を許可するセキュリティグループを作ってください。**Windows の初期設定とライセンス認証は利用者が行います。**

## 困ったとき

| 症状 | 原因 | 対応 |
| --- | --- | --- |
| 「この PC では Windows 11 を実行できません」 | OVMF・TPM が無い、または `machine` が q35 でない | イメージ宣言の `os: windows` を確認し、配備し直す |
| ディスクが見えずインストールできない | virtio ドライバ未導入 | セットアップ時に `vioscsi\w11\amd64` を読み込む |
| 起動後ネットワークが無い | cloudbase-init が NoCloud を読めていない | `cloudbase-init.log` を確認。`metadata_services` を NoCloud だけにする |
| 同じ IP が二重に付く | イメージ側に固定 IP が残っている | sysprep 前に DHCP へ戻す |
| `import-from` が失敗する | `cloud-images` にファイルが無い/名前違い | `file_name` と `/srv/cloud-images/import/` の名前を一致させる |
