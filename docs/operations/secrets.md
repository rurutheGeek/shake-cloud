---
title: 秘密値の管理（SOPS + age）
updated: 2026-10-22
section: 運用手順
audience: 管理者
tags:
  - ops
  - secrets
---

# 秘密値の管理（SOPS + age）

> **更新日** 2026-10-22 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 運用中。age鍵は生成済み（`~/.config/sops/age/keys.txt` と外部コピー）。`platform/sops/*.sops.yaml`（Proxmox root・Proxmox/開発VM・NetBox・Cloudflare（state用）・Cloudflare DNS・smtp・k8s・s3・cloudapi・eufy-security・home-assistant・monitoring・print-api・services）と、Flux の `sops-age` Secret で実際に復号しています。

**Proxmoxのアカウントパスワードだけは Terraform では作れません**（`/access/password` がAPIトークンを受け付けずチケットを要求するため）。`tools/ensure-secrets.py` が生成し、SOPSで暗号化したまま持ちます。既存の値は再生成しないので、再実行しても誰かが締め出されることはありません（`platform/ansible/roles/pve_users`・`devbox`が呼びます）。

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

sopsが鍵を見つけられない場合は、環境変数 `SOPS_AGE_KEY_FILE` で鍵の場所を指定します。

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
- **復旧専用の鍵（2026-10-03 に追加）**: 作業用の鍵（dev-02 の `~/.config/sops/age/keys.txt`）とは別に、復旧専用の age 鍵を `.sops.yaml` の受信者へ登録してあります。秘密鍵は**ラボの外**に置きます（スマホ、紙への印刷、Vaultwarden の3か所）。Vaultwarden はラボと一緒に失われるので、単独では復旧に使えません（日常の参照用）。使うときは `SOPS_AGE_KEY_FILE=<復旧鍵のファイル> sops -d <ファイル>`。全ファイルがこの鍵だけで復号できることを追加時に確認済みです。
- 暗号化は履歴を遡って適用されません。一度平文でpushした値は、暗号化コミットを重ねても公開済みとして扱い、**該当のトークンを失効・再発行**します。
- SOPSはファイルの値を守るもので、Terraformのstateは守りません。stateには復号後の値が平文で入り得ます。stateはK11の外のS3互換ストレージに置き、バケットを公開せず、アクセスキーを対象バケットの読み書きだけに絞ります。詳細は[Terraformの実行](terraform.md)を参照してください。

<a id="where"></a>
## 7. どこに何があるか

### 入口とログイン情報

**パスワードそのものはここに書きません。** 置き場所と、取り出し方だけを書きます。

