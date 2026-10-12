---
title: 決定ログ
updated: 2026-10-12
section: 設計
audience: 管理者・開発者
tags:
  - design
  - decisions
---

# 決定ログ

> **更新日** 2026-10-12 ・ **区分** 設計 ・ **読む人** 管理者・開発者

このホームラボで**すでに決まっていること**と、その理由です。`operations/handover.md` の「確定した決定」を、進捗と分けてここへ移しました。

**理由なく蒸し返さないでください。** 変えるときは、この表と、関係する設計文書・実装の両方を直します。決定が実機にどう出ているかは[配備台帳](../operations/handover.md)、背景の検討は[最小クラウドとProvider](cloud.md)ほか同じ節の各ページにあります。


| 論点 | 決定 |
| --- | --- |
| APIの形 | 一般的なクラウドの語彙・状態遷移・フィールド名に揃えた自作 REST（OpenAPI が正本）。ワイヤ互換（署名方式や他社CLIの受け入れ）は作らない |
| 認証 | ブラウザは Authentik の OIDC。機械は、ポータルで発行するアクセスキーを `Authorization: Bearer sca_<keyid>.<secret>` で送る |
| アクセスキーの発行 | **ポータルのログインからだけ。** アクセスキーで別のアクセスキーは作れない（漏れたキーが複製を作って居座れないように）。1アカウント5本まで。削除は行を残して無効化 |
| テナント | Authentik ユーザー1人 = 1アカウント |
| VM の見え方と権限 | **クラウドのVMは全員が見られる**（所有者名・イメージ・リソース・状態）。1台のホストを分け合うので、誰が何を動かしているか分からないと容量の判断ができないため。ただし**操作できるのは所有者と `admins` だけ**（他人のVMへの電源操作・削除は 403）。他人の `client_token` は返さない。`user_data` は一覧に出さない |
| VM の大きさ | **自由入力**。`vcpus`・`memory_mib`・`memory_min_mib`・`ballooning`・`root_disk_gib` を直接指定する。`instance_type`（`flavors.yaml` の名前）は**任意の近道**で、指定すると値が埋まるだけ。1つでも数値を上書きしたらその型名は外れる（カスタム扱い） |
| ディスクの置き場 | **`disk_tier`（`ssd`＝既定 / `hdd`）で選ぶ。** プール名（`local-lvm` / `bulk-disks`）はAPIに出さず、`site.yaml` の `vm_disks` / `vm_disks_hdd` が対応を決める。インスタンスのroot（WindowsのEFI/TPM含む）とボリュームの両方で指定でき、**作成後は変えられない**。HDD未設定のデプロイは400。HDDの使用率チェックはファイルシステム全体（バックアップ・メディア含む）で行う |
| バルーニング | **VMごとに選べる。** `ballooning: false` なら固定メモリ（Proxmox の `balloon=0`）。`true` のとき `memory_min_mib` が回収の下限で、省略すると上限の 1/4（最低 512MiB） |
| 大きさの変更 | `PATCH /v1/instances/{id}`、**`admins` だけ**。vCPU・メモリ・バルーニングは**停止中のみ**（Proxmox は次回起動時にしか反映しないので、動作中に変えると台帳と実物が食い違う）。ディスクは稼働中でも**拡大のみ**。変更後の大きさでクォータと空き容量を再検査する |
| イメージのアップロード経路 | **API を通した直接アップロードだけ。**`download-url`（URL から Proxmox に取りに行かせる）は `cloudapi@pve` に **403**、`upload` は `content=import` を受ける（どちらも実測）。**Proxmox はチャンク転送を 501 で拒否する**ので本文の長さを先に宣言する必要があり、**「一切溜めずに流す」は成立しない**。cloud-01 の実ディスク（`storage/uploads`）へ一旦書いて大きさを確定させ、そこから流す。**`/tmp` は tmpfs なので使えない**。**中身の検査は Proxmox が qemu-img で行う**ので、壊れたファイルは弾かれ、何も残らない |
| イメージの上限 | 1イメージ **12GiB**（`max_image_gib`、管理者が変更可、0 は無制限）。置き場（Proxmox のルートFS 約94GiB）と cloud-01 のディスク（空き約31GiB）の**両方**に同じ大きさが要るので、小さい方に合わせてある。加えて置き場の空き（`image_store_min_free_mib`）を必ず残す |
| イメージの削除 | 所有者と `admins`。**共有イメージは API から消せない**（Terraform の宣言物）。既にそのイメージから作った VM は無関係（作成時にディスクへ複製済み）。**作成中の VM がある間だけ**削除を断る |
| SSH鍵 | 公開鍵だけを保存する。**`user-data` には触らず、NoCloud の `meta-data` の `public-keys` で渡す**（`user-data` はシェルスクリプトでもよい自由書式なので、他人の文書を書き換えないため）。鍵の本文は**承認時に**インスタンスへ複製するので、直後に鍵ペアを消されても入れない VM は生まれない。鍵ペアを後から消しても既存の VM は動き続ける |
| Webコンソール | **noVNC 1.7.0 を同梱する**（`web/static/novnc/`、npm の sha512 と照合した tarball から `core/`・`vendor/`・`LICENSE.txt` を無改変で。MPL-2.0。出所と更新手順は同じ場所の `PROVENANCE.md`）。**CDN は使わない**。ビルド無しの ES モジュールとして読み、CSP の `script-src 'self'` に収まる |
| コンソールの経路 | ブラウザは WebSocket に `Authorization` を付けられず、`vncwebsocket` はそれを要求するので、**API が自分の `cloudapi@pve` トークンで中継する**。**WebSocket のライブラリは足さない**。ハンドシェイクだけ双方と行い、以後はフレームを解釈せずバイト列を双方向にコピーする（ブラウザのマスク付きフレームは Proxmox が期待する形、Proxmox の非マスクのフレームはブラウザが期待する形なので、そのまま正しい）。圧縮などの拡張はどちら側とも交渉しない |
| コンソールの手順と期限 | ①`POST /v1/instances/{id}/console`（所有者と管理者だけ、稼働中だけ）が**5分有効・アカウントに結び付いた URL** を返す。**この時点では Proxmox に何も頼まない**。②その**ページを開くたびに** Proxmox の新しいチケットと使い捨てパスワードを発行する（Proxmox の VNC プロキシは数秒しか WebSocket を待たないので、接続の直前まで遅らせる。再読み込みがそのまま再接続になる）。③WebSocket は**1回のページ表示につき1本だけ** |
| コンソールの防御 | **Cookie で認証された WebSocket は Origin が自サイトでなければ断る**（`CrossOriginProtection` は GET を見ないので、他サイトからのクロスサイト WebSocket 乗っ取りはここで止める）。アクセスキーは他サイトのページから送れないので Origin は問わない（CLI 用）。URL のトークンは**アクセスログに出さず**（`/console/{token}` と記録）、メモリ上も**ハッシュで持つ**。ページは `Cache-Control: no-store`（パスワードを含むため） |
| v1 の範囲 | VM + S3互換ストレージ（Garage）+ database（CloudNativePG）+ function（Knative）。4機能とも実装済み |
| VMの追加機能 | 追加ボリューム、セキュリティグループ。スナップショットとメタデータサービスは作らない |
| 運用機能 | クォータと空き容量検査、差分リコンサイラ、監査ログ。削除保護は作らない |
| Web UI | フルのセルフサービスポータル |
| イメージ | 利用者が API へ直接アップロード（他に道が無いことを実測で確認。下の「イメージのアップロード経路」） |
| user-data | 完全に自由（NoCloud seed ISO で渡す） |
| CLI | 作る |
| 置き場所 | API と管理DB（PostgreSQL）は専用VM `cloud-01`。コードは `cloud/`（`cloud/api` が Go、`cloud/openapi` が正本） |
| API の実装 | Go の標準 `net/http`（CSRF 対策は `http.CrossOriginProtection`）、`pgx`、`go-oidc`。**OpenAPI からのコード生成はしない。** エンドポイントが少ないうちは生成物の保守の方が重いので、Go のルート表と OpenAPI の一致をテスト（`routes_test.go`）で保証する |
| Terraform Provider 名 | `shakecloud_*` |
| 管理面の分離 | VLAN で分ける。**まず管理はタグなし（ネイティブVLAN）のまま、利用者VM（cloud）だけをタグ付きVLANに載せる。**切り替えは `network.yaml` の `vlan.cloud.vlan_id`（＋ `cloud.prefix`／range）を埋めるだけで行う。宣言と手順は [VLAN 分離への切替](../operations/vlan.md) |
| Authentik | **core-01 に置く。** 当初は専用の identity VM（110）に構築したが、2026-10-03 に core-01 へ統合して110を廃止した（NetBox・入口と同居。互いに依存しているので分けても止まる範囲が変わらない。[配置と命名の再編](placement-naming.md)） |
| Authentik の `sub` | `user_uuid`。プロバイダを作り直しても変わらないため |
| 知らない `sub` と既知のメール | ログインを拒否する（`AccountConflict`）。別アカウントを黙って作ると、その人のリソースが2つに分かれるため |
| ポータルの入口 | `https://cloud.apextox.dpdns.org`（OIDC の戻り先は `/auth/callback`） |
| ~~HTTPS の入口（各ホストに置く）~~ | **2026-10-02 に撤回した。** 各ホストの Caddy が自分で Let's Encrypt の証明書を取る形にしていたが、Cloudflare の DNS 編集トークンが5台に載るのが代償として重すぎた。置き換えは下の「HTTPSの入口」 |
| ドメイン | **`apextox.dpdns.org`**（DigitalPlat の無料ドメイン。DNS は Cloudflare に委任）。**インターネットには公開しない。** グローバルIPも使わず、HTTPS の証明書を DNS-01 で取るためにだけ使う。`home.arpa` と自前CAにしなかったのは、全端末へ CA を登録する手間と、スマホアプリが自前CAを信用しない問題を避けるため |
| OIDC クライアントの秘密値 | **SOPS へ複製しない。** 正本は core-01（旧 identity VM）の `oidc-cloud.json` で、`cloud.yml` が配備のたびに直接写す。2か所に持つと、作り直したときに食い違うため |
| ブートストラップ管理キー | cloud-01 のファイルが正本。起動時に DB をファイルへ合わせる。API から削除したキーは再起動しても復活しない。**2026-09-11 に無効化した**（以後はポータルでログインして発行するアクセスキーを使う。緊急時は `rotate-bootstrap-key` で作り直す） |
| インスタンスの上限 | **既定値は `platform/terraform/cloud.yaml`、変更は `admins` が実行中に行う**（`PUT /v1/limits` かポータルの「上限」）。管理DBには管理者が変えた項目だけを入れ、読むたびに既定値と重ねる（同じ事実を2か所に持たない）。既定は1アカウント 8台・32vCPU・32GiB・ディスク計 1000GiB・ボリューム16本/計 3072GiB、クラウド全体のメモリ枠 **48GiB**（2026-10-03 に 32→48GiB。アプリと開発VMをクラウドVMへ寄せる再編で最大約43GiBを割り当てるため）、ノードに 4GiB 残す、ディスク実使用率 85%。**0 は無制限。**停止中も数える |
| 上限とホストの保護の関係 | **上限の合計が物理メモリを超えることを許す**（バルーニング前提）。物理を見ているのは「ノードの `available` が指定量残るか」と「ディスクの実使用率」の2つだけで、これは上限を無制限にしても残る。この2つを 0 にすると基盤VMごと倒せる。[配分と実測](operations.md#measured-budget) |
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
| ドキュメントサイト | **apps-01 に置いて LAN に公開**（`https://docs.apextox.dpdns.org`。2026-10-03 に services-01 から移設）。Git の `docs/` が正本で、Nextcloud からは編集しない |
| game1（VMID 100） | 2026-09-11 に `cloud` プールへ移し、クラウドAPIが `shunyazhiyuan97`（ゲームサーバ開発者）のインスタンスとして引き取った。VMID 100 は `pools.yaml` の `reserved_vmids` で引き続き確保（public-edge には使わない） |
| 回線とポート | **MAP-E（v6プラス・JPNE）。CGNATではない。** ポート開放は可能だが**割り当てられた240個に限られ、80/443 は使えない**（2026-09-20の実測。[N06](../development/N06-router.md)）。**家庭回線に 80/443 の着信を開ける設計は採らない。** WireGuard など割当ポートで済むものは公開できる |
| 公開サイトの出し方 | **宅外の中継機を経由して出す（2026-10-05）。** 公開サイト（`ruruthegeek.dpdns.org` の4サイトとAlexaスキル）は `web-01` で動かし、Cloudflare → 宅外の中継機 → **tailnet** → `web-01` の順で届かせる。家庭回線には着信を開けない（上の「回線とポート」）。中継機には LAN のサブネットルートを持たせず、`web-01` 側はセキュリティグループとゲスト内 nftables で自宅LANへ戻れないようにする。**インターネットへ出すのはこの1台だけ**で、基盤VMと同じ信頼区分には置かない（[公開サイト](../operations/web.md)・[信頼境界](security.md)） |
| 公開サイトのゾーン | **ホームラボ（`apextox.dpdns.org`）と公開（`ruruthegeek.dpdns.org`）でゾーンを分ける。** 前者は公開DNSに内部IPを書くだけで外からは届かない。混ぜると「この名前は外から見えるのか」が読めなくなる |
| イメージの固定 | **レジストリから取るイメージは digest で固定し、`compose.lock.yaml` をリポジトリに置く（正本はリポジトリ側）。** 配備先だけで `pull` し直さない。これが無いと、再配備のたびに `:latest` の中身が変わって「何が動いているか」をGitから追えない。`tests/test_image_locks.py` が全スタックの lock と compose の対応を検査する。自作Botは GitHub Actions が `main` のマージで出す GHCR の固定タグを使い、配備先ではビルドしない |
| 自分で更新するVM | **公開サイト（web-01）とBotは、VMが自分で `main` を見て更新する。** 5分ごとのタイマーで、Ansible を流し直したのと同じ結果になる。外部のCDから配備先へ入る鍵を持たせずに済むため。**設定・秘密値の変更はタイマーでは入らない**ので、そのときは Ansible を流す |
| Composeスタックの配備 | **共通ロール `compose_stack` に寄せる。** スタックごとにタスクを書かず、「ファイルを置く → `.env` を書く → `manage.py init` → `manage.py up`」の流れを1か所に持つ。各スタックは `manage.py` の作法（`init` は秘密値と保存先を作る、`up` は起動して healthcheck を待つ）に合わせる。`--check` で事前確認できる |
| 家庭内ルータ | **K11 上の OpenWrt VM `router-01` として自作する。** 市販ルータ（Aterm）はAPモードのWi-Fi専用機へ降格。設定は Git（`platform/openwrt/`）が正本で、実機へ `uci` で入れた変更はイメージに焼くまで再作成で消える。**代償としてK11が落ちると家中のネットが落ちる**（[障害モード](failure-modes.md)） |
| ルータ管理画面の認証 | **LuCI にはSSOを付けない。** ルータは復旧経路なので、identity が止まっていても開ける必要がある。認証は LuCI 自身の root パスワード。AdGuard の管理画面は復旧に必須でないので Forward Auth を通す |
| VLAN分離の前提 | **アンマネージドスイッチ（TL-SG605）ではVLANを設定できない。** N03 はマネージドスイッチの調達が前提条件で、機器購入なしには完了できない |
| メール送信 | **外部SMTPリレーを各アプリから直接使う。Postfix（ローカルMTA）は置かない。** 家庭回線のIPからの直接MX配送は PTR・SPF/DKIM・ポート25遮断で拒否・迷惑メール扱いになりやすいため。**2026-09-12 に Gmail（`shake.notify@gmail.com`、アプリパスワード）を設定済み・実送信確認済み。** SMTP の資格情報は `platform/sops/smtp.sops.yaml` に置き、identity 配備で `.env` へ写す。招待メールは `stacks/identity/invitations.py` が送る（[SMTPとメール送信](../operations/smtp.md)） |
| Kubernetesの稼働 | **メモリが足りるときだけ動かす。常時起動は仕様にしない（2026-10-02）。** cp と worker-01 で11GiB以上を固定で使うため、普段は停止しておき、database（CNPG）・function（Knative）・AWX を使うときに `tools/k8s up` で起こす。停止中はこれらの機能が使えないのが正常で、障害ではない。常時動かす必要があるものは k8s に載せない（[Kubernetes](../operations/kubernetes.md#起動と停止)） |
| ポケモン系のPostgreSQLの置き場所 | **apps-01 に独立Composeで置く（2026-10-04）。** 以前は game1 に同居と決めていたが、常時つなぐBotがあり、game1 は構成管理・バックアップの外にある。約50MBのDBに専用VMは割かず、常時稼働でないCNPGにも載せない（[pkdb](../operations/pkdb.md)） |
| 生存確認の持ち方 | **dead man's switch は監視ノード（monitor-01）にだけ置く。それ以外のサービスの生死は監視（Prometheus・blackbox）で見る（2026-10-02）。** 各コンテナに `healthcheck` を揃えることは目標にしない。新しいサービスを足すときは、コンテナの `healthcheck` ではなく `stacks/monitoring/prometheus/blackbox-targets.yml` へ probe を足す（`tests/test_monitoring_stack.py` が `dns.yaml` との一致を検査する）。起動順の待ち合わせに要る `healthcheck`（DB→アプリ）は残してよい（[監視](../operations/monitoring.md)） |
| HTTPSの入口 | **公開の証明書と Cloudflare のDNS編集トークンは、入口の1台（core-01。決定時の名前は services-01）だけが持つ（2026-10-02。実機への切替は1台ずつ）。** 各ホストの Caddy は残し、入口との間は各ホストの内部CAの証明書で暗号化する。入口から各アプリへ平文で直接つなぐ形にしなかったのは、利用者VMと同じL2にSSOの通信を平文で流すことになり、`Remote-User` を信じるアプリの認証が各VMのファイアウォール設定だけに依存するため。入口が止まると全サービスに入れなくなるが、物理ホストが1台なので可用性は変わらない（[HTTPSの入口を1台にまとめる](../operations/edge.md)） |
| 配置と命名 | **基盤（Terraformで直接作る）は router-01・core-01（Authentik・NetBox・入口）・cloud-01（クラウドAPI・Garage）・monitor-01・k8s。それ以外のアプリはクラウドVM（media-01・apps-01・web-01・game-01 と開発VM）に置く（2026-10-03 に合意、2026-10-04 までに移行完了）。** 基準は「クラウドAPIが動くため、または壊れたときに直すために要るか」。Tailscale はルータへ移す。ホスト名は `<役割>-<2桁>`、Compose名・配備先・スタックはアプリ名で統一する。開発VM（dev-01・dev-02・android-01・win-01）もクラウドVMにし、用途「開発」としてまとめる。クラウドVMの所有者は game-01 と dev-01 が `shunyazhiyuan97`、ほかは `rurutheGeek`（[配置と命名の再編](placement-naming.md)） |
