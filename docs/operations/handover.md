# クラウド開発の引き継ぎとTODO

更新日: 2026-09-11。状態: **土台（Proxmox・NetBox・Authentik）、クラウドAPI の Phase 1（ログイン・アクセスキー・監査ログ）、LAN の中の HTTPS（`*.apextox.dpdns.org`）、**Phase 2（API から VM が作れる）**、上限の変更と容量の表示、**大きさの自由指定・バルーニングの選択・GUI での一覧と編集**を実機で構築・確認済み。Phase 3（イメージのアップロード・SSH鍵・Webコンソール）も実機で確認済み。**Phase 4（ボリュームとセキュリティグループ）も 2026-09-11 に実機で確認済み（データセンターFW有効化・ボリュームの attach/detach・SG の遮断/許容まで）**。Phase 5 のセルフサービスポータルを完成させ（既存VMの引き取りを実装し、2026-09-11 に game1 を `shunyazhiyuan97` として実機引き取り済み。プール移動・既定SG適用・稼働継続を確認）、**ブートストラップ管理キーを無効化した**（以後はポータル発行のアクセスキー）。**Phase 6 の CLI と Terraform Provider を実装し、実機で確認した**。Phase 7 は storage-s3 VM と Garage を構築し、バケット・S3キーを扱うクラウドAPI・CLI・Terraform Provider・ポータル画面を実装、APIが発行した鍵で実クライアント（awscli）から PUT/LIST/GET/削除まで確認した。利用者の招待フロー（identity サービスの `invitations.py`）も実装した。Phase 2 の最初の部分までは [PR #2](https://github.com/rurutheGeek/shake-cloud/pull/2) でマージ済みで、それ以降の作業はまだ main に入っていない（Git の取り込みの時期は所有者が決める）。

**この文書が、クラウド開発の進捗とTODOの正本です。** 途中で担当が変わっても、ここを読めば「何が決まっていて、どこまでできていて、次に何をやるか」が分かるようにします。作業を終えたら表の状態と更新日を直してください。チャットや個人の作業メモにだけ残さないこと。

## 1. 何を作っているか

Proxmox VE の上に、**AWS の語彙で操作できる小さなプライベートクラウド**を作っています。

到達点は次のとおりです。

1. 利用者が Authentik（共通ログイン）のアカウントでポータルに入る
2. ポータル・Terraform・CLI のどれからでも自分のVMを作る
3. Webコンソールで入り、要らなくなったら消す

v1 の範囲は **EC2相当（VM）と S3（Garage）** です。オートスケール、冗長化、ネットワークのAPI化は作りません。一覧は[最小クラウドとProvider](../architecture/cloud.md)にあります。

## 2. 読む順番

| 順 | 文書 | 何が分かるか |
| --- | --- | --- |
| 1 | この文書 | 決定・入口とログイン情報の置き場所・進捗・TODO・引き継ぎ方法 |
| 2 | [最小クラウドとProvider](../architecture/cloud.md) | 設計と、Proxmox の権限制約に対する答え |
| 3 | [IaCの所有境界](../architecture/iac.md) | 誰が何を作るか、宣言ファイルの置き場所 |
| 4 | [クラウドAPIの構築](cloud.md) | 実機で行った手順・実測値・確認結果。API の配備と運用は 3-8 |
| 5 | `cloud/openapi/shakecloud.yaml` | API の正本。エンドポイント・フィールド・エラーコード |
| 6 | [shakecloud CLI](cli.md) | コマンドからの操作。アクセスキーの使い方とサブコマンド |
| 7 | [shakecloud Terraform Provider](terraform-provider.md) | Terraform から操作。リソースと例 |
| 8 | [Terraformの実行](terraform.md) | plan/apply の方法と、中断時の回収 |
| 9 | [秘密値の管理](secrets.md) | SOPS と age の扱い |

## 3. 確定した決定

**理由なく蒸し返さないでください。** 変えるときは、ここと関係する設計文書の両方を直します。

| 論点 | 決定 |
| --- | --- |
| APIの形 | AWS の語彙・状態遷移・フィールド名に揃えた自作 REST（OpenAPI が正本）。ワイヤ互換（SigV4、本物の `aws` CLI）は作らない |
| 認証 | ブラウザは Authentik の OIDC。機械は、ポータルで発行するアクセスキーを `Authorization: Bearer sca_<keyid>.<secret>` で送る |
| アクセスキーの発行 | **ポータルのログインからだけ。** アクセスキーで別のアクセスキーは作れない（漏れたキーが複製を作って居座れないように）。1アカウント5本まで。削除は行を残して無効化 |
| テナント | Authentik ユーザー1人 = 1アカウント |
| VM の見え方と権限 | **クラウドのVMは全員が見られる**（所有者名・イメージ・リソース・状態）。1台のホストを分け合うので、誰が何を動かしているか分からないと容量の判断ができないため。ただし**操作できるのは所有者と `cloud-admins` だけ**（他人のVMへの電源操作・削除は 403）。他人の `client_token` は返さない。`user_data` は一覧に出さない |
| VM の大きさ | **自由入力**。`vcpus`・`memory_mib`・`memory_min_mib`・`ballooning`・`root_disk_gib` を直接指定する。`instance_type`（`flavors.yaml` の名前）は**任意の近道**で、指定すると値が埋まるだけ。1つでも数値を上書きしたらその型名は外れる（カスタム扱い） |
| バルーニング | **VMごとに選べる。** `ballooning: false` なら固定メモリ（Proxmox の `balloon=0`）。`true` のとき `memory_min_mib` が回収の下限で、省略すると上限の 1/4（最低 512MiB） |
| 大きさの変更 | `PATCH /v1/instances/{id}`、**`cloud-admins` だけ**。vCPU・メモリ・バルーニングは**停止中のみ**（Proxmox は次回起動時にしか反映しないので、動作中に変えると台帳と実物が食い違う）。ディスクは稼働中でも**拡大のみ**。変更後の大きさでクォータと空き容量を再検査する |
| イメージのアップロード経路 | **API を通した直接アップロードだけ。**`download-url`（URL から Proxmox に取りに行かせる）は `cloudapi@pve` に **403**、`upload` は `content=import` を受ける（どちらも実測）。**Proxmox はチャンク転送を 501 で拒否する**ので本文の長さを先に宣言する必要があり、**「一切溜めずに流す」は成立しない**。cloud-01 の実ディスク（`storage/uploads`）へ一旦書いて大きさを確定させ、そこから流す。**`/tmp` は tmpfs なので使えない**。**中身の検査は Proxmox が qemu-img で行う**ので、壊れたファイルは弾かれ、何も残らない |
| イメージの上限 | 1イメージ **12GiB**（`max_image_gib`、管理者が変更可、0 は無制限）。置き場（Proxmox のルートFS 約94GiB）と cloud-01 のディスク（空き約31GiB）の**両方**に同じ大きさが要るので、小さい方に合わせてある。加えて置き場の空き（`image_store_min_free_mib`）を必ず残す |
| イメージの削除 | 所有者と `cloud-admins`。**共有イメージは API から消せない**（Terraform の宣言物）。既にそのイメージから作った VM は無関係（作成時にディスクへ複製済み）。**作成中の VM がある間だけ**削除を断る |
| SSH鍵 | 公開鍵だけを保存する。**`user-data` には触らず、NoCloud の `meta-data` の `public-keys` で渡す**（`user-data` はシェルスクリプトでもよい自由書式なので、他人の文書を書き換えないため）。鍵の本文は**承認時に**インスタンスへ複製するので、直後に鍵ペアを消されても入れない VM は生まれない。鍵ペアを後から消しても既存の VM は動き続ける |
| Webコンソール | **noVNC 1.7.0 を同梱する**（`web/static/novnc/`、npm の sha512 と照合した tarball から `core/`・`vendor/`・`LICENSE.txt` を無改変で。MPL-2.0。出所と更新手順は同じ場所の `PROVENANCE.md`）。**CDN は使わない**。ビルド無しの ES モジュールとして読み、CSP の `script-src 'self'` に収まる |
| コンソールの経路 | ブラウザは WebSocket に `Authorization` を付けられず、`vncwebsocket` はそれを要求するので、**API が自分の `cloudapi@pve` トークンで中継する**。**WebSocket のライブラリは足さない**。ハンドシェイクだけ双方と行い、以後はフレームを解釈せずバイト列を双方向にコピーする（ブラウザのマスク付きフレームは Proxmox が期待する形、Proxmox の非マスクのフレームはブラウザが期待する形なので、そのまま正しい）。圧縮などの拡張はどちら側とも交渉しない |
| コンソールの手順と期限 | ①`POST /v1/instances/{id}/console`（所有者と管理者だけ、稼働中だけ）が**5分有効・アカウントに結び付いた URL** を返す。**この時点では Proxmox に何も頼まない**。②その**ページを開くたびに** Proxmox の新しいチケットと使い捨てパスワードを発行する（Proxmox の VNC プロキシは数秒しか WebSocket を待たないので、接続の直前まで遅らせる。再読み込みがそのまま再接続になる）。③WebSocket は**1回のページ表示につき1本だけ** |
| コンソールの防御 | **Cookie で認証された WebSocket は Origin が自サイトでなければ断る**（`CrossOriginProtection` は GET を見ないので、他サイトからのクロスサイト WebSocket 乗っ取りはここで止める）。アクセスキーは他サイトのページから送れないので Origin は問わない（CLI 用）。URL のトークンは**アクセスログに出さず**（`/console/{token}` と記録）、メモリ上も**ハッシュで持つ**。ページは `Cache-Control: no-store`（パスワードを含むため） |
| v1 の範囲 | EC2相当 + S3（Garage）。サーバレス・RDB は Kubernetes 構築後 |
| EC2 の追加機能 | 追加ボリューム、セキュリティグループ。スナップショットと IMDS は作らない |
| 運用機能 | クォータと空き容量検査、差分リコンサイラ、監査ログ。削除保護は作らない |
| Web UI | フルのセルフサービスポータル |
| イメージ | 利用者が API へ直接アップロード（他に道が無いことを実測で確認。下の「イメージのアップロード経路」） |
| user-data | 完全に自由（NoCloud seed ISO で渡す） |
| CLI | 作る |
| 置き場所 | API と管理DB（PostgreSQL）は専用VM `cloud-01`。コードは `cloud/`（`cloud/api` が Go、`cloud/openapi` が正本） |
| API の実装 | Go の標準 `net/http`（CSRF 対策は `http.CrossOriginProtection`）、`pgx`、`go-oidc`。**OpenAPI からのコード生成はしない。** エンドポイントが少ないうちは生成物の保守の方が重いので、Go のルート表と OpenAPI の一致をテスト（`routes_test.go`）で保証する |
| Terraform Provider 名 | `shakecloud_*` |
| 管理面の分離 | VLAN で分ける。**まず管理はタグなし（ネイティブVLAN）のまま、利用者VM（cloud）だけをタグ付きVLANに載せる。**切り替えは `network.yaml` の `vlan.cloud.vlan_id`（＋ `cloud.prefix`／range）を埋めるだけで行う。宣言と手順は [VLAN 分離への切替](vlan.md) |
| Authentik | identity VM（110）に**新規構築**した。作業機上の `stacks/hub` は検証用で、移行しない |
| Authentik の `sub` | `user_uuid`。プロバイダを作り直しても変わらないため |
| 知らない `sub` と既知のメール | ログインを拒否する（`AccountConflict`）。別アカウントを黙って作ると、その人のリソースが2つに分かれるため |
| ポータルの入口 | `https://cloud.apextox.dpdns.org`（OIDC の戻り先は `/auth/callback`） |
| HTTPS の入口 | 各ホストの Caddy（`stacks/tls-proxy/`）が Let's Encrypt の証明書を DNS-01 で取り、同じホストの 127.0.0.1 のサービスへ中継する。1台に集めず各ホストに置くのは、認証基盤（identity）を他のホストの障害に巻き込まないため。代わりに Cloudflare の DNS トークンが各ホストに載る |
| ドメイン | **`apextox.dpdns.org`**（DigitalPlat の無料ドメイン。DNS は Cloudflare に委任）。**インターネットには公開しない。** グローバルIPも使わず、HTTPS の証明書を DNS-01 で取るためにだけ使う。`home.arpa` と自前CAにしなかったのは、全端末へ CA を登録する手間と、スマホアプリが自前CAを信用しない問題を避けるため |
| OIDC クライアントの秘密値 | **SOPS へ複製しない。** 正本は identity VM の `oidc-cloud.json` で、`cloud.yml` が配備のたびに直接写す。2か所に持つと、作り直したときに食い違うため |
| ブートストラップ管理キー | cloud-01 のファイルが正本。起動時に DB をファイルへ合わせる。API から削除したキーは再起動しても復活しない。**2026-09-11 に無効化した**（以後はポータルでログインして発行するアクセスキーを使う。緊急時は `rotate-bootstrap-key` で作り直す） |
| インスタンスの上限 | **既定値は `platform/terraform/cloud.yaml`、変更は `cloud-admins` が実行中に行う**（`PUT /v1/limits` かポータルの「上限」）。管理DBには管理者が変えた項目だけを入れ、読むたびに既定値と重ねる（同じ事実を2か所に持たない）。既定は1アカウント 8台・32vCPU・32GiB・ディスク計 1000GiB、クラウド全体のメモリ枠 32GiB、ノードに 4GiB 残す、ディスク実使用率 85%。**0 は無制限。**停止中も数える |
| 上限とホストの保護の関係 | **上限の合計が物理メモリを超えることを許す**（バルーニング前提）。物理を見ているのは「ノードの `available` が指定量残るか」と「ディスクの実使用率」の2つだけで、これは上限を無制限にしても残る。この2つを 0 にすると基盤VMごと倒せる。[配備台帳の実測](../architecture/operations.md#measured-budget) |
| VMID | API が 5000–5999 から採番する。**他が使っていた VMID は隔離し、二度と払い出さない**。プローブ用の 5998・5999 は使わない |
| VM の識別 | 作った VM の description に instance ID を書く。**それが無い VM には触らない**（削除も電源操作もしない） |
| 削除 | VM・ディスク・seed ISO・NetBox の IP をすべて解放してから `terminated` にする。作成に失敗したときも同じ経路で片付ける。Terminate は成功するまで諦めない（諦めると資源が漏れる） |
| 差分リコンサイラ | 外での電源変更（ゲスト側の shutdown、GUI の操作）には追従する。**消えて見える VM は消さない。** ACL の事故と区別できないので記録だけ。全台が同時に見えないときは何もしない |
| 宣言の置き場 | 秘密でない値は Git の YAML（`platform/terraform/*.yaml`）。**tfvars は使わない** |
| 実機依存の値 | `site.yaml` は `tools/site-yaml.py --api` が実機から生成する。手で書かない |
| 自動化の範囲 | `10-platform` は将来 AWX に任せる。`00-bootstrap` は特権なので人が承認して実行する |
| メモリとディスク | メモリはバルーニング、ディスクはシンプロビジョニングが既定。どちらも空き容量には数えない |
| 秘密値 | すべて自動生成する。人に鍵を作らせたり、変えさせたりしない |
| NetBox | LAN に公開。`https://netbox.apextox.dpdns.org`。Terraform・Ansible・クラウドAPI が使う `http://192.168.10.200:8000` はまだ開けている |
| ドキュメントサイト | services-01 に置いて LAN に公開（`https://docs.apextox.dpdns.org`）。Git の `docs/` が正本で、旧ハブの「Nextcloud で編集する」仕組みは持ち込まない。Kubernetes ができたら設計どおり worker-01 へ移す |
| game1（VMID 100） | 2026-09-11 に `cloud` プールへ移し、クラウドAPIが `shunyazhiyuan97`（ゲームサーバ開発者）のインスタンスとして引き取った。VMID 100 は `pools.yaml` の `reserved_vmids` で引き続き確保（public-edge には使わない） |
| メール送信 | **外部SMTPリレーを各アプリから直接使う。Postfix（ローカルMTA）は置かない。** 家庭回線のIPからの直接MX配送は PTR・SPF/DKIM・ポート25遮断で拒否・迷惑メール扱いになりやすいため。**2026-09-12 に Gmail（`shake.notify@gmail.com`、アプリパスワード）を設定済み・実送信確認済み。** SMTP の資格情報は `platform/sops/smtp.sops.yaml` に置き、identity 配備で `.env` へ写す。招待メールは `stacks/identity/invitations.py` が送る（[SMTPとメール送信](smtp.md)） |

## 4. いまの実機

Proxmox ホストは `apextox`（`https://192.168.10.126:8006`、PVE 9.2.2）です。

| VMID | 名前 | IP | 役割 | 状態 |
| --- | --- | --- | --- | --- |
| 100 | game1 | 192.168.10.127 | ゲームサーバ（Bazzite、GPUパススルー hostpci0/1）。`cloud` プール | 稼働。2026-09-11 にクラウドAPIへ引き取り済み（owner `shunyazhiyuan97`、instance `i-bec54e3a0169b3660`、既定SG） |
| 110 | identity | 192.168.10.204 | Authentik | 稼働。`https://auth.apextox.dpdns.org`（`:9000`・`:9443` は 127.0.0.1 に閉じた） |
| 130 | storage-s3 | 192.168.10.206 | Garage（S3互換オブジェクトストア、単一ノード） | 稼働。S3 `:3900`、管理API `:3903`。データは専用ディスク32GiB（`/srv/garage`） |
| 140 | cloud-01 | 192.168.10.205 | クラウドAPI（Phase 1）と管理DB | 稼働。`https://cloud.apextox.dpdns.org`（`:8080` は 127.0.0.1 に閉じた）。メモリ使用 約500MiB / 2GiB |
| 150 | services-01 | 192.168.10.200 | NetBox、ドキュメントサイト（台帳・共有サービスの過渡的な置き場） | 稼働。`https://netbox.apextox.dpdns.org`（`:8000` も開いている）、`https://docs.apextox.dpdns.org`（`:8090` も開いている） |
| 200 | k8s-cp-01 | 192.168.10.207 | Kubernetes control plane・etcd | 稼働。**Ready**。kubeadm 1.36.4、Cilium 1.20.1 |
| 210 | k8s-worker-01 | 192.168.10.209 | Kubernetes worker（AWX・クラウドなど） | 稼働。**Ready**。join 済み |
| 211 | k8s-worker-02 | 192.168.10.208 | Kubernetes worker（予備） | **停止のまま**。`tools/k8s up --all` で起動し `--limit k8s-worker-02` で join |
| 400 / 401 | dev-a / dev-b | .202 / .203 | 開発VM。dev-b が自動化の実行ホスト | 稼働 |
| 900 | probe-01 | 192.168.10.201 | 検証用 | 稼働 |
| 5997 | shakecloud-volumes | — | ボリュームのホルダー（デタッチしたディスクの待機先）。起動しない | 停止。API が初回のボリューム作成時に作る |

`cloud` プールにあるのは、ボリュームのホルダー（5997）と、引き取った game1（VMID 100。プール所属はVMIDの範囲に依らない）です。利用者VMを新規作成すると 5000–5999 から採番し、game1 の 100 は使いません。IP はクラウド用に `.100`–`.180`、基盤用に `.201`–`.249` を NetBox の IP Range で分けています。game1 の `.127` は NetBox に予約登録してあり、新規VMには払い出されません。

## 5. サービスの入口とログイン情報の置き場所

**パスワードそのものはここに書きません。** 置き場所と、取り出し方だけを書きます。

| サービス | 入口 | ログイン名 | 資格情報の置き場所 |
| --- | --- | --- | --- |
| Proxmox の画面 | `https://pve.apextox.dpdns.org:8006`（証明書は Let's Encrypt。IP `192.168.10.126:8006` でも入れるが、名前が一致しないので警告が出る） | `root`（Realm: Linux PAM） | `platform/sops/proxmox-root.sops.yaml` の `PROXMOX_VE_PASSWORD`（ACME アカウントの作成に要るので入れた） |
| Proxmox の画面（開発者） | 同上 | `dev-a@pve` / `dev-b@pve`（Realm: Proxmox VE） | `platform/sops/pve-users.sops.yaml` |
| Proxmox ホストへの SSH | `root@192.168.10.126` | 鍵のみ | **dev-b の鍵は登録されていない**（2026-09-10 に拒否を確認）。入れる鍵は人が管理している。API なら root トークン（`proxmox-root.sops.yaml`）で届く |
| NetBox | `https://netbox.apextox.dpdns.org` | `admin` | services-01 の `/opt/netbox-stack/secrets/superuser_password` |
| NetBox API | `http://192.168.10.200:8000/api/`（ツールの接続先。`https://netbox.apextox.dpdns.org/api/` でも届く） | トークン | 書き込み: `netbox.sops.yaml`、読み取り: `netbox-inventory.sops.yaml`、クラウドAPI用: `cloudapi.sops.yaml` |
| Authentik | `https://auth.apextox.dpdns.org` | `akadmin` | identity の `/opt/identity-stack/secrets/bootstrap_password` |
| クラウドのポータル | `https://cloud.apextox.dpdns.org` | Authentik のアカウント（`cloud-users` か `cloud-admins`） | Authentik 側。`akadmin` は `cloud-admins` に入っている |
| クラウドAPI（Terraform・CLI・curl） | `https://cloud.apextox.dpdns.org/v1/` | アクセスキー | 利用者の分はポータルで発行（表示は一度だけ）。管理用ブートストラップキーは 2026-09-11 に無効化（§6 Phase 5）。緊急時は cloud-01 で `manage.py rotate-bootstrap-key` |
| 開発VM への SSH | `debian@192.168.10.202` / `.203` | パスワードまたは鍵 | `.local/devvm-passwords.yml`（**devbox の playbook を実行した作業機の手元にだけある平文**。dev-b には無い） |
| 基盤VM への SSH（services-01、identity、cloud-01、probe-01） | `debian@<IP>` | 鍵のみ | 鍵は `platform/terraform/access.yaml`。dev-b からは `~/.ssh/id_ed25519_pve` |
| Terraform の state | Cloudflare R2 | アクセスキー | `platform/sops/s3.sops.yaml` |
| DNS（`apextox.dpdns.org`） | Cloudflare ダッシュボード（ゾーンID `112734e967c919ddd9ec1fa5c4f2a320`） | 所有者の Cloudflare アカウント | 証明書用のトークン（このゾーンの DNS 編集だけ）: `platform/sops/cloudflare-dns.sops.yaml` |
| ドキュメントサイト | `https://docs.apextox.dpdns.org` | 不要（LAN 内に公開） | 資格情報なし。原稿は Git の `docs/`、配備は `platform/ansible/docs-site.yml` |
| メディア系（Homarr、Nextcloud など） | 旧構成のハブ。SSH トンネル経由 | 旧 Authentik | この基盤の外。[ハブ運用](hub.md) |

VM の中にある値の取り出し方（dev-b で実行）:

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.200 sudo cat /opt/netbox-stack/secrets/superuser_password
```

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.204 sudo cat /opt/identity-stack/secrets/bootstrap_password
```

```bash
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.205 sudo cat /opt/cloud-stack/secrets/bootstrap_admin_key
```

SOPS の値の取り出し方:

```bash
sops --decrypt platform/sops/pve-users.sops.yaml
```

## 6. 進捗とTODO

✅ 済み ⬜ 未着手 🟨 途中 👤 人の手が要る

### Phase 0 — 土台

| 状態 | 作業 | メモ |
| --- | --- | --- |
| ✅ | `00-bootstrap` 適用（`cloudapi@pve`、ロール4種、ACL、`cloud-images` ストレージ） | [cloud.md §3](cloud.md) |
| ✅ | 実機プローブ4つ（空き容量、ISO の上げ下ろし、プール境界、noVNC） | すべて PASS。`tools/verify-cloud.py` |
| ✅ | `10-platform` 適用（identity、cloud-01、NetBox の IP Range） | 再 plan で差分なし |
| ✅ | NetBox の書き込みアイデンティティ `cloudapi` | `virtualization` と `ipam` にだけ書ける。実測済み |
| ✅ | NetBox の LAN 公開 | `platform/ansible/roles/netbox` |
| ✅ | Authentik の新規構築、`cloud-users` / `cloud-admins`、OIDC クライアント `cloud` | `stacks/identity/`、`platform/ansible/identity.yml`。再実行で変更ゼロ |
| ✅ | ドメイン `apextox.dpdns.org` を取得し、DNS を Cloudflare へ委任 | 2026-09-10。ゾーンは有効、レコードはまだ無い。DNS 編集トークンは SOPS に格納し、動作を確認済み |
| ✅ | 名前を決めて HTTPS にする（Authentik・ポータル・API・NetBox・ドキュメントサイト） | 2026-09-10。Terraform `20-dns` と各ホストの Caddy。証明書は Let's Encrypt。Authentik と API の平文ポートは 127.0.0.1 に閉じた。[cloud.md 3-9](cloud.md) |
| ✅ | Proxmox 本体の証明書（`pve.apextox.dpdns.org`） | 2026-09-10 に取得（Let's Encrypt、`CN=pve.apextox.dpdns.org`、期限 12/9）。ACME アカウント・Cloudflare プラグイン・証明書のすべてを `00-bootstrap` の `acme.tf` が作る。**ACME アカウントの作成だけ API トークンでは通らない**（root のトークンでも `user != root@pam`）ので、`proxmox-root.sops.yaml` の `root@pam` のパスワードで ticket 認証に切り替えて流す（`tools/tf` が自動で判断）。**画面での手作業は無い** |
| ⬜ | NetBox を使うツール（Terraform・Ansible・クラウドAPI）の接続先を `https://netbox.apextox.dpdns.org` へ移し、`:8000` と `:8090` を閉じる | `netbox.sops.yaml`・`netbox-inventory.sops.yaml`・`cloudapi.sops.yaml` の URL を変える |
| ⬜ | 外出先（Tailscale）から名前で使えるようにする | Tailscale の DNS がどの名前にも SERVFAIL を返す件と、LAN へのサブネットルートが未設定 |
| ✅ | OIDC クライアントの秘密値を cloud-01 へ渡す | SOPS へ入れる予定だったが、identity VM から直接写す方式に変えた（§3） |
| ✅ | 新しい Authentik での利用者の作り方（招待フロー） | identity サービスの `stacks/identity/invitations.py`（`configure`/`invite`/`list`/`revoke`、標準ライブラリのみ）。**招待専用フロー・1回限り・24時間・`cloud-users` へ**。**メール送信に対応**（`smtp.sops.yaml` の `SMTP_*` を `.env` 経由で読み、現在は Gmail。無ければリンクを 0600 で保存）。配備（`identity.yml`）で `configure` が走る。実機確認済み（[cloud.md 3-17](cloud.md#3-17)・[smtp.md](smtp.md)） |
| ✅ | データセンターのファイアウォール有効化 | Phase 4 の前提。`platform/terraform/00-bootstrap/firewall.tf` で安全に自動化し、**2026-09-11 に適用済み**（再 plan は No changes）。ノードFWは無効、DC FWは有効・既定ACCEPT、`nf_conntrack_allow_invalid=1`。既存の基盤VM・game1 への通信に影響がないこと、`nf_conntrack_allow_invalid=1` が入っていることを実機で確認。次に触る場合は物理コンソール/IPMI を用意する |
| 🟨 👤 | VLAN 工事（ルータ、スイッチ、`vmbr0` を VLAN 対応に） | 物理機器の作業を含む。**宣言と安全装置・手順書は用意済み**（`network.yaml` の `vlan`、`managed-host` と `site.Validate` の precondition、[vlan.md](vlan.md)）。実機切替は人の物理作業待ち |

### Phase 1 — Go の足場、認証、監査ログ

| 状態 | 作業 | メモ |
| --- | --- | --- |
| ✅ | `cloud/openapi/shakecloud.yaml`（API の正本） | ルート表との一致を `routes_test.go` が検査 |
| ✅ | `cloud/api/`: HTTP、設定、PostgreSQL 接続とマイグレーション、`/healthz` | マイグレーションは `internal/db/migrations/`。起動時に advisory lock 下で適用 |
| ✅ | OIDC ログイン（Authentik）と、アクセスキーの発行・一覧・失効 | state のブラウザ束縛・nonce・PKCE。偽の OIDC プロバイダで本物のコードを通すテストあり |
| ✅ | 監査ログ | 追記専用（トリガーで UPDATE/DELETE/TRUNCATE を拒否）。`GET /v1/audit-events` |
| ✅ | 開発用のブートストラップ管理キー | `manage.py rotate-bootstrap-key` / `disable-bootstrap-key` |
| ✅ | Phase 1 の最小ページ（ログイン、キーの発行・削除、操作履歴） | `html/template` と素の JS。ビルド基盤なし。Phase 5 で置き換える |
| ✅ | `cloud/compose.yaml` と `cloud/manage.py`（既存スタックと同じ作法） | API のイメージは cloud-01 でビルド。ベースイメージは Dockerfile で digest 固定 |
| ✅ | Ansible ロール `cloud_api` と `platform/ansible/cloud.yml` | 2026-09-10 に配備。再実行で変更ゼロ |
| ✅ | CI に Go を追加（`gofmt -l`、`go vet`、`go test ./...`、PostgreSQL サービス） | `validate.yml`。2026-09-11 に push して GitHub 上で初めて実行し、`push` と `pull_request` の両方で成功した |
| ✅ | 実際のブラウザで Authentik ログインを1回通す | 2026-09-10 に `akadmin` で確認。監査ログに `CompleteLogin`（アカウント作成、管理者）、`CreateAccessKey`、`DeleteAccessKey` が残った |

実機で確かめたこと（2026-09-10、dev-b から）:

| 確認 | 結果 |
| --- | --- |
| `/healthz` | 200 |
| `/auth/login` | Authentik の authorize へ 302。`redirect_uri`・PKCE（S256）・scope が正しく、Authentik はエラーでなくログイン画面へ進んだ |
| ブートストラップ管理キーで `GET /v1/caller-identity` | 200、`bootstrap-admin`（管理者） |
| アクセスキーで `POST /v1/access-keys` | 403 `UnauthorizedOperation` |
| 秘密値だけ違うキー | 401。監査ログに `AuthFailure`（`secret_mismatch`） |
| セッションなしの一覧、クロスサイトの POST | 401、403 `CrossOriginRequestBlocked` |
| `cloud.yml` の再実行 | `changed=0` |

### Phase 2 以降

| 状態 | Phase | 内容 |
| --- | --- | --- |
| ✅ | 2 | **VMが1台できる縦串**。2026-09-10 に実機で確認（作成 → SSH でログイン → 削除 → 残骸なし）。冪等性（`client_token`）、クォータと空き容量、VMID の採番と隔離、NetBox での IP 採番、seed ISO、一覧・電源操作・Terminate、差分リコンサイラを含む。[cloud.md 3-10](cloud.md) |
| ✅ | 2 の追加 | **上限を管理者が変えられるようにし、容量が見えるようにした。**`GET /v1/capacity`（CPU・メモリ・ストレージ・配った合計・アカウント別）、`GET`/`PUT /v1/limits`、ポータルの「容量」と「上限」。16GiB の `2xlarge` を追加。2026-09-10 に実機で確認（上限の上書きと復帰、16GiB の VM が `balloon=4096` で起動 → 削除して残骸なし、監査ログに記録）。[cloud.md 3-11](cloud.md#3-11) |
| ✅ | 2 の追加 | **大きさを自由に指定できるようにし、GUI に一覧と編集を出した。**`vcpus`・`memory_mib`・`memory_min_mib`・`ballooning`・`root_disk_gib` を直接指定（`instance_type` は任意の近道）。`PATCH /v1/instances/{id}`（管理者のみ）。ポータルの「インスタンス」で作成・電源・削除・編集ができ、**クラウドの全VMが所有者名つきで並ぶ**。2026-09-11 に実機で確認（バルーニングなしで `balloon=0`、稼働中のディスク拡大、縮小の拒否、停止後の vCPU・メモリ・バルーニング変更が実物に反映、削除して残骸なし）。[cloud.md 3-10](cloud.md) |
| ✅ | 3 | **イメージのアップロード、SSH鍵ペア、Webコンソール。**2026-09-11 に実機で確認。本物の qcow2 が入って消え、フィンガープリントは `ssh-keygen -lf` と一致し、`user_data` なしで SSH ログインできた（`meta-data` の `public-keys`）。コンソールは API を通した WebSocket の最初のフレームが VM の VNC サーバからの `RFB 003.008` だった（noVNC 1.7.0 を同梱、中継は API）。**ブラウザで画面が描かれるところは、人がポータルから開いて確かめる**。[cloud.md 3-12](cloud.md#3-12)・[3-13](cloud.md#3-13) |
| ✅ | 4 | **ボリュームとセキュリティグループを実装し、2026-09-11 に実機で確認。** `cloud/api/internal/compute/{volumes,volume_worker,securitygroups,firewall}.go`、DBマイグレーション `0006`、API エンドポイント、ポータル画面、Terraform の DC FW 有効化まで含む。実機では `volume_reassign`・`vm_firewall` プローブが PASS、ボリュームの作成→アタッチ→ゲストで `/dev/disk/by-id/virtio-<serial>` 認識→拡張→デタッチ→削除が通り、SSH のみ許可した SG で 8000 番と ICMP が遮断・許可ルール追加で回復した。残骸なし。**検証中に見つけた「ルール変更で Proxmox が live ruleset を再構築しない」バグを修正**（`setFilteredOptions` を毎回書く。§10 参照）。再現は `tools/verify-volumes.py`（`tests/test_verify_volumes.py` が判定を検査） |
| ✅ | 5 | **セルフサービスポータルを完成させ、ブートストラップ管理キーを無効化（2026-09-11）。** ポータルはVM・ボリューム・SG（受信/送信ルール）・イメージ・SSH鍵・アクセスキー・容量・上限・操作履歴を扱え、古い文言も直した。既存VMの引き取りも実装し、**game1（VMID 100）を `shunyazhiyuan97` として引き取り済み**（`i-bec54e3a0169b3660`、IP `192.168.10.127` を NetBox に予約）。ブートストラップ管理キーは無効化し、以後はポータル発行のアクセスキーを使う（緊急時は `manage.py rotate-bootstrap-key`） |
| ✅ | 6 | **CLI と Terraform Provider を実装・実機確認（2026-09-11）。** CLI（`cloud/client`・`cloud/cli`）は identity・capacity・limits・events・instance・volume・sg・image・key・access-key を操作。Provider（`cloud/provider`、`terraform-plugin-framework`）は `shakecloud_instance`・`shakecloud_volume`・`shakecloud_volume_attachment`・`shakecloud_security_group`・`shakecloud_security_group_rule`・`shakecloud_key_pair` と `shakecloud_caller_identity`。実機で apply/plan‑no‑changes/import/destroy を確認。[CLI](cli.md)・[Provider](terraform-provider.md) |
| ✅ | 7 | **Garage を storage-s3 VM（VMID 130、.206）へ単一ノードで構築し、バケット・S3キーを扱うクラウドAPIを実装（2026-09-11）。** データは専用32GiBディスク。API の `POST /v1/buckets`・`POST /v1/s3-keys`・権限の付与/剥奪で Garage の管理API v2 を操作する。CLI に `bucket`・`s3-key`、**Terraform Provider に `shakecloud_bucket`、ポータルに「S3バケット」画面**（作成・キー権限・S3キー発行）を追加。**実クライアント（awscli）で、APIが発行した鍵を使い PUT/LIST/GET/削除まで確認**。Garage 自体は [garage.md](garage.md)、APIは [cloud.md 3-16](cloud.md#3-16) |
| 🟨 | 8 | **切替の宣言・安全装置・手順書を用意（2026-09-11）。** `network.yaml` の `vlan`、`10-platform` がそこから管理VLANを読む形、`managed-host` と `site.Validate` の「bridge が vlan-aware でないのに vlan_id を設定したら止める」precondition、API が作るVMへのタグ付け、[vlan.md](vlan.md) の段階手順とロールバック。**実機切替は物理スイッチ/ルータと Proxmox bridge の作業待ち** |
| 🟨 | K8s | **スライス①〜③を実機で確認（2026-09-12）。** cp-01 と worker-01 が **Ready**、Cilium 1.20.1 が kube-proxy を置換、Pod間通信・NetworkPolicy・**local-path の PVC 永続化**・**MetalLB の LoadBalancer（`.240`）**・**cert-manager の CA** まで動作。worker-02 は停止のまま（`--limit` で後から join）。`tools/k8s up\|down` で起動/停止。**Flux/SOPS は Git の取り込み方の決定待ち**。次は AWX・CloudNativePG・Knative | [kubernetes.md](kubernetes.md) |

各 Phase の詳しい中身と完了条件は[最小クラウドとProvider](../architecture/cloud.md)にあります。

## 7. 未決事項と後回しにしたこと

| 項目 | 現状 | 決めるときの材料 |
| --- | --- | --- |
| パスキー | 2026-09-10 に `akadmin` が登録した。予備の認証器と、失くしたときの復旧方法は未決 | 名前（`auth.apextox.dpdns.org`）を変えると登録し直しになる。予備の認証器と復旧方法を先に決める。[ネットワーク・SSO](../architecture/network-auth.md) |
| 無料ドメインの継続性 | DigitalPlat の更新・取り消しの規則は確認できていない | 取り上げられたら名前の付け替えになる。困るようなら有料ドメイン（候補 `ruruthegeek.org`）へ移す |
| メディア系の認証 | 旧 `stacks/hub` の Authentik のまま | 新しい identity へ寄せるかは未決 |
| public-edge の VMID | 設計上は 100 だが、game1 が使用中 | public-edge を作るときに別の番号を決める |
| `05-seed` の SSH 鍵 | **解決済み（2026-09-12）**: `access.yaml` の `seed_ssh_public_keys` へ移した。実機（VMID 150 の `sshkeys`）の順序＝admin 先頭2鍵の逆順と一致。`05-seed/main.tf` が access.yaml を読む（`tests/test_platform_inventory.py` が検査） | — |
| cloud-01 のサイズ | `small`（2GiB）。Phase 1 の実測で使用 約500MiB（API 7MiB、PostgreSQL 65MiB） | Phase 2 以降の負荷を見て、足りなければ `medium`。その分、利用者VMに回せる余白が減る |
| ポータルのフロント | `html/template` と素の JS。**2026-09-12 に[Web GUI監査・改善案](../audits/webgui-2026-09-12.md)を作成**（P1 6件・P2 10件）。同じ監査の指摘どおり、送信ロックとVMの `client_token`、ID単位の一覧更新と入力保持、選択IDの保持、日本語のエラーと操作箇所への表示、用途別ナビ、検索・絞り込み、履歴の検索・ページ送り・詳細、アップロードの段階表示と中断、S3権限の用途選択と owner 既定オフ、上限の差分確認を `index.html`・`portal.js`・新規 `portal-ui.js`・`portal.css` へ実装 | 模擬APIと実ブラウザ（Chrome Headless Shell 153）で機能28項目とキーボード操作、axe-coreの自動検査（一般利用者／管理者・ライト／ダークの3画面、違反0件）を確認し、**dev-bのPostgreSQLを使って`go vet ./...`と`go test ./...`（cloud/api全パッケージ）も通した**（連打・入力保持・選択保持・320/390px・コントラスト・502/401・S3権限・上限差分・雛形・アップロード段階／中断とサーバー側の接続断）。結果は監査の「改修後の確認」と[確認結果JSON](../audits/webgui-2026-09-12/after-results.json)に残した。**2026-09-12 に `cloud.yml` で cloud-01 へ配備**し、`/healthz` 200 と新規 `/static/portal-ui.js`・`portal.js`・`portal.css` の配信を確認。未確認は、Authentikログインで確立する認証済みポータルでの画面操作、実VM／実S3の作成・変更、実機のスクリーンリーダー。新しい JS ビルド基盤は増やさない前提 |
| 管理DBのバックアップ | **定期実行を実装（2026-09-12）**: cloud-01 の `cloud-backup.timer` が毎日 `manage.py backup --keep 14` を `/var/backups/cloud-api` へ。**外部コピーは未着手**（Garage は単一ノードなので唯一の控えにしない） | 別ディスク／外部へのコピー先を決める（[cloud.md 3-18](cloud.md#3-18)） |
| state の置き場 | Cloudflare R2 | Phase 7 で Garage へ移すか。クラウドが止まっていても読める場所という条件がある |
| AWX | 未構築 | Kubernetes が前提。できるまでは dev-b から人が実行する |
| Terraform の版 | **解決済み（2026-09-12）**: `.terraform-version`＝`1.15.8` が唯一の出所。CI は同ファイルを読み、`devbox` ロールも同版のバイナリを入れる（`tests/test_terraform_version.py` が検査） | — |

## 8. 引き継ぐ人のアクセス

今は**アクセス手段が dev-b の1か所に集まっています。** 引き継ぐときは、同じものをもう1人分作ります。どれも既存の保持者が1回操作すれば済み、秘密値そのものを受け渡す必要はありません。

| 必要なもの | 今どこにあるか | 新しい人の分を作る方法 |
| --- | --- | --- |
| SOPS の復号（age 鍵） | dev-b の `~/.config/sops/age/keys.txt` | 新しい人が自分の age 鍵を作り、**公開鍵だけ**を渡す。保持者が `.sops.yaml` へ足し、`sops updatekeys platform/sops/*.sops.yaml` を実行する（[秘密値の管理](secrets.md)） |
| 基盤VMへの SSH | `platform/terraform/access.yaml` の公開鍵 | 公開鍵を `admin_ssh_public_keys` の**末尾に**足す（順序を変えない）。新しく作るVMにはこれで入る。既にあるVMには、入れる人が `ssh-copy-id` か Ansible で足す |
| Proxmox ホストへの SSH | 人が管理（dev-b の鍵は未登録） | ホストの `authorized_keys` へ公開鍵を足す |
| クラウドの管理者権限 | Authentik の `cloud-admins` グループ | 新しい人の Authentik アカウントを `cloud-admins` に入れる。ブートストラップ管理キーは共有しない |
| 手元にしか無い設定 | `platform/ansible/pve.ini`、`seed.ini`、`.local/pve-readonly.env` | `.example` から作る。`pve-readonly.env` は `site.yaml` を作り直すときだけ要る |
| Go のツールチェーン | dev-b の `~/.local/go`（1.27.1。apt の版は古い） | `https://go.dev/dl/` から取得して `PATH` に足す。版は `cloud/api/go.mod` に合わせる |

VM の中にある秘密値は、次の場所で自動生成されています。Git には入りません。

| 場所 | 中身 |
| --- | --- |
| services-01 `/opt/netbox-stack/secrets/` | NetBox の DB・鍵、各トークン（`inventory` / `terraform` / `cloudapi`） |
| identity `/opt/identity-stack/secrets/` | Authentik の DB・鍵、`akadmin` の初期パスワード、ブートストラップトークン、`oidc-cloud.json` |
| cloud-01 `/opt/cloud-stack/secrets/` | 管理DBのパスワード、`oidc_credentials`（identity の `oidc-cloud.json` の写し）。`bootstrap_admin_key` は 2026-09-11 に無効化して空 |
| identity・cloud-01・services-01 の `/opt/tls-proxy/secrets/` | Cloudflare の DNS 編集トークン（`cloudflare-dns.sops.yaml` の写し）。証明書は `/srv/tls-proxy/storage/data` |

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
| `platform/sops/pve-users.sops.yaml` | 開発VM用の Proxmox ユーザー |

## 9. 確認のしかた

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

**アクセスキーはポータルで発行したものを使います**（ブートストラップ管理キーは 2026-09-11 に無効化済み。§5・§6 Phase 5）。ポータルにログイン →「アクセスキー」→ 発行し、表示された一度きりの値を環境変数に入れます。どうしても管理キーが要る場合は `manage.py rotate-bootstrap-key` で作り直します。

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

ボリュームとセキュリティグループは、実際に遮断・許可されるところまで見ます（§6 Phase 4、`SHAKECLOUD_ACCESS_KEY` が要ります）:

```bash
sops exec-env platform/sops/cloudapi.sops.yaml 'python3 tools/verify-volumes.py'
```

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml 'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/identity.yml'
```

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml 'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/cloud.yml'
```

ドキュメントサイトの更新（**静的インベントリで流します**。理由は §10）:

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
