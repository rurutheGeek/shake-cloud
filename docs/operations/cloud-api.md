---
title: クラウドAPI本体とインスタンス
updated: 2026-09-19
section: 運用手順
audience: 管理者
tags:
  - ops
  - cloud
---

# クラウドAPI本体とインスタンス

> **更新日** 2026-09-19 ・ **区分** 運用手順 ・ **読む人** 管理者

[クラウドAPIの構築](cloud.md)の続きです。**3-1〜3-7 の土台が終わっていることが前提**で、ここでは API 本体を上げ、名前と HTTPS を付け、インスタンスを作れるところまで進めます。

続きは[ボリューム・S3・DB・関数](cloud-resources.md)、検査は[実機プローブと切り戻し](cloud-verify.md)です。


### 3-8. クラウドAPI（Phase 1）

cloud-01 に API と管理DB（PostgreSQL）を置きます。OIDC クライアントの秘密値を identity VM から読むので、`identity.yml` の後に流します。

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/cloud.yml'
```

API のイメージは cloud-01 の上で `cloud/api/` からビルドします。ベースイメージは `cloud/api/Dockerfile`、PostgreSQL は `cloud/compose.lock.yaml` で digest を固定しています。

| 入口 | 中身 |
| --- | --- |
| `https://cloud.apextox.dpdns.org/` | セルフサービスポータル。Authentik でログインし、VM・ボリューム・SG・イメージ・SSH鍵・S3バケット・database・function・容量・上限・操作履歴を扱える（Phase 5 で完成） |
| `https://cloud.apextox.dpdns.org/v1/…` | JSON API。正本は `cloud/openapi/shakecloud.yaml`。Go のルート表と食い違うとテストが落ちる |
| `https://cloud.apextox.dpdns.org/healthz` | 管理DBに届くか。**Authentik は見ない**（Authentik が止まっていても API は正常） |

秘密値はすべて cloud-01 上で自動生成し、再実行しても作り直しません。Git には入りません。

| 場所 | 中身 |
| --- | --- |
| `/opt/cloud-stack/secrets/db_password` | 管理DBのパスワード |
| `/opt/cloud-stack/secrets/bootstrap_admin_key` | ブートストラップ管理キー（下記） |
| `/opt/cloud-stack/secrets/oidc_credentials` | identity VM の `/opt/identity-stack/secrets/oidc-cloud.json` の写し |
| `/srv/cloud-stack/storage/postgres` | 管理DB |

**OIDC クライアントの秘密値は SOPS に入れていません。** 以前は `cloudapi.sops.yaml` へ入れる予定でしたが、正本は identity VM にあり、2か所に持つと Authentik 側で作り直したときに食い違います。配備のたびに Ansible が identity VM から直接写し、ログには出しません（`tests/test_cloud_stack.py` が `no_log` を検査）。

#### 実機での確認（2026-09-10）

| 確認 | 結果 |
| --- | --- |
| `cloud.yml` の初回 | 失敗。PostgreSQL 18 がマウント先に入れなかった（下記）。直して再配備し成功 |
| `cloud.yml` の再実行 | `changed=0` |
| コンテナ | `api`・`postgres` とも healthy。メモリは API 7MiB、PostgreSQL 65MiB、VM 全体で約500MiB / 2GiB |
| `/healthz` | 200 |
| `/auth/login` | Authentik の authorize へ 302。`redirect_uri` は現在 `https://cloud.apextox.dpdns.org/auth/callback`、PKCE は S256（当時は IP 直だった） |
| ブートストラップ管理キーで `GET /v1/caller-identity` | 200、`bootstrap-admin`（管理者） |
| アクセスキーで `POST /v1/access-keys` | 403 `UnauthorizedOperation` |
| 秘密値だけ違うキー | 401。監査ログに `AuthFailure`（`secret_mismatch`） |
| 資格情報なし／クロスサイトの POST | 401／403 `CrossOriginRequestBlocked` |
| ブラウザで Authentik にログインする | 2026-09-10 に `akadmin` で確認済み。監査ログに `CompleteLogin`（アカウント作成、管理者）が残った（[配備台帳](handover.md) Phase 1） |

