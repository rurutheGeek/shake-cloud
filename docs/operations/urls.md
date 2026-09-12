# 接続先一覧（URL・アドレス）

更新日: 2026-09-12。**サービスを探すときはまずこのページを見てください。** 名前の正本は `platform/terraform/dns.yaml`、実機のVMとIPは[配備台帳](handover.md)です。

## 新しい基盤（`*.apextox.dpdns.org`・家庭内LANから）

`apextox.dpdns.org` は Cloudflare の公開 DNS に**内部IPをそのまま**書いています。名前は外からも引けますが、**インターネットには公開していません**（[ネットワーク・公開範囲・SSO](../architecture/network-auth.md)）。

| サービス | URL | 中身 | 誰が使う |
| --- | --- | --- | --- |
| クラウド | <https://cloud.apextox.dpdns.org> | ポータルと API（cloud-01。API の `:8080` は 127.0.0.1） | `users` / `admins` |
| クラウドAPI | `/v1/...`（上と同じホスト） | JSON API。[OpenAPI](../../cloud/openapi/shakecloud.yaml) が正本 | CLI・Terraform・アプリ |
| 共通ログイン | <https://auth.apextox.dpdns.org> | Authentik（identity VM。`:9000`・`:9443` は 127.0.0.1） | 全員 |
| 招待リンク | `https://auth.apextox.dpdns.org/if/flow/cloud-invitation-enrollment/?itoken=…` | 招待登録（1回限り・24時間） | 招待された人 |
| AWX | <https://awx.apextox.dpdns.org> | Ansible 実行基盤（Kubernetes・Let's Encrypt） | 管理者 |
| NetBox | <https://netbox.apextox.dpdns.org> | 台帳（IP・VM）。直アクセス `http://192.168.10.200:8000` | 管理者 |
| ドキュメント | <https://docs.apextox.dpdns.org> | このサイト（直アクセス `http://192.168.10.200:8090`） | 全員 |
| Proxmox | <https://pve.apextox.dpdns.org:8006> | 仮想化ホストの管理画面。IP 直は `https://192.168.10.126:8006` | 管理者 |

### クラウドの中身（API・k8s）

| もの | アドレス | 備考 |
| --- | --- | --- |
| クラウドポータルのログイン | `https://cloud.apextox.dpdns.org/auth/login` | Authentik へ転送 |
| OIDC redirect | `https://cloud.apextox.dpdns.org/auth/callback` | 完全一致 |
| 健全性 | `https://cloud.apextox.dpdns.org/healthz` | 200 で正常 |
| OIDC issuer | `https://auth.apextox.dpdns.org/application/o/cloud/` | クラウドAPIが読む |
| Kubernetes API | `https://192.168.10.207:6443` | kubeconfig は dev-b とクラスタ内 |
| Cilium Ingress | `192.168.10.241` | AWX の入口 |
| Kourier（関数） | `192.168.10.240` | Knative の入口 |
| 関数 URL | `https://<name>.functions.k8s.apextox.dpdns.org` | ワイルドカード証明書 |
| DB（クラウドが作る） | `db-<id>-rw.databases.svc:5432` | **クラスタ内からだけ**。資格情報は API/ポータルで取得 |
| MetalLB レンジ | `192.168.10.240–249` | 予約。管理レンジ `.201–239` の外 |

## ストレージ（Garage / S3）

| もの | アドレス | 備考 |
| --- | --- | --- |
| S3 API | `http://192.168.10.206:3900` | クライアントに渡す `s3_endpoint` |
| 管理 API | `http://192.168.10.206:3903` | Bearer トークン。クラウドAPIが使う |
| リージョン | `garage` | |

## VM・SSH

| 名前 | アドレス | 用途 |
| --- | --- | --- |
| Proxmox ホスト | `root@192.168.10.126` | 仮想化ホスト |
| services-01 | `debian@192.168.10.200` | NetBox・ドキュメント |
| identity | `debian@192.168.10.204` | Authentik |
| cloud-01 | `debian@192.168.10.205` | クラウドAPI・管理DB |
| storage-s3 | `192.168.10.206` | Garage |
| k8s-cp-01 | `debian@192.168.10.207` | Kubernetes control plane |
| k8s-worker-01 | `192.168.10.209` | AWX・CNPG・Knative |
| k8s-worker-02 | `192.168.10.208` | 予備（停止中） |
| dev-a / dev-b | `debian@192.168.10.202` / `.203` | 開発VM |
| probe-01 | `192.168.10.201` | 検証用 |
| game1 | `192.168.10.127` | ゲーム（クラウド管理下） |

VM の正本は[配備台帳](handover.md)と `platform/terraform/hosts.yaml` です。

## 旧メディアスタック（SSH トンネル経由）

**`localhost` の URL は SSH トンネルを張ったときだけ使えます**（[接続手順](hub.md)）。ポート一覧は `hub.md` を参照してください。`login.localhost:9443` は**旧 Authentik**で、新しい `auth.apextox.dpdns.org` とは別物です。

| サービス | URL | 用途 |
| --- | --- | --- |
| Homarr | `http://localhost:7575` | ハブ |
| Nextcloud | `https://nextcloud.localhost:8443` | ファイル |
| Kavita | `https://kavita.localhost:5443` | 書籍 |
| Navidrome | `http://localhost:4533` | 音楽 |
| MeTube | `http://localhost:8081` | 音声取り込み |
| Vaultwarden | `https://vault.localhost:8243` | パスワード |
| 旧 Authentik | `https://login.localhost:9443` | 旧メディアのSSO |

## 外部サービス

| もの | アドレス | 用途 |
| --- | --- | --- |
| Gmail SMTP | `smtp.gmail.com:587`（`shake.notify@gmail.com`） | 招待・パスワード再設定メール |
| Let's Encrypt / ACME | `admin@apextox.dpdns.org`（連絡先） | 証明書 |
| Cloudflare | DNS ゾーン `apextox.dpdns.org` | A レコードは内部IP |
| GitHub | `github.com/rurutheGeek/shake-cloud`（`main`） | Flux の同期元 |

## 注意

- **LAN の外から使うには VPN が要ります。** まだ構築していません（[VPN比較](../architecture/vpn.md)）。
- Proxmox の IP 直アクセスは証明書の名前が合わないため警告が出ます。`pve.apextox.dpdns.org` を使ってください。
- クラウドのドメインは変えると**パスキーの登録をやり直し**になります（登録したホスト名に結び付くため）。
