# 開発参加ガイド

更新日: 2026-09-09。状態: **本文のコマンドは実機で実行して確認済み**。

## 前提

作業する環境は **Debian系のLinux**（Debian / Ubuntu）です。以下のコマンドはそれを前提にしています。

作業する場所は3つあります。コマンドブロックの前に必ずどこで実行するかを書きます。

| 場所 | 何を動かすか |
| --- | --- |
| **手元の作業機**（このリポジトリを clone した場所） | Terraform、`tools/tf`、`tools/devvm`、Ansible、テスト |
| **開発VM**（`dev-a` / `dev-b`） | アプリのコード、自作クラウドAPI、Flux のマニフェスト |
| **Proxmoxホスト** | `qm`、`pveum`、`vzdump`。復旧と調査のとき |

## 何が動いているか

ミニPC1台（Ryzen 9 8945HS / 61GiB RAM / 1TB NVMe）の Proxmox VE 9.2 上です。

| VM | VMID | IP | 中身 |
| --- | --- | --- | --- |
| services-01 | 150 | 192.168.10.200 | NetBox（IPと機器の台帳） |
| dev-a | 400 | 192.168.10.202 | 開発VM |
| dev-b | 401 | 192.168.10.203 | 開発VM |
| probe-01 | 900 | 192.168.10.201 | 復元ドリル用 |

Proxmox の Web は `https://192.168.10.126:8006`。Kubernetes・Garage・Knative・自作クラウドAPIは設計だけで、まだありません（[構成案](architecture/index.md)）。

## 1. 手元の作業機を用意する

実行場所: 手元の作業機

```bash
sudo apt install -y ansible python3-venv git curl
```

Terraform（1.10以降）と age を入れます。

```bash
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/hashicorp.gpg
echo "deb [signed-by=/etc/apt/keyrings/hashicorp.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y terraform age
```

SOPS は配布物がバイナリなので、チェックサムを確認して置きます。

```bash
VER=3.13.3
curl -sSfL -o /tmp/sops "https://github.com/getsops/sops/releases/download/v$VER/sops-v$VER.linux.amd64"
curl -sSfL -o /tmp/sums "https://github.com/getsops/sops/releases/download/v$VER/sops-v$VER.checksums.txt"
grep "linux.amd64$" /tmp/sums | awk '{print $1"  /tmp/sops"}' | sha256sum -c -
sudo install -m 0755 /tmp/sops /usr/local/bin/sops
```

NetBox の動的インベントリを使うには、Ansible が使う Python に依存が要ります。どの Python かは環境で変わるので確認してから入れてください。

```bash
head -1 "$(command -v ansible-inventory)"
```

そこに出た Python で `pynetbox` と `pytz` を入れ、collection も入れます。

```bash
ansible-galaxy collection install -r platform/ansible/requirements.yml
```

## 2. 参加に必要なもの

| 要るもの | 入手方法 |
| --- | --- |
| `192.168.10.126:22` への到達 | 同じLANなら直接。外からは経路が要る（下の「外から入る」） |
| SSH公開鍵の登録 | 自分の公開鍵を `platform/terraform/10-platform/terraform.tfvars` の `host_ssh_public_keys` へ入れて `tools/tf 10-platform apply` |
| age の秘密鍵 | 暗号化された資格情報を読むのに要る。既存の鍵を受け取るか、自分の公開鍵を `.sops.yaml` の受信者へ足して `sops updatekeys platform/sops/*.sops.yaml` |
| PVEのパスワードとAPIトークン | 発行済み。下で取り出す |

**PVEの資格情報を取り出す** — 実行場所: 手元の作業機、リポジトリのルート

```bash
tools/tf 00-bootstrap output -json dev_credentials
```

```bash
sops --decrypt platform/sops/pve-users.sops.yaml
```

前者が `devvm` 用のAPIトークン（`user@realm!name=uuid` の完全な形）、後者が Proxmox の画面にログインするパスワードです。

## 3. 開発VMへ接続する

### 前提: 公開鍵が入っていること

**パスワードでは入れません。** `common` ロールが sshd を `PasswordAuthentication no` にしていて、`debian` ユーザーのパスワードも設定されていません（ロック状態）。

入れるのは、VM作成時に cloud-init が `/home/debian/.ssh/authorized_keys` へ書いた公開鍵の持ち主だけです。中身は `platform/terraform/10-platform/terraform.tfvars` の `admin_ssh_public_keys`（全ホストへ入る）と `host_ssh_public_keys`（ホスト個別）で決まります。

自分の鍵をまだ入れていない場合は、先にそこへ足して適用します。

実行場所: 手元の作業機、リポジトリのルート

```bash
ssh-keygen -t ed25519 -C "$(whoami)@$(hostname)"
cat ~/.ssh/id_ed25519.pub
```

出た1行を `host_ssh_public_keys` の自分のホストへ足してから:

```bash
tools/tf 10-platform apply
```

### 同じLANから

実行場所: 手元の作業機

```bash
ssh -i ~/.ssh/id_ed25519 debian@192.168.10.203
```