初回の失敗: PostgreSQL 18 のイメージは、postgres ユーザー（uid 70）になってから `<マウント先>/18/docker` を作ります。マウント元が root 所有の 0700 だと入れず、`mkdir: can't create directory '/var/lib/postgresql/18/'` で再起動を繰り返しました。`manage.py init` がマウント元を uid 70 にするよう直しました。

#### アクセスキー

- ポータルで発行し、`Authorization: Bearer sca_<キーID>.<秘密値>` で送ります。秘密値は発行時に一度だけ表示し、DB にはハッシュだけを置きます。
- **アクセスキーでアクセスキーは作れません。** 発行はポータルのログインからだけです。漏れたキーが自分の複製を作って居座れないようにするためです。一覧と削除はキーからもできます。
- 1アカウント5本まで。期限は任意（30日・90日・1年・無期限）です。
- 削除したキーは行を残して無効にします。監査ログがキーIDを指したままにするためです。
- 他人のキーを削除しようとすると「存在しない」と同じ 404 を返します。admins は誰のキーでも削除できます。

#### ブートストラップ管理キー（2026-09-11 に無効化済み）

ポータルでログインしなくても、Authentik が止まっていても、管理者が API を叩けるキーです。持ち主は `bootstrap-admin` という専用アカウントで、admins と同じく全体が見えます。

**セルフサービスが実利用できるようになったので、2026-09-11 に無効化しました**（ファイルは空、DBのキーは失効）。以後の機械アクセスは、ポータルにログインして発行するアクセスキーを使ってください。`akadmin` は `admins` に入っているので、`https://cloud.apextox.dpdns.org` からログインしてキーを発行できます。

再び管理用キーが要る場合（ポータルに入れない等の緊急時）:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.205
sudo sh -c 'cd /opt/cloud-stack && python3 manage.py rotate-bootstrap-key'
```

取り出し方（無効化前・再有効化後のみ。通常は空）:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.205 sudo cat /opt/cloud-stack/secrets/bootstrap_admin_key
```

使い方:

```bash
curl -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" https://cloud.apextox.dpdns.org/v1/caller-identity
```

**ファイルが正本です。** API は起動時に DB をファイルへ合わせます。

| やりたいこと | cloud-01 の `/opt/cloud-stack` で実行 |
| --- | --- |
| 取り替える（古いキーは失効） | `sudo sh -c 'cd /opt/cloud-stack && python3 manage.py rotate-bootstrap-key'` |
| 無効にする | `sudo sh -c 'cd /opt/cloud-stack && python3 manage.py disable-bootstrap-key'` |

ただし、**API から削除したキーはファイルに残っていても復活しません**。緊急の失効を再起動で取り消さないためです。使い直すときは `rotate-bootstrap-key` で新しいキーにします。

#### 監査ログ

- 記録するもの: すべての変更、ログイン（拒否も含む）、**実在する**キーIDでの認証失敗。存在しないキーIDでの失敗はアプリのログだけに出します。誰でも作れる値で DB を埋めさせないためです。
- `event_name` は OpenAPI の operationId です。項目名は CloudTrail の LookupEvents に揃えています。
- テーブルは追記専用です。UPDATE・DELETE・TRUNCATE はトリガーが拒否します。
- `GET /v1/audit-events` で読めます。利用者は自分のアカウントの分だけ、admins は全体です。

#### ログインの扱い

- Authentik 側で `users` / `admins` 以外は弾いていますが、API でも `groups` を確認します。Authentik の設定を誤って外しても、全員に開かないようにするためです。
- 管理者かどうかはログインのたびに `groups` から読み直します。`admins` から外した人は、次のログインで一般利用者になります。
- **知らない `sub` が既存アカウントのメールアドレスで来たら、ログインを拒否します。** Authentik のユーザーを作り直したときに起きます。別アカウントを黙って作ると、その人のリソースが2つに分かれるためです。起きたら監査ログに `AccountConflict` が残るので、管理DBの `accounts.subject` を新しい値へ直します。

#### 開発とテスト

```bash
cd cloud/api && go test ./...
```

DB を使うテストは `SHAKECLOUD_TEST_DATABASE_URL`（データベースを作れるユーザー）を設定したときだけ走り、テストごとに DB を作って消します。CI は PostgreSQL のサービスコンテナで走らせます。ログインのテストは偽の OIDC プロバイダを立て、state・nonce・PKCE の検査まで本物のコードを通します。

### 3-9. 名前と HTTPS