| サービス | 入口 | ログイン名 | 資格情報の置き場所 |
| --- | --- | --- | --- |
| Proxmox の画面 | `https://pve.apextox.dpdns.org:8006`（証明書は Let's Encrypt。IP `192.168.10.10:8006` でも入れるが、名前が一致しないので警告が出る） | `root`（Realm: Linux PAM） | `platform/sops/proxmox-root.sops.yaml` の `PROXMOX_VE_PASSWORD`（ACME アカウントの作成に要るので入れた） |
| Proxmox の画面（開発者） | 同上 | `dev-a@pve` / `dev-b@pve`（Realm: Proxmox VE） | `platform/sops/pve-users.sops.yaml` |
| Proxmox ホストへの SSH | `root@192.168.10.10` | 鍵のみ | **dev-02 の鍵は登録されていない**（2026-09-10 に拒否を確認）。入れる鍵は人が管理している。API なら root トークン（`proxmox-root.sops.yaml`）で届く |
| NetBox | `https://netbox.apextox.dpdns.org` | `admin` | core-01 の `/opt/netbox-stack/secrets/superuser_password` |
| NetBox API | `http://192.168.10.200:8000/api/`（ツールの接続先。`https://netbox.apextox.dpdns.org/api/` でも届く） | トークン | 書き込み: `netbox.sops.yaml`、読み取り: `netbox-inventory.sops.yaml`、クラウドAPI用: `cloudapi.sops.yaml` |
| Authentik | `https://auth.apextox.dpdns.org` | `akadmin` | core-01 の `/opt/identity-stack/secrets/bootstrap_password` |
| Homarr | `https://homarr.apextox.dpdns.org` | Authentik（`users`は閲覧、`admins`は編集） | SSO。ローカル復旧は apps-01 の `/opt/homarr/secrets/admin_password` |
| Grafana | `https://grafana.apextox.dpdns.org` | Authentik（`admins`=Admin、`users`=Viewer） | SSO。ローカル復旧は tarakoserver の `/opt/monitoring-stack/secrets/grafana_admin_password` |
| LibreSpeed | `https://speed.apextox.dpdns.org` | 不要（LAN内） | 履歴の統計ページ（`/results/stats.php`）は apps-01 の `/opt/librespeed/secrets/stats_password` |
| クラウドのポータル | `https://cloud.apextox.dpdns.org` | Authentik のアカウント（`users` か `admins`） | Authentik 側。`akadmin` は `admins` に入っている |
| クラウドAPI（Terraform・CLI・curl） | `https://cloud.apextox.dpdns.org/v1/` | アクセスキー | 利用者の分はポータルで発行（表示は一度だけ）。管理用ブートストラップキーは 2026-09-11 に無効化。緊急時は cloud-01 で `manage.py rotate-bootstrap-key` |
| 開発VM への SSH | `debian@192.168.10.202` / `.203` | パスワードまたは鍵 | `.local/devvm-passwords.yml`（**devbox の playbook を実行した作業機の手元にだけある平文**。dev-02 には無い） |
| 基盤VM への SSH（core-01、cloud-01、probe-01 など） | `debian@<IP>` | 鍵のみ | 鍵は `platform/terraform/access.yaml`。dev-02 からは `~/.ssh/id_ed25519_pve` |
| Terraform の state | Cloudflare R2 | アクセスキー | `platform/sops/s3.sops.yaml` |
| DNS（`apextox.dpdns.org`） | Cloudflare ダッシュボード（ゾーンID `112734e967c919ddd9ec1fa5c4f2a320`） | 所有者の Cloudflare アカウント | 証明書用のトークン（このゾーンの DNS 編集だけ）: `platform/sops/cloudflare-dns.sops.yaml` |
| ドキュメントサイト | `https://docs.apextox.dpdns.org` | 不要（LAN 内に公開） | 資格情報なし。原稿は Git の `docs/`、配備は `platform/ansible/docs-site.yml` |
| Home Assistant | `https://ha.apextox.dpdns.org` | Authentik（`users` / `admins`）または緊急用のローカルオーナー | HA 自身の config（`/srv/home-assistant/config`。apps-01）。**`manage.py backup` は sudo で実行**。長期アクセストークンは `platform/sops/home-assistant.sops.yaml` |
| Eufy Security（eufy-security-ws 3.1.0） | `eufy-security-ws:3000`（HA の Docker ネットワーク内だけ。LAN 非公開） | Eufy アカウント | `platform/sops/eufy-security.sops.yaml`（`EUFY_USERNAME`・`EUFY_PASSWORD`・`EUFY_COUNTRY`・`EUFY_TRUSTED_DEVICE_NAME`・`EUFY_STATION_IP_ADDRESSES`）。セッションは `/srv/eufy-security-ws/data`（apps-01）。「No houses」が出たら `manage.py reset-session` |
| SwitchBot Cloud（Hub Mini 経由） | HA の「設定 → デバイスとサービス」 | SwitchBot アカウント | トークンとシークレットは HA の config entry にだけ保存（Git・SOPS には置かない） |

