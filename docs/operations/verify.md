---
title: 確認と、はまりどころ
updated: 2026-09-19
section: 運用手順
audience: 管理者
tags:
  - ops
  - verify
---

# 確認と、はまりどころ

> **更新日** 2026-09-19 ・ **区分** 運用手順 ・ **読む人** 管理者

変更したあとに流す検査と、実際に踏んだ落とし穴です。**確認して落ちたら、下の「はまりどころ」を先に見てください。**

クラウドAPIだけを対象にした実機プローブは[クラウドの実機プローブと切り戻し](cloud-verify.md)にあります。


## 手元で流す検査

変更したら、CI と同じ検査を手元で流します。

```bash
python3 -m unittest discover -s tests
```

```bash
terraform fmt -check -recursive platform/terraform
```

```bash
.venv/bin/yamllint -c .yamllint .
```

```bash
.venv/bin/mkdocs build --strict
```

```bash
python3 tools/check-publication.py
```

```bash
gofmt -l cloud
```

DB を使う Go のテストは、データベースを作れる PostgreSQL を `SHAKECLOUD_TEST_DATABASE_URL` で渡したときだけ走ります。渡さなければ skip されます。

```bash
cd cloud/api && go vet ./... && go test ./...
```

実機で「API から VM が1台できて、片付けまで済む」ことは次で確かめます。作成→SSH→削除まで行い、残骸があれば失敗します。

**アクセスキーはポータルで発行したものを使います**（ブートストラップ管理キーは 2026-09-11 に無効化済み。[配備台帳](handover.md) §4・§5 Phase 5）。ポータルにログイン →「アクセスキー」→ 発行し、表示された一度きりの値を環境変数に入れます。どうしても管理キーが要る場合は `manage.py rotate-bootstrap-key` で作り直します。

```bash
export SHAKECLOUD_ACCESS_KEY='sca_...'   # ポータルで発行したアクセスキー
```

```bash
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-instances.py'
```

実機がコードどおりかは、次で確かめます。どれも**差分なし・変更ゼロ・PASS・200** が正常です。

```bash
tools/tf 10-platform plan -detailed-exitcode
```

```bash
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-cloud.py'
```

ボリュームとセキュリティグループは、実際に遮断・許可されるところまで見ます（[配備台帳](handover.md) §5 Phase 4、`SHAKECLOUD_ACCESS_KEY` が要ります）:

```bash
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-volumes.py'
```

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml 'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/identity.yml'
```

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml 'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/cloud.yml'
```

ドキュメントサイトの更新（**静的インベントリで流します**。理由は下の「はまりどころ」）:

```bash
ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/seed.ini platform/ansible/docs-site.yml
```

```bash
curl https://cloud.apextox.dpdns.org/healthz
```

いまの容量と、効いている上限（アクセスキーが要ります）:

```bash
curl -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" https://cloud.apextox.dpdns.org/v1/capacity
```

```bash
curl -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" https://cloud.apextox.dpdns.org/v1/limits
```

```bash
tools/tf 20-dns plan -detailed-exitcode
```

## 10. はまりどころ

実際に起きたか、実機で確認した落とし穴です。

