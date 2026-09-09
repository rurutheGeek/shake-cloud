# 秘密値の管理（SOPS + age）

更新日: 2026-09-08。状態: **導入手順。実鍵は未生成**。

これまでの秘密値は配備先で生成し、Gitへ入れない方針でした（リポジトリのREADME「GitHubへ置くもの」）。Proxmox・NetBox・Kubernetesを足すと、**配備する前に必要な資格情報**（Proxmox APIトークン、NetBoxの書き込みトークン、SSH鍵）が増えます。これらを暗号化した状態でGitに置くためにSOPSとageを使います。

Ansible・Terraform・Fluxの3者が同じ鍵で復号できることが採用理由です。SOPSは値だけを暗号化し、キー名と構造は平文で残るため、差分レビューができます。[SOPS](https://github.com/getsops/sops)、[age](https://github.com/FiloSottile/age)

これは配備先で生成する秘密値（DBパスワード、Vaultwarden管理トークン、ローカルCAの秘密鍵）を置き換えるものではありません。それらは今までどおり配備先に留まり、Gitへは入りません。

## 1. 何ができるか

暗号化したまま `platform/sops/*.sops.yaml` をコミットでき、`sops exec-env` で復号せずに環境変数としてコマンドへ渡せます。復号した平文がディスクに残りません。

## 2. どの利用者に影響するか

管理者だけです。利用者向けサービスの使い方は変わりません。復号できるのはage秘密鍵を持つ管理者だけです。

## 3. 設定場所

| 対象 | 場所 |
| --- | --- |
| 暗号化ルール（公開鍵） | **リポジトリのルート**の `.sops.yaml`。Gitで管理する |
| 暗号化済みの値 | `platform/sops/*.sops.yaml`。Gitで管理する |
| 雛形 | `platform/sops/*.example`。Gitで管理する |
| **age秘密鍵** | `~/.config/sops/age/keys.txt`。**リポジトリの外**。Gitで管理しない |

`platform/sops/` は既定で全て除外し、上の3種だけを `.gitignore` の否定パターンで明示的に追跡しています。復号した平文をうっかり `git add` できません。

## 4. 具体的な入力例

初回だけ鍵を作り、公開鍵を `.sops.yaml` へ書きます。

```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
chmod 600 ~/.config/sops/age/keys.txt
grep 'public key' ~/.config/sops/age/keys.txt

cp .sops.yaml.example .sops.yaml
# age1... の公開鍵へ置き換える
```

**`.sops.yaml` はリポジトリのルートに置きます。** sopsはカレントディレクトリから上へ辿って設定を探すため、`platform/sops/` に置くとルートから実行したときに見つかりません。`path_regex` は絶対パスに対して評価されるので、Windowsの `\` も受けるように `platform[\\/]sops[\\/]` と書きます。

Windowsではsopsが既定で `%AppData%\sops\age\keys.txt` を見ます。上の場所に鍵を置いた場合、**暗号化はできるのに復号できない**状態になるので、`SOPS_AGE_KEY_FILE` に鍵のパスを設定してシェルを開き直します。手順は[初回セットアップの順番](bootstrap.md)にあります。

値を入れて暗号化します。**平文のままコミットしないでください。**

```bash
cp platform/sops/proxmox.sops.yaml.example platform/sops/proxmox.sops.yaml
# 実値へ編集
sops --encrypt --in-place platform/sops/proxmox.sops.yaml
```

使うときは復号せず、コマンドへ環境変数として渡します。

```bash
sops exec-env platform/sops/proxmox.sops.yaml \
  'terraform -chdir=platform/terraform/00-bootstrap plan'
```

編集は `sops platform/sops/proxmox.sops.yaml` です。エディタを閉じると再暗号化されます。

## 5. 変更後の確認方法

`git add` の後に公開チェックを実行します。暗号化し忘れた `*.sops.yaml` はここで落ちます。

```bash
git add platform/sops/proxmox.sops.yaml
.venv/bin/python tools/check-publication.py
git diff --cached platform/sops/proxmox.sops.yaml
```

差分に `ENC[AES256_GCM,data:...` が並び、実値が読めないことを目視でも確認します。キー名・コメント・構造は平文で残るのが正常です。

## 6. 元に戻す方法と注意点

- 鍵を差し替える場合は、新しい公開鍵を `.sops.yaml` へ足し、`sops updatekeys platform/sops/*.sops.yaml` を実行してから古い鍵を外します。順序を逆にすると復号できなくなります。
- **age秘密鍵を失うと、暗号化済みファイルは復元できません。** 管理PCと外部コピーの2か所で保持し、[バックアップと復旧](../architecture/operations.md)の対象へ含めます。
- 暗号化は履歴を遡って適用されません。一度平文でpushした値は、暗号化コミットを重ねても公開済みとして扱い、**該当のトークンを失効・再発行**します。
- SOPSはファイルの値を守るもので、Terraformのstateは守りません。stateには復号後の値が平文で入り得ます。stateはCloudflare R2に置き、バケットを公開せず、R2のAPIトークンを対象バケットの読み書きだけに絞ります。詳細は[Terraformの実行](terraform.md)を参照してください。