鍵が `~/.ssh/id_ed25519` にあるか ssh-agent に入っていれば `-i` は省けます。

### Proxmoxホストを踏み台にする

`192.168.10.126:22` に届けば、そこを経由して開発VMに入れます（`AllowTcpForwarding yes`、確認済み）。

実行場所: 手元の作業機、`~/.ssh/config`

```
Host pve-jump
  HostName 192.168.10.126
  User root
  IdentityFile ~/.ssh/id_ed25519

Host dev-b
  HostName 192.168.10.203
  User debian
  IdentityFile ~/.ssh/id_ed25519
  ProxyJump pve-jump
```

```bash
ssh dev-b
```

VS Code の Remote-SSH もこの設定をそのまま使います。Ansible も `~/.ssh/config` を読むので、動的インベントリから流すときの鍵指定もここで済みます。

### 外から入る

`192.168.10.0/24` はNATの内側です。外から届かせる方法は決まっていません。選択肢は3つで、まだどれも配備していません。

| 方法 | 状態 |
| --- | --- |
| セルフホストVPN（`vpn-01`、VMID 105） | [比較中](architecture/vpn.md)。NetBirdが第一候補 |
| 公開した踏み台サーバー経由 | 未検討 |
| ルータのポート転送 | 未検討 |

決まったらここに書きます。

## 4. 開発VMを起動・停止する

`tools/devvm` が Proxmox の API を叩きます。設定を `~/.config/devvm/config`（0600）に置きます。値は手順2で取り出したものです。

実行場所: 手元の作業機

`PVE_ENDPOINT` は `https://192.168.10.126:8006`、`PVE_NODE` は `apextox`、`PVE_VMID` は自分のVMID、`PVE_TOKEN` は取り出したトークン、`SSH_TARGET` は `debian@<自分のVMのIP>`、自己署名証明書のままなので `PVE_INSECURE=1` です。雛形は `tools/devvm` の冒頭にあります。作ったら `chmod 600` します。

| コマンド | 何が起きるか |
| --- | --- |
| `devvm status` | Proxmox に現在の状態を問い合わせて表示する |
| `devvm start` | 起動を要求し、`running` になるまで待つ。既に起動していれば何もしない |
| `devvm ssh` | 止まっていれば起動してから、sshdが応答するのを待って入る |
| `devvm stop` | ACPI で正常終了させ、`stopped` になるまで待つ |
| `devvm restart` | 正常な再起動を要求する |

Proxmox の画面（`https://192.168.10.126:8006`、Realm は「Proxmox VE authentication server」）からも同じ操作ができます。**Shutdown** が `devvm stop` と同じ、**Stop** は電源を落とす強制停止です。

`dev-b@pve` のACLは `/vms/401` にだけ付いているので、画面にも `dev-b` だけが出ます。

## 5. VMを払い出す

**最終形は、自作クラウドAPIをTerraformの `homelab` Provider から叩く形です**（[最小クラウドとProvider](architecture/cloud.md)）。それが実装できるまでの暫定として、いまは `platform/terraform/hosts.yaml` に書くと作られます。GUIでも他の手段でも構いませんが、**NetBoxに構成が入ることだけは満たしてください**。台帳が実態とずれると、動的インベントリも払い出しも壊れます。

現在の書き方 — 実行場所: 手元の作業機、`platform/terraform/hosts.yaml`

```yaml
  dev-c:
    vm_id: 402
    pool: dev
    flavor: small
    disk_gib: 40
    on_boot: false
    started: true
    tags: [devbox, managed-by-terraform-admin]
    description: 用途を書く
```

| 項目 | 決め方 |
| --- | --- |
| `vm_id` | プールの範囲内で未使用のもの。範囲は `platform/terraform/pools.yaml`（platform 100-399 / dev 400-499 / lab 900-999 / cloud 5000-5999） |
| `flavor` | `platform/terraform/flavors.yaml` の `small` / `medium` / `large` / `xlarge` |
| `tags` | `platform/terraform/tags.yaml` にあるもの。Ansibleのグループ分けに使われる |

IPは書きません。NetBox が `192.168.10.201`〜`.249` から採番します。

`10-platform` は NetBox に到達する必要があります。NetBox は `services-01` の localhost にしか出ていないので、**作業機の上で**ポート転送を張ります。

実行場所: 手元の作業機、別のシェル

```bash
ssh -N -L 8001:127.0.0.1:8000 debian@192.168.10.200
```

実行場所: 手元の作業機、リポジトリのルート

```bash
tools/tf 10-platform plan
```

作られるものを確認してから適用します。

```bash
tools/tf 10-platform apply
```

Debian の cloud image には `qemu-guest-agent` が入っていないため、Terraform はエージェントの応答を待って**戻ってきません**。別のシェルから Ansible を流すと待ちが解けます。

実行場所: 手元の作業機、リポジトリのルート

```bash
set -a; . platform/ansible/netbox.env; set +a
ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/guests.yml
```