| 症状 | 原因と対処 |
| --- | --- |
| apply が途中で止まり、次の apply が「VMID が既にある」で失敗する | VM は作られたが state に入っていない。消さずに `terraform import` で取り込む。[Terraformの実行](terraform.md) |
| plan / apply が何分も終わらない | `qemu-guest-agent` の応答を待っている。Debian の cloud image には入っていないので入れる |
| 保存した plan が apply できない | Terraform の版が変わった。plan を作り直す |
| 別の作業機で plan すると、イメージや鍵の削除が出る | 宣言が tfvars にしか無かった。秘密でない宣言は YAML に置く |
| Ansible インベントリが空になる | ホスト名とグループ名が同じ（`identity`）。グループ名を変える（`tests/test_identity_stack.py` が検査） |
| Ansible が `Permission denied (publickey)` で止まる | NetBox の動的インベントリも `ansible.cfg` も鍵を指定しない。`ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve` を付けて流す |
| `check-publication.py` が正しいファイルを拒否する | 経路に `storage` `library` `backups` `runtime` `secrets` `trust` `.terraform` を含む。Go のパッケージ名にも効くので `internal/db` などにする。`go mod vendor` は使えない（`tests/test_cloud_stack.py` が `cloud/` を検査） |
| `access.yaml` を並べ替えただけで全VMに差分が出る | Proxmox は鍵を連結した1つの文字列として持つ。順序を変えない |
| Authentik の設定が毎回「変更あり」になる | API が返す余分なフィールド（`redirect_uri_type`）を宣言側にも書く |
| PostgreSQL 18 が `mkdir: can't create directory '/var/lib/postgresql/18/'` で再起動を繰り返す | 18 以降は postgres ユーザーになってからデータディレクトリを作る。マウント元が root 所有だと入れない。マウント元を uid 70 にする（`cloud/manage.py init` が行う） |
| アクセスキーで `POST /v1/access-keys` が 403 | 仕様。発行はポータルのログインからだけ |
| ブートストラップ管理キーがファイルにあるのに 401 | API から削除したキーは、再起動しても復活しない。`manage.py rotate-bootstrap-key` で新しくする |
| ログインが「別のアカウントに登録されています」で拒否される | Authentik のユーザーを作り直して `sub` が変わった。監査ログの `AccountConflict` の `subject` を見て、管理DBの `accounts.subject` を新しい値へ直す |
| リコンサイラが全インスタンスを「消えた」と判断しうる | Proxmox は ACL の外に 403、存在しない VM に 500 を返す。**403 を見たら、その周回を丸ごと中止する** |
| セキュリティグループのルールが効かない | VM のファイアウォール有効化、NIC の `firewall=1`、ルール本体の3つが全部要る |
| VM は起動したがネットワークが無い | IP は seed ISO の `network-config` に書く。ラベルは `CIDATA` |
| 実機プローブが全部通るのに本番で 403 | `root@pam` で試した。絞ったトークン（`cloudapi@pve`）で走らせる。スクリプトは `root@pam` を拒否する |
| DNS レコードを作った直後に「名前が無い」と返る | Cloudflare の中で反映が終わる前に問い合わせた。権威サーバー `daisy.ns.cloudflare.com` に直接聞けば、作った時点で答えている。**その「無い」という答えは、各ホストの systemd-resolved に最大30分残る**（ルーターが直っても、そのホストだけ引けない）。`sudo resolvectl flush-caches` で消すか、30分待つ。作った直後にホストから名前を引かないのが一番よい |
| Caddy が証明書を取れない（権限エラー、`Invalid request headers`） | トークンに「ゾーンの読み取り」と「DNS の編集」の両方が要る。テンプレート「ゾーン DNS を編集する」なら両方付く |
| 監査ログの送信元が全部 172.x になる | Caddy の後ろに置いたのに `SHAKECLOUD_TRUSTED_PROXIES` が無い。逆に広げすぎると、直接つないだ人が送信元を偽れる |
| Ansible が置いたファイルの末尾に `\n` という2文字が残る | YAML の**単一引用符の中では `\n` が改行にならない**。`site.json` の末尾に付いて API が「JSON の後ろにごみがある」で起動できなかった。二重引用符にする（`tests/test_cloud_stack.py` が5つのロールをまとめて検査する） |
| 配備が「HTTPS の確認」で止まり、原因を直すタスクまで進まない | `tls_proxy` は各サービスのロールより**前**に走る。中身が落ちていると Caddy が 502 を返し、この待ちが失敗して配備が終わる。502・503 も合格にした。ここで見るのは証明書だけで、中身の健全性は各ロールの `/healthz` が見る |
| `sops exec-env` の中で `ansible-playbook: not found` | **`sops exec-env` は `/bin/sh` で実行するので、venv は PATH に入っていない。**ansible は `.venv/bin/` にしか無い（`command -v ansible-playbook` は何も返さない）。コマンド全体を単一引用符で囲んでいるため、外側のシェルの PATH も効かない。`.venv/bin/ansible-playbook` と書く |
| 失敗した配備が成功したように見える | `... \| tail -30` のようにパイプへ繋ぐと、終了コードはパイプの**最後**のコマンドのものになる。`ansible-playbook` が起動すらしていなくても `tail` が 0 を返すので 0 になる。`${PIPESTATUS[0]}` を見るか、パイプを外す |
| ドキュメントサイトの配備が「何もせずに」終わる | `docs-site.yml` は `hosts: netbox_bootstrap` で、このグループは**静的な `platform/ansible/seed.ini` にしか無い**（services-01 は `05-seed` の管轄で NetBox にVM記録が無いため、動的インベントリに入っていない）。動的インベントリで流すと `skipping: no hosts matched` になり、**そのとき ansible の終了コードは 0** なので成功に見える。`-i platform/ansible/seed.ini` で流し、`PLAY RECAP` に `services-01` が出ることを確かめる |
| セキュリティグループのルールが正しいのに通信が遮断されない | **Proxmox は VM の `firewall/options` を書かないと、実行中VMの live ruleset を再構築しない。**最初のSG適用で `enable=1`・`policy_in=DROP` になった後は、ルールだけ変えても options の値は変わらないため、`setFilteredOptions` が PUT を省くと**ホスト側は前の（緩い）ルールのまま**になる。API の `firewall_state` は `in-sync`、`firewall/rules` も新ルールなのに、許可していないポートが開いたままになる（2026-09-11 実測）。修正: options を**毎回書く**（`compute/firewall.go` の `setFilteredOptions`）。`TestARuleOnlyChangeRewritesTheOptionsSoProxmoxReloads` が回帰を防ぐ。実機は `tools/verify-volumes.py` が実際の遮断まで見る |
| 複数の `shakecloud_security_group_rule` が同じルールIDを state に持つ | **Provider の Create が並列に走ると、どれも同じ `before`（空）を読み、API はグループ全体を返すため、`findNewRule` が最初の新ルールを全部へ選んでいた**（2026-09-12、media-01 の apply で3ルールが同じ `sgr-...` になった）。属性（protocol・CIDR・ポート・説明）が一致するものを選ぶよう修正。重複した state は `terraform state rm` → `terraform import GROUP/RULE` で直し、再 plan を No changes にする。`cloud/provider/internal/provider/security_group_rule_test.go` が回帰を防ぐ |
| クラウドVMが突然、SSHもHTTPも応答しない（ARPは解決する） | **クラウドのIPレンジ `.100-.180` がルーターのDHCP配布範囲と重なっている。**2026-09-12、Amazon端末がDHCPで `192.168.10.101` を取得し、本来の持ち主である media-01 がLANから見えなくなった（`ip neigh` に別MAC・ベンダーはAmazon Technologies）。cloud-01 から静的ARP（`ip neigh replace 192.168.10.101 lladdr <VMのMAC> nud permanent`）を入れるとVMは正常だった。ルーターで `.100-.180` をDHCPから除外するか、クラウドのレンジを移す。**VMを増やす前に解消する。**応急処置はVM再起動（gratuitous ARP）だが再発する。**2026-09-14: 解消済み（ユーザー確認。net-01 作成前にルーター側で対応）** |
| クラウドVMの `docker pull` が `dial tcp [2600:...]:443: i/o timeout` で失敗する | **ルータがIPv6のdefault routeをRAで配るのに、インターネットへのIPv6が通っていない。**DockerはAAAAを先に引いてタイムアウトする（2026-09-12、media-01のtls-proxyビルドで実測）。`platform/ansible/media-base.yml` が `/etc/sysctl.d/99-media-no-ipv6.conf` でIPv6を無効にし、getaddrinfoとDockerをIPv4へ揃える。ルータのIPv6が直ったら外す |
| Forward Authがアプリを素通しする（ログイン画面が出ない・404や空の200） | **Authentik 2026.8のoutpostはリクエストの `Host` でアプリを選ぶ。**Caddyの既定は中継先のHostに書き換えるため、`forward_auth` に `header_up Host {http.request.host}` を付ける。さらにidentityのCaddyは未知のHostに空の200を返すので、identityだけ `tls_proxy_catchall_upstream: 127.0.0.1:9000` のcatch-allを置き、AuthentikへHostごと渡す（2026-09-12実測。埋め込みoutpostを使い、別コンテナは要らない） |
| `ballooning = false` で `memory_min_mib` を明示すると `terraform apply` が失敗する | **Provider と API の不一致。** API は ballooning オフのとき `memory_min_mib` を 0 で返すのに、Provider は設定値（例: 512）をそのまま期待するため `Provider produced inconsistent result after apply` になる（2026-09-14、net-01 の作成で実測）。`memory_min_mib` は ballooning がオンのときだけ送る（`platform/terraform/services/net/main.tf`）。Provider 側は ballooning オフ＋明示値を plan 時にエラーにするのが修正候補 |
