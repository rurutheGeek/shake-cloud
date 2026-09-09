# 開発VMの使い方

更新日: 2026-09-09。状態: **実機未確認**。VMの定義と権限はコード化済み、実機への適用はこれから。

2人がそれぞれ1台ずつ、GUIなしのLinux VMを持ちます。SSHとVS Code Remote SSHで使い、**使うときだけ起動します**。

| | 値 |
| --- | --- |
| 台数 | 2台（`dev-a`＝VMID 400、`dev-b`＝VMID 401） |
| サイズ | 2vCPU / RAM 2GiB / ディスク 40GiB |
| 自動起動 | しない。K11を再起動しても止まったまま |
| 相手のVM | 見えない。操作もできない |

`onboot: false` なのでK11を再起動しても止まったままです。RAMは全体で61GiBを分け合っており、設計上の配分は[配分表](../architecture/operations.md#resource-budget)にあります。

## 1. 何ができるか

起動・停止・再起動・コンソール接続ができます。

VMの形（CPU・RAM・ディスク・NIC）の正本は `platform/terraform/hosts.yaml` です。ここを直して `tools/tf 10-platform apply` すると反映されます。Proxmoxの画面から直接変えると次の apply で戻ります。`DevVMOperator` ロールには `VM.Config.*` が含まれていないので、画面からは変更できません。

## 2. どの利用者に影響するか

自分だけです。`dev-a` の権限は `/vms/400` にしか付いていないので、Proxmoxの画面にも自分のVMしか出ません。

## 3. 設定場所

| 対象 | 場所 |
| --- | --- |
| PVEのログイン | Realm は「Proxmox VE authentication server」。パスワードは `platform/sops/pve-users.sops.yaml` にある |
| CLIの設定 | `~/.config/devvm/config`（権限 0600） |
| SSHの別名 | `~/.ssh/config` |

## 4. 具体的な入力例

### 電源を操作する（GUI）

`https://<PVEのIP>:8006` を開き、Realm に「Proxmox VE authentication server」を選んでログインします。左のツリーに自分のVMだけが出ます。VMを選んで右上のボタンを使います。

| ボタン | 動作 | 使いどころ |
| --- | --- | --- |
| Start | 起動 | 使い始め |
| Shutdown | ACPI経由の正常終了 | **通常の停止はこれ** |
| Stop | 電源を切る（強制） | 応答しなくなったときだけ |
| Reboot | 正常な再起動 | カーネル更新のあとなど |

Stop はゲストOSに終了処理をさせません。書き込み中のファイルが壊れることがあるので、Shutdown が効かないときだけ使います。

### 電源を操作する（CLI）

`tools/devvm` はProxmoxのAPIを呼ぶだけの薄いラッパーです。先に設定を置きます。

```bash
mkdir -p ~/.config/devvm
cat > ~/.config/devvm/config <<'CONF'
PVE_ENDPOINT=https://192.0.2.10:8006
PVE_NODE=pve
PVE_VMID=400
PVE_TOKEN='dev-a@pve!devvm=00000000-0000-0000-0000-000000000000'
SSH_TARGET=debian@192.0.2.40
CONF
chmod 600 ~/.config/devvm/config
```

パスワードとトークンはコードで発行済みです。手で作る必要はありません。取り出し方（実行場所: 管理PC、リポジトリのルート）:

```bash
tools/tf 00-bootstrap output -json dev_credentials   # トークン
sops --decrypt platform/sops/pve-users.sops.yaml     # GUI用パスワード
```

```bash
devvm status      # 起動しているか
devvm start       # 起動して、起動を確認するまで待つ
devvm ssh         # 止まっていれば起動してからSSHで入る
devvm stop        # 正常終了（GUIのShutdownと同じ）
devvm restart     # 正常な再起動
```

`start` と `stop` は繰り返し実行しても安全です。すでにその状態なら何もしません。

### SSHで入る

パスワードでも公開鍵でも入れます。パスワードは `platform/sops/devvm-users.sops.yaml` にホストごとに入っています。

```bash
sops --decrypt platform/sops/devvm-users.sops.yaml
```


`~/.ssh/config` に別名を書いておくと、VS Code Remote SSH からも同じ設定が使えます。

```
Host dev-a
  HostName 192.0.2.40
  User debian
  IdentityFile ~/.ssh/id_ed25519
```

```bash
ssh dev-a
```

VS Code は「Remote-SSH: Connect to Host」で `dev-a` を選びます。

### コンソールで入る（復旧用）

ネットワーク設定やsshdを壊してSSHで入れなくなったときは、Proxmoxの画面でVMを選び「Console」を開きます。**これは復旧経路であり、普段の接続方法ではありません。**

## 5. 変更後の確認方法

一周してみてください。`devvm start` → `ssh dev-a` → 作業 → `exit` → `devvm stop`。

再起動してもホームディレクトリとSSH鍵が残ることを確認します。相手のVMが一覧に出ないことも確認してください。出るようならACLの設定ミスです。

## 6. 元に戻す方法と注意点

- **宅外からは使えません。** VPN（`vpn-01`）が入るまでは宅内LANからだけです。ProxmoxのWeb画面をインターネットへ公開しません。
- どの鍵がどのVMに入るかは `platform/terraform/10-platform/terraform.tfvars` の `admin_ssh_public_keys`（全ホスト）と `host_ssh_public_keys`（ホスト個別）で決まります。
- VM自体はTerraformで作り直せますが、その際ディスクの中身は失われます。
- `~/tf`（0700）が各VMのTerraform state置き場として用意してあります。
- 電源の状態をTerraformは追いかけません。止めたVMを勝手に起動し直すことはありません。