VM の中にある値の取り出し方（dev-02 で実行）:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.200 sudo cat /opt/netbox-stack/secrets/superuser_password
```

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.200 sudo cat /opt/identity-stack/secrets/bootstrap_password
```

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.205 sudo cat /opt/cloud-stack/secrets/bootstrap_admin_key
```

**cloud-01 の `bootstrap_admin_key` は 2026-09-11 に無効化済みで、通常は空です**（緊急時は `manage.py rotate-bootstrap-key`。[決定ログ](../architecture/decisions.md)・[cloud.md 3-8](cloud.md)）。

SOPS の値の取り出し方:

```bash
sops --decrypt platform/sops/pve-users.sops.yaml
```

### VM の中とリポジトリの暗号化済みファイル

VM の中にある秘密値は、次の場所で自動生成されています。Git には入りません。

| 場所 | 中身 |
| --- | --- |
| core-01 `/opt/netbox-stack/secrets/` | NetBox の DB・鍵、各トークン（`inventory` / `terraform` / `cloudapi`） |
| core-01 `/opt/identity-stack/secrets/` | Authentik の DB・鍵、`akadmin` の初期パスワード、ブートストラップトークン、`oidc-cloud.json` |
| cloud-01 `/opt/cloud-stack/secrets/` | 管理DBのパスワード、`oidc_credentials`（identity の `oidc-cloud.json` の写し）。`bootstrap_admin_key` は 2026-09-11 に無効化して空 |
| apps-01 `/opt/<アプリ名>/secrets/` | Home Assistant の config、Eufy の `.env`、Vaultwarden の `secrets/admin_token`、LibreSpeed の `secrets/stats_password`、print-api のトークンなど。状態は `/srv/<アプリ名>/...` |
| tarakoserver `/opt/monitoring-stack/secrets/` | Grafana の管理者パスワード、Grafana の OIDC 秘密値（identity の `oidc-grafana.json` の写し）、NUT のパスワード、`game_metrics_token`（Prometheusだけが読む0444）など。状態は `/srv/monitoring/...` |
| **core-01 だけ**の `/opt/tls-proxy/secrets/` | Cloudflare の DNS 編集トークン（`cloudflare-dns.sops.yaml` の写し）。証明書は `/srv/tls-proxy/storage/data`。他ホストの Caddy は内部CAで、トークンを持たない（[HTTPSの入口](edge.md)） |

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
| `platform/sops/monitoring.sops.yaml` | 監視（tarakoserver）用の Proxmox 読み取りトークン（`PVE_TOKEN_VALUE`）、NUT 監視ユーザーのパスワード（`NUT_MONITOR_PASSWORD`）、ゲームポータルの指標トークン（`GAME_METRICS_TOKEN`。Prometheusの `game` ジョブだけが使う） |
| `platform/sops/k8s.sops.yaml` | database/function 用 ServiceAccount `databases/cloud-api` の接続情報（`K8S_API_URL`・`K8S_CA_BASE64`・`K8S_TOKEN`） |
| `platform/sops/print-api.sops.yaml` | Nextcloud 印刷アプリ → apps-01 `print-api` のトークン |
| `platform/sops/smtp.sops.yaml` | Gmail（`shake.notify@gmail.com`）のアプリパスワード。identity の招待・復旧メール用 |
| `platform/sops/services.sops.yaml` | サービスVM（`services/*`）のstate用 shakecloud アクセスキー（作成済み。有効性・権限は未確認） |
| `platform/sops/pve-users.sops.yaml` | 開発VM用の Proxmox ユーザー |

### 引き継ぐ人の分を作る

今は**アクセス手段が dev-02 の1か所に集まっています。** 引き継ぐときは、同じものをもう1人分作ります。どれも既存の保持者が1回操作すれば済み、秘密値そのものを受け渡す必要はありません。

| 必要なもの | 今どこにあるか | 新しい人の分を作る方法 |
| --- | --- | --- |
| SOPS の復号（age 鍵） | dev-02 の `~/.config/sops/age/keys.txt`。**復旧専用の鍵を別に登録済み（2026-10-03）。** 秘密鍵は Nextcloud（ルルザギークの `shake-cloud-recovery/recovery-key.txt`）に置いてあり、dev-02 の分は削除済み（2026-10-04）。ラボの外にも保存済み（2026-10-04、利用者が実施）（[秘密値](secrets.md)） | 新しい人が自分の age 鍵を作り、**公開鍵だけ**を渡す。保持者が `.sops.yaml` へ足し、`sops updatekeys platform/sops/*.sops.yaml` を実行する（[秘密値の管理](secrets.md)） |
| 基盤VMへの SSH | `platform/terraform/access.yaml` の公開鍵 | 公開鍵を `admin_ssh_public_keys` の**末尾に**足す（順序を変えない）。新しく作るVMにはこれで入る。既にあるVMには、入れる人が `ssh-copy-id` か Ansible で足す |
| Proxmox ホストへの SSH | 人が管理（dev-02 の鍵は未登録） | ホストの `authorized_keys` へ公開鍵を足す |
| クラウドの管理者権限 | Authentik の `admins` グループ | 新しい人の Authentik アカウントを `admins` に入れる。ブートストラップ管理キーは共有しない |
| 手元にしか無い設定 | `platform/ansible/pve.ini`、`seed.ini`、`.local/pve-readonly.env` | `.example` から作る。`pve-readonly.env` は `site.yaml` を作り直すときだけ要る |
| Go のツールチェーン | dev-02 の `~/.local/go`（apt の版は古い） | `https://go.dev/dl/` から取得して `PATH` に足す。版は `cloud/api/go.mod` に合わせる |