LAN の中の管理画面に `*.apextox.dpdns.org` の名前を付け、Let's Encrypt の証明書で HTTPS にしています。**インターネットには公開していません。** 決めた理由は[ネットワーク・公開範囲・SSO](../architecture/network-auth.md)の「DNSとHTTPS」にあります。

仕組みは3段です。どれも `platform/terraform/dns.yaml` が正本です。

| 段 | 担当 | すること |
| --- | --- | --- |
| 1. 名前 | Terraform `20-dns` | Cloudflare に A レコードを書く。アドレスは 10-platform・05-seed の出力から引き、書き写さない |
| 2. 証明書と入口 | Ansible ロール `tls_proxy`（`stacks/tls-proxy/`） | 各ホストに Caddy を置き、DNS-01 で証明書を取り、127.0.0.1 のサービスへ中継する |
| 3. サービス側 | 各ロール | Authentik と API は 127.0.0.1 に閉じ、URL を HTTPS の名前にする。NetBox は名前を許可に足す |

名前を足すときは、`dns.yaml` にレコードを足してから次を流します。

```bash
tools/tf 20-dns apply
```

そのあと、そのホストの playbook を流すと Caddy が名前を受けるようになります。identity は `identity.yml`、cloud-01 は `cloud.yml`、services-01 は `netbox.yml`・`docs-site.yml`・`home-assistant.yml`・`vaultwarden.yml`・`cups.yml` など、media-01 は `media.yml` です。**services-01 のものは静的インベントリ `platform/ansible/seed.ini` で流します**（NetBox の動的インベントリに services-01 は居ません。動的インベントリで流すと何もせずに成功したように終わります）。

Caddy が使う Cloudflare のトークンは `platform/sops/cloudflare-dns.sops.yaml` にあり、**ゾーンの読み取りと DNS の編集**の2つの権限が要ります。テンプレート「ゾーン DNS を編集する」で作れば、両方が付きます。

証明書は Caddy が期限の約30日前に自動で更新します。証明書は各ホストの `/srv/tls-proxy/storage/data` にあり、ここを消すと取り直しになります。Let's Encrypt には1ドメインあたり週50枚の上限があるので、何度も消さないでください。

クラウドAPI は Caddy の後ろにいるので、監査ログの送信元は Caddy が付ける `X-Forwarded-For` から取ります。**信用するのは同じホストの Caddy から来たときだけ**です（`SHAKECLOUD_TRUSTED_PROXIES`）。直接つないで偽の値を送っても、ログには記録されません。

#### 実機での確認（2026-09-10）

| 確認 | 結果 |
| --- | --- |
| 証明書 | `auth`・`cloud`・`netbox`・`docs` とも Let's Encrypt。警告は出ない |
| `http://` で開く | `https://` へ転送（308） |
| Authentik の issuer | `https://auth.apextox.dpdns.org/application/o/cloud/` |
| ポータルからのログイン開始 | 戻り先 `https://cloud.apextox.dpdns.org/auth/callback` を Authentik が受け付け、ログイン画面へ進んだ |
| セッション Cookie | `Secure` が付いた |
| LAN から Authentik の `:9000`・`:9443`、API の `:8080` | 閉じている |
| HTTPS 越しの NetBox のログイン | CSRF 検査を通る。誤った資格情報で試し、403 ではなく「パスワードが違う」が返った |
| 監査ログの送信元 | Caddy ではなく実際の端末（192.168.10.203）。わざと送った偽の `X-Forwarded-For` は無視された |

#### 実際に起きたこと

| 症状 | 原因と対処 |
| --- | --- |
| レコードを作った直後に、ルーターや 1.1.1.1 が「名前が無い」と返す（Google は SERVFAIL） | Cloudflare の中で反映が終わる前に問い合わせた。1分ほどで全部引けるようになった。権威サーバー（`daisy.ns.cloudflare.com`）に直接聞くと、作った時点で答えている |
| ルーターは答えるのに、あるホストだけ名前を引けない（`docs.apextox.dpdns.org` で起きた） | そのホストの systemd-resolved が、反映前の「名前が無い」を最大30分覚えていた。`sudo resolvectl flush-caches` で直った。`tls_proxy` の HTTPS 確認がこれで失敗することがある |
| Tailscale の DNS（100.100.100.100）がどの名前にも SERVFAIL を返す | Tailscale 側の DNS 設定の問題で、この名前に限らない。LAN の中では使わないので影響しない。外出先から使うときの課題（サブネットルートも未設定） |

