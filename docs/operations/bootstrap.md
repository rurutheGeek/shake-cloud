# 初回セットアップの順番

更新日: 2026-09-09。状態: **手順1〜4は実機で確認済み。5以降は未実施**。

この文書は「まっさらな管理端末から、Proxmox上に最初のVMが立つまで」を一本道でまとめたものです。個々の詳細は各文書にありますが、**順番と実機で引っかかる点**はここに集約します。

- 秘密値の扱い → [秘密値の管理](secrets.md)
- Terraformの詳細 → [Terraformの実行](terraform.md)
- 誰が何を所有するか → [IaCの所有境界](../architecture/iac.md)
- 実機側の作業 → [Proxmox導入後の手順](../architecture/bring-up.md)

## 0. 管理端末に入れるもの

| 道具 | 用途 | Windowsでの入れ方 |
| --- | --- | --- |
| Terraform | Proxmox・NetBoxの宣言。**1.10以降**（stateロックに必要） | `winget install Hashicorp.Terraform` |
| SOPS | 資格情報の暗号化 | `winget install SecretsOPerationS.SOPS` |
| age | SOPSの鍵 | `winget install FiloSottile.age` |
| Ansible | ゲストOSの構成 | **Windowsでは動きません。**WSLのUbuntuへ `apt install ansible` |

`ansible-core` はWindowsを制御ノードとしてサポートしません。WSL2のUbuntuを制御ノードにします。リポジトリは `/mnt/c/...` から見えます。

`winget` でパスを追加した直後は、**シェルを開き直さないと `terraform` や `sops` が見つかりません**。

## 1. age鍵を作り、`.sops.yaml` をルートへ置く

```bash
age-keygen -o ~/.config/sops/age/keys.txt
grep 'public key' ~/.config/sops/age/keys.txt
cp .sops.yaml.example .sops.yaml
# age1... の公開鍵へ置き換える
```

**`.sops.yaml` はリポジトリのルートに置きます。** sopsはカレントディレクトリから上へ辿って設定を探すので、`platform/sops/` に置くとルートから実行したときに見つかりません。公開鍵しか入らないのでGitへコミットします。

`path_regex` は**絶対パス**に対して評価されます。Windowsでは区切りが `\` になるため、雛形は `platform[\\/]sops[\\/]` と書いてあります。片方だけにすると一致しません。

### Windowsでは鍵の場所を教える必要があります

sopsが既定で見るのは `%AppData%\sops\age\keys.txt` です。上の手順で作った鍵は `~/.config/sops/age/keys.txt` にあるので、そのままでは**暗号化はできるのに復号できません**。環境変数で指定します。

```powershell
[Environment]::SetEnvironmentVariable(
  'SOPS_AGE_KEY_FILE', "$env:USERPROFILE\.config\sops\age\keys.txt", 'User')
```

設定後はシェルを開き直します。WSLから使う場合は `/mnt/c/Users/<名前>/.config/sops/age/keys.txt` を同じ変数に入れます。

## 2. ProxmoxのAPIトークンを作る（唯一の手作業）

Proxmoxの画面で **データセンター → 権限 → APIトークン → 追加**。ユーザーは `root@pam`、トークンIDは任意（例 `bootstrap`）、**「特権の分離」のチェックを外します**。作成直後に一度だけ表示される秘密値を控えます。

`00-bootstrap` が作る `terraform@pve` は自分自身を作れないため、この1段だけ上位の資格情報が要ります。以降はこのトークンを使いません。

## 3. トークンをSOPSへ入れる

```bash
cp platform/sops/proxmox-root.sops.yaml.example platform/sops/proxmox-root.sops.yaml
```

`platform/sops/proxmox-root.sops.yaml` を開き、次の2つを実値にします。

- `PROXMOX_VE_ENDPOINT` … `https://<ProxmoxのIP>:8006/`
- `PROXMOX_VE_API_TOKEN` … `root@pam!<トークンID>=<秘密値>` の形

保存したら**必ず暗号化してから**次へ進みます。

```bash
sops --encrypt --in-place platform/sops/proxmox-root.sops.yaml
sops --decrypt platform/sops/proxmox-root.sops.yaml   # 読めることの確認
```

暗号化を忘れてコミットしようとすると `tools/check-publication.py` が止めます。ただしこれは補助であり、`git diff --cached` の目視も行います。平文で一度でもpushしたトークンは**失効・再発行**します。

## 4. Proxmoxホストの棚卸し（読み取りのみ）

先に手動でSSHし、ホスト鍵の指紋を確認します。**表示された指紋をProxmox側の実物と突き合わせてから** `yes` と答えます。

```bash
# Proxmoxのホスト上（GUIのShell）で
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub

# 管理端末から
ssh root@<ProxmoxのIP>
```

WSLから棚卸しを実行します。

```bash
cp platform/ansible/pve.ini.example platform/ansible/pve.ini
# 接続先を編集
ansible-playbook -i platform/ansible/pve.ini platform/ansible/survey-pve.yml
```

出力は管理端末の `.survey/<ホスト名>.md` です。Gitからは除外されています。

### WSLで出る警告について

`/mnt/c` は誰でも書ける扱いになるため、Ansibleが「world writable directory」として `ansible.cfg` を無視します。ロールは playbook の隣（`platform/ansible/roles/`）から解決されるので動作に影響はありませんが、設定を効かせたい場合は明示します。

```bash
ANSIBLE_CONFIG=/mnt/c/.../shake-cloud/ansible.cfg ansible-playbook ...
```