これで `common` ロール（guest agent、時刻、sshd）と、`devbox` タグが付いていれば開発用の道具（Terraform・Docker・age）が入ります。`platform/ansible/netbox.env` は NetBox の読み取り専用トークンで、雛形は `platform/ansible/netbox.env.example` です。

## 6. 設計思想

コードとドキュメントに根拠があるものだけを挙げます。

- **手作業の最小化。** コードで管理できるものはコードにします。残っている手作業は[初回セットアップの順番](operations/bootstrap.md)に理由付きで一覧にしてあります（README「設計上の決定」）。
- **広く採用された形式を選ぶ。** ロックイン回避は命名ではなくインターフェースの選択です。state置き場はS3互換なので R2 / Garage / MinIO のどれでも同じコードが動きます。事業者固有APIへの依存は `platform/terraform/state-store` の1モジュールに閉じ込めています（README「設計上の決定」）。
- **同じオブジェクトを2つのstateで管理しない。** 誰が何を作るかは[IaCの所有境界](architecture/iac.md)が正本です（`architecture/operations.md`）。
- **秘密値と状態の分離。** Gitにはコード・設定例・ロックファイルだけ。資格情報はSOPS+ageで暗号化したものを追跡します（README「設計上の決定」）。
- **再実行と再現性。** `terraform plan` の2回目が `No changes`、`ansible-playbook` の2回目が `changed=0` になることを各手順の完了条件にしています（`architecture/bring-up.md`）。
- **Ansibleはロールと用途別のplaybook。** 処理は `platform/ansible/roles/` に置き、用途ごとの playbook を `site.yml` が `import_playbook` でまとめます。AWX の Job Template は playbook 単位なのでこの形にしています。

## 7. 知っておくと詰まらないこと

- **ゲストOSは Debian 13 (trixie)** です。Proxmox VE 9.2 自体が Debian 13 上で動いているので土台を揃えました。`architecture/bring-up.md` の「公式のDebian／Ubuntu cloud image」の範囲内の選択で、`platform/terraform/00-bootstrap/terraform.tfvars` の `cloud_images` でURLとチェックサムを指定しているだけなので Ubuntu へ差し替えられます。Ansible の `common` ロールはどちらも通ります。
- **ミニPC1台・SSD1枚**です。VMを増やしてもハードウェア障害には耐えません。RAMは61GiB、設計上の配分は[配分表](architecture/operations.md#resource-budget)にあります。
- **Terraformのstateには秘密値が平文で入ります。** S3互換ストレージ（現在はCloudflare R2）に置いてあります。`sensitive` 指定は表示を隠すだけです。
- **`.sops.yaml` はリポジトリのルート**にあります。sopsはカレントから上へ辿って探すので、別の場所に置くと見つかりません。
- **基盤のTerraformは手元の作業機から実行します。** `00-bootstrap` / `05-seed` / `10-platform` のstateが開発VM自身を作っているため、開発VM上で動かすと循環します。開発VMで書くのは、その上に載るものです。
- **動的インベントリには NetBox の primary IP が要ります。** `has_primary_ip` で絞っているため、設定されていないVMは出てきません。`managed-host` モジュールが `netbox_primary_ip` で設定します。
- **ログイン名は `platform/ansible/group_vars/terraform_managed.yml`** にあります。NetBoxは名前とIPしか持たないためです。SSH鍵は各自の `~/.ssh/config` で指定します。

## 8. リポジトリの歩き方

| 場所 | 中身 |
| --- | --- |
| `platform/terraform/` | `hosts.yaml`、`pools.yaml`、`flavors.yaml`、`tags.yaml` と各ルートモジュール |
| `platform/ansible/` | `site.yml`、用途別のplaybook、`roles/`、`group_vars/` |
| `platform/sops/` | 暗号化した資格情報 |
| `stacks/` | 稼働中のCompose一式。直下が配備先 `/opt/media-stack` に対応 |
| `tools/` | `tf`（Terraform実行ラッパー）、`devvm`、`ensure-secrets.py`、公開前チェック |
| `docs/` | 日本語ドキュメント。`mkdocs build` でサイトになる |

## 9. 変更を入れる

実行場所: 手元の作業機、リポジトリのルート。

```bash
python3 -m venv .venv
.venv/bin/pip install -r stacks/hub/requirements.txt -r tools/requirements.txt
```

| コマンド | 何を見るか |
| --- | --- |
| `.venv/bin/python -m unittest discover -s tests` | 宣言ファイルの整合（VMIDの範囲・重複・タグ）と既存の回帰 |
| `.venv/bin/python -m mkdocs build --strict` | ドキュメントのリンク切れ |
| `.venv/bin/python -m yamllint -c .yamllint .` | YAMLの壊れ |
| `terraform fmt -check -recursive platform/terraform` | HCLの整形 |
| `.venv/bin/python tools/check-publication.py` | 暗号化し忘れた秘密値。`git add` の後に実行する |

CIも同じものを回します。ドキュメントを足すときは[書き方](overview.md)の6節構成に合わせてください。