### 3-10. インスタンス（Phase 2）

**API から VM が作れます。** 2026-09-10 に実機で、作成 → SSH でログイン → 削除 → 残骸なしまで確認しました。

| 操作 | 呼び方 |
| --- | --- |
| 共有イメージの一覧 | `GET /v1/images` |
| 雛形の一覧 | `GET /v1/instance-types`（`flavors.yaml` と同じ名前）。**選ばなくてもよい** |
| 作成 | `POST /v1/instances`（`image_id` と、`vcpus`＋`memory_mib`。任意で `memory_min_mib`・`ballooning`・`root_disk_gib`・`user_data`・`client_token`・`tags`。`instance_type` を使えば値が埋まる） |
| 一覧・1台 | `GET /v1/instances`、`GET /v1/instances/{id}`。**一覧はクラウドの全VM**（所有者名・イメージ名つき） |
| 大きさの変更 | `PATCH /v1/instances/{id}`（`admins` だけ） |
| 電源 | `POST /v1/instances/{id}/start`・`/stop`・`/reboot` |
| 削除 | `DELETE /v1/instances/{id}` |

**大きさは自由に決められます。**決まったサイズの一覧から選ぶ必要はありません。

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"image_id":"img-debian13","vcpus":6,"memory_mib":20480,"ballooning":false,"root_disk_gib":120,"tags":{"Name":"game"}}' \
  https://cloud.apextox.dpdns.org/v1/instances
```

- `instance_type` は**任意の近道**です。指定すると `flavors.yaml` の値が入り、そこから好きな項目だけ上書きできます。1つでも上書きするとその型名は外れます（一覧では「カスタム」）。
- `ballooning: false` は**固定メモリ**です（Proxmox の `balloon=0`）。ゲームVMのように実際に使い切る相手には、返ってこないメモリを空きに数えないぶん、こちらが正直です。
- `ballooning: true`（既定）のとき `memory_min_mib` が回収の下限で、省略すると**上限の 1/4**（最低 512MiB）になります。
- vCPU はノードのスレッド数（16）を超えられません。メモリとディスクは上限（`/v1/limits`）と実際の空きが決めます。

**管理者は後から変えられます。**vCPU・メモリ・バルーニングは停止中だけ、ディスクは稼働中でも拡大のみです。

```bash
curl -X PATCH -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"vcpus":8,"memory_mib":16384,"ballooning":true}' \
  https://cloud.apextox.dpdns.org/v1/instances/i-0123456789abcdef0
```

**ディスクは縮められません。**縮小はゲストのファイルシステムに知らせずに末尾を捨てる操作なので、断ります。

#### 実機での確認（2026-09-11）

| 確認 | 結果 |
| --- | --- |
| 型名なしで作成（2vCPU・3072MiB・バルーニングなし） | そのまま通った。`instance_type` は付かず、`memory_min_mib` は 0 |
| Proxmox の実物 | `cores=2`、`memory=3072`、**`balloon=0`**（バルーニング無効） |
| 一覧 | クラウドの全VMが出て、**所有者名とイメージ名**が付く |
| 稼働中に `memory_mib` を変更 | **409**（次回起動までは反映されないので断る） |
| 稼働中にディスクを 25GiB へ | 200。実物が `size=25G` になった |
| ディスクを 10GiB へ縮小 | **400**（拒否） |
| 停止後に 4vCPU・6144MiB・バルーニング有効へ | 200。床は上限の 1/4 の **1536MiB** に再計算 |
| Proxmox の実物 | `cores=4`、`memory=6144`、`balloon=1536` |
| 削除 | `terminated`、VM の残骸なし |
| 監査ログ | `ModifyInstance` が成功・`IncorrectInstanceState`・`InvalidParameterValue` の3通りとも残った |

作成の例（アクセスキーは Terraform・CLI と同じもの）:

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"image_id":"img-debian13","instance_type":"small","root_disk_gib":20,"tags":{"Name":"web"}}' \
  https://cloud.apextox.dpdns.org/v1/instances
```