SSH秘密鍵を `/mnt/c` に置いたままだと、パーミッションが緩すぎるとしてsshが拒否します。WSL側の `~/.ssh/` へ 0600 でコピーして使います。

## 5. Proxmoxの所有境界を作る

`.survey/` の「Terraformへ転記する値」を埋めてから進みます。

```bash
sops exec-env platform/sops/proxmox-root.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap init'
sops exec-env platform/sops/proxmox-root.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap plan'
sops exec-env platform/sops/proxmox-root.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap apply'
```

`sops exec-env` はWindowsでもシェル経由ではなく直接コマンドを起動します。環境変数は子プロセスへ渡りますが、**引用符の中でシェルの展開（`$VAR` など）は効きません**。単純なコマンドだけを書きます。

出てきたトークンをそのまま次の資格情報にします。

```bash
cp platform/sops/proxmox.sops.yaml.example platform/sops/proxmox.sops.yaml
terraform -chdir=platform/terraform/00-bootstrap output -raw automation_token_value
# 表示された値を PROXMOX_VE_API_TOKEN へ入れてから
sops --encrypt --in-place platform/sops/proxmox.sops.yaml
```

**完了条件:** 2回目の `apply` が `No changes`。`terraform@pve` から `cloud` プールが操作できないこと。

## 6. 最初の1台を作る（05-seed）

`10-platform` はNetBoxにIPを採番させる設計なので、**NetBox自身の置き場はそれでは作れません**（鶏と卵）。`stacks/netbox/README.md` が「NetBox本体を作る初回だけ静的なSSH指定を使用します」と書いているのと同じ理由で、`platform/terraform/05-seed` だけはNetBoxを使わず静的IPで1台作ります。

cloud imageの取得は `00-bootstrap`（`root@pam`）の担当です。ProxmoxのURLメタデータ取得APIは `/` に対する `Sys.Audit` と `Sys.Modify` を要求するため、プールとストレージに絞った `terraform@pve` では実行できません。特権が要る一度きりの作業を上位の資格情報側へ寄せています。

```bash
cp platform/terraform/05-seed/terraform.tfvars.example platform/terraform/05-seed/terraform.tfvars
# 00-bootstrap の cloud_image_file_ids 出力と、棚卸しの値を転記する
terraform -chdir=platform/terraform/00-bootstrap output cloud_image_file_ids

sops exec-env platform/sops/proxmox.sops.yaml   'terraform -chdir=platform/terraform/05-seed apply'
```

`ipv4_cidr` は**ルータのDHCP配布範囲の外**にします。範囲は外から見えないので、ルータの管理画面で確認してから決めます。

Debianのcloud imageには `qemu-guest-agent` が入っていません。Terraformはエージェントの応答を待つので、**作成直後は `apply` が待ち状態のままになります**。別のシェルからAnsibleを流すと待ちが解けます。

```bash
cp platform/ansible/seed.ini.example platform/ansible/seed.ini
# 接続先を編集
ansible-playbook -i platform/ansible/seed.ini platform/ansible/guests.yml --limit seed
```

**完了条件:** 2回目の `terraform plan` が `No changes`、2回目の `ansible-playbook` が `changed=0`。

## 7. NetBoxとその後

NetBoxの構築はリポジトリの `stacks/netbox/README.md`、その後の流れは[Proxmox導入後の手順](../architecture/bring-up.md)へ続きます。

## つまずいたときの対応表

| 症状 | 原因 | 対応 |
| --- | --- | --- |
| `terraform` / `sops` が見つからない | wingetのパス反映前 | シェルを開き直す |
| stateのR2移行で `NoSuchBucket` | バケット名かエンドポイントの誤り | `r2.sops.yaml` の `R2_BUCKET` と `R2_ENDPOINT`（アカウントIDを含む）を確認 |
| `config file not found, or has no creation rules` | `.sops.yaml` がルートに無い | ルートへ置く |
| `no matching creation rules found` | `path_regex` が区切り文字に一致しない | `platform[\\/]sops[\\/]` を使う |
| `Failed to get the data key required to decrypt` | sopsが秘密鍵を見つけられない | `SOPS_AGE_KEY_FILE` を設定してシェルを開き直す |
| `Host key verification failed` | ホスト鍵が未登録 | 指紋を突き合わせてから手動SSHで登録 |
| `invalid privilege 'VM.Monitor'` | PVEの版で廃止された権限 | 棚卸しの権限一覧を見て `platform_admin_privileges` を直す |
| APIが `401` を返す | トークン文字列が二重になっている | `output -raw automation_token_value` は完全な形。接頭辞を足さない |
| 権限があるはずなのに一覧が空 | トークンの「特権の分離」が有効 | `pveum user token modify <user> <id> --privsep 0` |
| `Permission check failed (/sdn/zones/.../vmbr0, SDN.Use)` | PVE 8.2以降はbridge割り当てにSDN.Useが要る | `00-bootstrap` の `sdn_acl_path` を実機のゾーン名に合わせる |
| イメージ取得が `Permission check failed` | URLメタデータAPIは `/` の権限を要求する | 取得は `00-bootstrap`（root@pam）で行う。`terraform@pve` では実行しない |
| `terraform apply` がVM作成後に戻ってこない | cloud imageに qemu-guest-agent が無い | 別シェルで `guests.yml` を流す。エージェントが上がれば待ちが解ける |
| Ansibleが `world writable directory` と言う | リポジトリが `/mnt/c` にある | 動作には影響しない。必要なら `ANSIBLE_CONFIG` を明示 |
| `UNPROTECTED PRIVATE KEY FILE` | 鍵が `/mnt/c` にある | WSLの `~/.ssh/` へ 0600 でコピー |
