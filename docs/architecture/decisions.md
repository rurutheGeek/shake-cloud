---
title: 決定ログ
updated: 2026-09-19
section: 設計
audience: 管理者・開発者
tags:
  - design
  - decisions
---

# 決定ログ

> **更新日** 2026-09-19 ・ **区分** 設計 ・ **読む人** 管理者・開発者

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
| Authentik | identity VM（110）に構築した |
| Authentik の `sub` | `user_uuid`。プロバイダを作り直しても変わらないため |
| 知らない `sub` と既知のメール | ログインを拒否する（`AccountConflict`）。別アカウントを黙って作ると、その人のリソースが2つに分かれるため |
| ポータルの入口 | `https://cloud.apextox.dpdns.org`（OIDC の戻り先は `/auth/callback`） |
| HTTPS の入口 | 各ホストの Caddy（`stacks/tls-proxy/`）が Let's Encrypt の証明書を DNS-01 で取り、同じホストの 127.0.0.1 のサービスへ中継する。1台に集めず各ホストに置くのは、認証基盤（identity）を他のホストの障害に巻き込まないため。代わりに Cloudflare の DNS トークンが各ホストに載る |
| ドメイン | **`apextox.dpdns.org`**（DigitalPlat の無料ドメイン。DNS は Cloudflare に委任）。**インターネットには公開しない。** グローバルIPも使わず、HTTPS の証明書を DNS-01 で取るためにだけ使う。`home.arpa` と自前CAにしなかったのは、全端末へ CA を登録する手間と、スマホアプリが自前CAを信用しない問題を避けるため |
| OIDC クライアントの秘密値 | **SOPS へ複製しない。** 正本は identity VM の `oidc-cloud.json` で、`cloud.yml` が配備のたびに直接写す。2か所に持つと、作り直したときに食い違うため |
| ブートストラップ管理キー | cloud-01 のファイルが正本。起動時に DB をファイルへ合わせる。API から削除したキーは再起動しても復活しない。**2026-09-11 に無効化した**（以後はポータルでログインして発行するアクセスキーを使う。緊急時は `rotate-bootstrap-key` で作り直す） |
| インスタンスの上限 | **既定値は `platform/terraform/cloud.yaml`、変更は `admins` が実行中に行う**（`PUT /v1/limits` かポータルの「上限」）。管理DBには管理者が変えた項目だけを入れ、読むたびに既定値と重ねる（同じ事実を2か所に持たない）。既定は1アカウント 8台・32vCPU・32GiB・ディスク計 1000GiB、クラウド全体のメモリ枠 32GiB、ノードに 4GiB 残す、ディスク実使用率 85%。**0 は無制限。**停止中も数える |
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
| ドキュメントサイト | services-01 に置いて LAN に公開（`https://docs.apextox.dpdns.org`）。Git の `docs/` が正本で、Nextcloudからは編集しない。今回の方針ではservices-01に維持する。家電（H01）は2026-09-12に配備済みで、Authentik SSO・Eufy・SwitchBot Cloud を設定済み。VPNの同居は未配備 |
| game1（VMID 100） | 2026-09-11 に `cloud` プールへ移し、クラウドAPIが `shunyazhiyuan97`（ゲームサーバ開発者）のインスタンスとして引き取った。VMID 100 は `pools.yaml` の `reserved_vmids` で引き続き確保（public-edge には使わない） |
| メール送信 | **外部SMTPリレーを各アプリから直接使う。Postfix（ローカルMTA）は置かない。** 家庭回線のIPからの直接MX配送は PTR・SPF/DKIM・ポート25遮断で拒否・迷惑メール扱いになりやすいため。**2026-09-12 に Gmail（`shake.notify@gmail.com`、アプリパスワード）を設定済み・実送信確認済み。** SMTP の資格情報は `platform/sops/smtp.sops.yaml` に置き、identity 配備で `.env` へ写す。招待メールは `stacks/identity/invitations.py` が送る（[SMTPとメール送信](../operations/smtp.md)） |