**返事は即座に返り、状態は `pending` です。** 作成は裏で進むので、`GET /v1/instances/{id}` が `running` になるのを待ちます。失敗したときは `terminated` になり、`state_reason` に理由が入ります。

裏で進む順番は次のとおりで、**途中で落ちても同じところから再開します**（できたものを記録してから次へ進むため）。

1. NetBox の IP Range から住所を採番する（`description` は instance ID）
2. seed ISO を作って `cloud-images` へ上げる
3. VM を作る（イメージからディスクを作り、seed ISO を CD-ROM で付ける）
4. ディスクを指定の大きさへ広げる
5. 起動する

削除は逆順で、VM・ディスク・seed ISO・NetBox の IP をすべて解放してから `terminated` になります。**作成に失敗した場合も同じ経路で片付きます。**

上限の既定値は `platform/terraform/cloud.yaml`、**変更は管理者が画面から**行います。既定は1アカウント 8台・32vCPU・32GiB・ルートディスク計 1000GiB、クラウド全体のメモリ枠 32GiB、ノードに 4GiB 残す、ディスク実使用率 85% です。**停止中のインスタンスも数えます**（起動すれば同じだけ使うため）。詳しくは [3-11](#3-11) を参照してください。

#### 安全のための決めごと

- **他人の VM には触りません。** 作った VM の description に instance ID を書き、それが無い VMID は隔離して二度と払い出しません（手で作った VM が同じ番号に居た場合を実機で確認済み）。
- **差分リコンサイラは何も消しません。** ゲスト側の shutdown や GUI での操作には追従しますが、「VM が見えない」ときは記録だけです。ACL の事故でも同じ見え方になるためで、全台が同時に見えないときは何もしません。
- **監査ログに残ります。** 作成・削除・電源操作は、誰がどのキーで行ったかが `GET /v1/audit-events` に出ます。

#### 実機での確認（2026-09-10）

| 確認 | 結果 |
| --- | --- |
| `POST /v1/instances` | 202、`pending`。数十秒で `running` |
| NetBox | `192.168.10.100/24` を採番、DNS 名は Name タグから、`description` は instance ID |
| Proxmox の VM | VMID 5000、10GiB のディスク、seed ISO の CD-ROM、指定した MAC、バルーニング 2048/512、タグ `shakecloud`。**VM 名は Name タグ**（無ければ instance ID。人が Proxmox 画面で読めるようにするため） |
| **seed ISO が効いたか** | **SSH でログインできた。**ホスト名・IP・既定経路が指定どおりで、`cloud-init status` は `done` |
| `DELETE /v1/instances/{id}` | 202、`shutting-down` → `terminated` |
| 後片付け | VM・ディスク・seed ISO・NetBox の IP すべて残骸なし |

この一連は `tools/verify-instances.py` として残してあるので、いつでも同じ確認ができます（残骸があれば失敗します）。

<a id="3-11"></a>
### 3-11. 容量の確認と、上限の変更

**上限は管理者が実行中に変えられます。**ポータルの「上限」か `PUT /v1/limits` です。`cloud.yaml` は**既定値**で、管理者が変えた項目だけが管理DBに入ります（同じ事実を2か所に持たないため）。空欄にすれば既定値へ戻ります。

| 操作 | 呼び方 |
| --- | --- |
| いまの容量（CPU・メモリ・ストレージ・配った合計） | `GET /v1/capacity`、ポータルの「容量」 |
| 上限を読む（実効値・既定値・管理者が変えた分） | `GET /v1/limits` |
| 上限を変える（`admins` だけ） | `PUT /v1/limits` |

```bash
curl -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" https://cloud.apextox.dpdns.org/v1/capacity
```

`PUT` は**全体を置き換えます。**送らなかった項目は既定値へ戻るので、「昔いじった上限が残っていた」が起きません。`{}` を送れば全部が既定値へ戻ります。

```bash
curl -X PUT -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"account_quota":{"memory_mib":0},"capacity":{"memory_budget_mib":49152}}' \
  https://cloud.apextox.dpdns.org/v1/limits
```

**0 は無制限です。**台数・vCPU・メモリ・ディスク合計と、クラウド全体のメモリ枠に使えます。

#### 何がホストを守っているか

無制限にできるのは**方針の枠**だけで、実際の容量を見る検査は残ります。ここを理解しないまま 0 にするとホストごと倒せます。

| 検査 | 既定 | 0 にすると |
| --- | --- | --- |
| `node_memory_reserve_mib` | 4GiB | ノードに何も残さない。**ただし「要求ぶんが実際に空いている」検査は消えません** |
| `vm_disk_max_used_percent` | 85% | ディスクの使用率を見なくなる。シンプロビジョニングなので、ゲストからは空いて見えたまま書き込みが失敗します |
| `memory_budget_mib` | 32GiB | クラウドが配る上限の合計に制限が無くなる（物理は上の2つが見る） |

#### 16GiB のVMを作る

`2xlarge`（8vCPU・16GiB、バルーニングの下限 4GiB）を追加しました。既定の上限のままで作れます。

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' \
  -d '{"image_id":"img-debian13","instance_type":"2xlarge","root_disk_gib":100,"tags":{"Name":"game"}}' \
  https://cloud.apextox.dpdns.org/v1/instances
```

**上限の合計と実際の空きは一致しません。**バルーニングを前提にしているので、上限の合計は物理メモリを超えられます。超えたぶんは「ゲストが使っていなければ返る」という前提に乗っているだけで、ゲームVMのように実際に使う相手からは返りません。「容量」の画面が**両方**を並べて出すのはそのためです。考え方は[配備台帳の実測](../architecture/operations.md#measured-budget)にあります。

#### 実機での確認（2026-09-10）

| 確認 | 結果 |
| --- | --- |
| `GET /v1/capacity` | ホスト 61095 MiB・8コア/16スレッド・ストレージ2つを返した。管理者にはアカウント別も付く |
| 上限の初期状態 | 実効値＝既定値、上書きは空（`{}`） |
| `PUT /v1/limits`（台数だけ 3 に） | 実効値が 3 になり、**保存されたのは `account_quota.instances` だけ**。他の項目は既定値のまま。変更者と時刻が記録された |
| `PUT /v1/limits {}` | すべて既定値へ戻り、上書きが消えた |
| `GET /v1/instance-types` | `2xlarge` = 8vCPU・16384 MiB・下限 4096 MiB |
| **16GiB の作成** | `pending` → `running`。NetBox が `192.168.10.100/24` を採番 |
| Proxmox の VM | VMID 5000、`memory=16384`、**`balloon=4096`**、`cores=8` |
| 「容量」の集計 | 配ったメモリが 16384 MiB に増えた |
| 削除 | `terminated`。VM の残骸なし |
| 監査ログ | `UpdateLimits`・`RunInstances`・`TerminateInstance` が残った |

<a id="3-12"></a>
### 3-12. イメージのアップロードと SSH鍵

| 操作 | 呼び方 |
| --- | --- |
| イメージの一覧（共有＋全員のアップロード） | `GET /v1/images` |
| アップロード | `POST /v1/images`（`multipart/form-data`、`name` と `file`） |
| 削除 | `DELETE /v1/images/{image_id}` |
| SSH鍵の登録・一覧・削除 | `POST`/`GET`/`DELETE /v1/key-pairs` |
| 作成時に鍵を入れる | `POST /v1/instances` の `key_name` |

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -F 'name=ubuntu 24.04' -F 'file=@noble.qcow2' https://cloud.apextox.dpdns.org/v1/images
```

**`name` を `file` より先に送ってください。**素通しで流すので、ファイルの名前をファイルより後には受け取れません。

#### なぜ直接アップロードなのか（実測）

設計当初は「URL を渡して Proxmox に取りに行かせる」（`download-url`）方が軽いと見えましたが、**`cloudapi@pve` では 403** でした。絞ったトークンには許されていません。一方 `upload` は `content=import` を受け付けます（どちらも 2026-09-11 に実測）。したがって **API を通した直接アップロードが唯一の道**です。

そのうえで3つの制約が実装を決めました。**最初に書いた「素通しで流す」設計は実機で成立しませんでした。**

- **Proxmox はチャンク転送を 501 で拒否します**（`chunked transfer encoding not supported`、2026-09-11 実測）。つまり**本文の長さを先に宣言しなければ受け取ってもらえません**。長さは本文の終わりまで分からないので、「一切溜めずに流す」ことは**できません**。
- したがって cloud-01 の**実ディスク**（`/srv/cloud-stack/storage/uploads`、コンテナ内は `/var/lib/shakecloud/uploads`）へ一旦書き出し、大きさを確定させてから Proxmox へ流します。**`/tmp` は RAM（tmpfs）なので使えません**（cloud-01 の RAM は 2GiB、ディスクの空きは約31GiB）。multipart の枠は自前で組み立てて長さを正確に計算し、**中身はストリームで送ります**（枠だけがメモリに載ります）。
- **サーバの読み取り期限は 30秒**です。アップロードのときだけ**この1リクエストの期限を外します**（他のリクエストは今までどおり守られます）。なお `statusRecorder` に `Unwrap()` が無いと期限を外せません（`feature not supported` になる）。

**上限の既定を 12GiB にしてあるのはこのためです。**置き場（Proxmox のルートFS）と cloud-01 のディスクの**両方**に同じ大きさが必要で、cloud-01 の空きは約31GiB しかありません。

**中身の検査は Proxmox が qemu-img で行います。**壊れたファイルや対応外の形式はタスクが失敗し、**何も残りません**（実測で確認）。大きさは `max_image_gib`（既定 12GiB、管理者が変更可、0 は無制限）と、置き場に残す空き（`image_store_min_free_mib`）で決まります。置き場は Proxmox のルートFS（約94GiB）で、ISO やバックアップと同じ領域を分け合います。

**共有イメージは API から消せません。**Terraform の宣言物なので、消すならコードを直します。利用者のイメージは所有者と管理者が消せます。**そのイメージから既に作った VM は無関係です**（作成時にディスクへ複製済み）。ただし**作成中の VM がある間は**断ります。

#### SSH鍵

**公開鍵だけを保存します。**秘密鍵を貼った場合はそう指摘して弾きます。フィンガープリントは `ssh-keygen -lf` と同じ `SHA256:…` 形式なので、手元の鍵と見比べられます。

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" -H 'Content-Type: application/json' -d "{\"key_name\":\"laptop\",\"public_key\":\"$(cat ~/.ssh/id_ed25519.pub)\"}" https://cloud.apextox.dpdns.org/v1/key-pairs
```

**鍵は `user-data` ではなく `meta-data` の `public-keys` で渡します。**`user-data` は自由書式で、シェルスクリプトを書く人もいます。そこへ鍵を混ぜ込むのは他人の文書を書き換える操作なので、cloud-init 自身が持つ経路を使います。

**鍵の本文は作成を受け付けた時点でインスタンスへ複製します。**直後に鍵ペアを消されても、入れない VM は生まれません。逆に後から鍵ペアを消しても**既存の VM は動き続けます**（鍵はその VM の seed イメージの中にあります）。

#### 実機での確認（2026-09-11）

`qemu-img` で作った本物の qcow2（196,616 バイト）を使いました。

| 確認 | 結果 |
| --- | --- |
| アップロード | 201。`cloud-images:import/img-….qcow2` として実在し、形式は store が返した `qcow2` |
| 一覧 | 共有イメージは `public` のまま、アップロード分は所有者名つきで並ぶ |
| ディスクイメージでないファイル | **400** |
| ファイルを付けない要求 | **400** |
| 共有イメージの削除 | **409**（Terraform の宣言物なので API からは消せない） |
| 鍵の登録 | 201。フィンガープリントが **`ssh-keygen -lf` と完全一致** |
| 同じ名前で2回 | **409** |
| 秘密鍵を貼る | **400** |
| `key_name` を付けて作成 → SSH | **ログインできた。**`user_data` は一切送っていないので、`meta-data` の `public-keys` が効いた証拠 |
| 鍵ペアを消してから再ログイン | **入れた**（鍵は seed イメージの中にある） |
| イメージの削除 | 204。置き場は元の1件（共有イメージ）だけに戻った |
| 監査ログ | `ImportImage`・`DeleteImage`・`ImportKeyPair`・`DeleteKeyPair` が成功・失敗とも残った |

**空の qcow2 は起動しないので、「アップロードしたイメージから起動する」ところまでは実機で確かめていません。**API がそのイメージの実体を VM 作成時に渡すことは単体テストで検査しています（`import-from=` が作成パラメータに入ること）。

<a id="3-13"></a>
### 3-13. Webコンソール

ポータルのインスタンス一覧で、**稼働中の自分のVM**（管理者は全VM）に「コンソール」ボタンが出ます。押すと別タブで noVNC の画面が開きます。上部に Ctrl+Alt+Del・全画面・画面に合わせる・切断のボタンがあります。

API から開く場合:

```bash
curl -X POST -H "Authorization: Bearer $SHAKECLOUD_ACCESS_KEY" https://cloud.apextox.dpdns.org/v1/instances/i-0123456789abcdef0/console
```

返ってくる `url` を、**同じアカウントでログインしたブラウザ**で開きます。URL は5分有効で、別のアカウントでは使えません。

#### 仕組みと、そうした理由

**3段階に分けています。**2つの制約が逆を向いているためです。

1. `POST …/console` は**開けるかどうかの判定だけ**をして URL を返します（所有者か管理者か、稼働中か）。Proxmox にはまだ何も頼みません。
2. **ページを開いた瞬間に** Proxmox へ VNC のチケットと使い捨てパスワードを頼みます。Proxmox の VNC プロキシは起動してから**数秒しか接続を待たない**ので、接続の直前まで遅らせています。そのため**ページを再読み込みすれば新しいチケットで繋ぎ直せます**。
3. ページの WebSocket は **API が中継します**。ブラウザは WebSocket に `Authorization` ヘッダを付けられませんが、Proxmox の `vncwebsocket` はそれを要求するためです。API が自分の `cloudapi@pve` トークンで Proxmox に接続し、あとは**中身を解釈せずバイト列をそのまま双方向にコピー**します（WebSocket のライブラリは使っていません）。

**noVNC 1.7.0 を同梱しています**（`cloud/api/internal/server/web/static/novnc/`）。npm の sha512 と照合した tarball から無改変で取り、ライセンス（MPL-2.0）も同梱しました。CDN は使いません。更新手順は同じ場所の `PROVENANCE.md` にあります。

#### 守っていること

- **他サイトからは開けません。**Cookie で認証された WebSocket は、Origin がこのサイトでなければ断ります。`http.CrossOriginProtection` は POST などしか見ないので、GET で始まる WebSocket はここで別に守る必要があります。
- **1回のページ表示で張れる WebSocket は1本だけ**です。URL を誰かに見られても、横から同じ画面に入れません。
- **URL のトークンはログに出しません**（`/console/{token}` と記録します）。API のメモリ上もハッシュで持ちます。
- パスワードを含むページは**キャッシュさせません**（`Cache-Control: no-store`）。
- 開いた記録と接続した記録が、どちらも**監査ログに残ります**（`CreateConsoleSession`、`ConnectConsole`）。

#### 実機での確認（2026-09-11）

ブラウザを使わず、生の TLS ソケットで noVNC と同じ手順を踏みました（ページと WebSocket はアクセスキーでも認証できるため）。

| 確認 | 結果 |
| --- | --- |
| 起動中に `POST …/console` | **409**（まだ VM が無い） |
| 稼働後に `POST …/console` | 201、`/console/…` の URL |
| `console.js`・noVNC の `rfb.js`・`pako` | どれも 200 で `text/javascript` として配信 |
| ページ | 200。専用の CSP（`img-src 'self' data: blob:`）と `Cache-Control: no-store`、WebSocket のパスと使い捨てパスワードを含む |
| **API を通した WebSocket** | 101（accept キーも正しい）。**最初のフレームは VM の VNC サーバからの `RFB 003.008`**（マスク無しのバイナリ）。ブラウザ側 → API の中継 → Proxmox の `vncwebsocket` → VM の VNC、の全経路が実物で繋がった |
| 同じページ表示で2本目 | **404** |
| ページを再読み込みして接続 | 101 と `RFB 003.008`（再接続できる） |
| ログインせずにページを開く | **401** |
| 存在しない URL の WebSocket | **404** |
| API のログ | **トークンは出ていない**。接続と切断は記録されている |
| 監査ログ | `CreateConsoleSession`（成功と `IncorrectInstanceState`）、`ConnectConsole` |

**画面そのもの（noVNC がブラウザで絵を描くところ）は、この確認では見ていません。**ポータルの「コンソール」から開いて確かめてください。サーバ側は、テンプレートの項目がハンドラと一致することと、ページにインラインのスクリプトやスタイルが無いこと（CSP で弾かれるため）を Go のテストで検査しています。
