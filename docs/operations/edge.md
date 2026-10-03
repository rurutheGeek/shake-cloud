---
title: HTTPSの入口を1台にまとめる
updated: 2026-10-02
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
---

# HTTPSの入口を1台にまとめる

> **更新日** 2026-10-02 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: コードは入っている。**実機への切替は未実施**（`dns.yaml` の `edge.backends` は空で、全ホストが従来どおり自分で証明書を取っている）。

公開の証明書（Let's Encrypt）と Cloudflare のDNS編集トークンを持つホストを、**入口の1台（services-01）だけ**にします。これまでは identity・cloud-01・media-01・services-01・monitor-01 の5台がそれぞれトークンを持ち、1台が侵害されるとゾーン全体のDNSを書き換えられる状態でした。

## しくみ

```text
端末 ──HTTPS（Let's Encrypt）──▶ 入口の Caddy（services-01）
                                    │  中継先の内部CAを確かめて HTTPS で中継
                                    ▼
                              各ホストの Caddy（内部CAの証明書・トークンなし）
                                    │  今までどおり Forward Auth・経路の振り分け
                                    ▼
                              127.0.0.1 のアプリ
```

- **名前はすべて入口を指す。** `20-dns` が、入口の後ろのホストの名前（`upstream` を持つレコード）を入口のアドレスへ向けます。
- **各ホストの Caddy は残す。** 認証（Forward Auth）、`Remote-User` の付け外し、パスの振り分けは今までどおり各ホストで行い、アプリは `127.0.0.1` に閉じたままです。入口は公開の証明書で受けて、暗号化して渡すだけです。
- **入口と各ホストの間も暗号化する。** 各ホストの Caddy は自分の内部CAで証明書を出し（`tls internal`）、入口はそのCAの証明書（`platform/ansible/files/backend-ca/<ホスト>.crt`）で相手を確かめます。LAN内を平文で流しません。
- **アプリには元の端末のアドレスを渡す。** 各ホストの Caddy は入口だけを信頼し（`trusted_proxies`）、`X-Forwarded-For` を元の端末のアドレスへ付け直します。アプリ側の設定は変えません。
- **Forward Auth が輪にならないようにする。** identity を入口の後ろへ移すと、`auth` の名前は入口を指します。入口は `/outpost.goauthentik.io/*` を identity へ直接渡し、入口自身の Forward Auth も identity へ直接つなぎます。

宣言は `platform/terraform/dns.yaml` の `edge` です。

```yaml
edge:
  host: services-01
  backends: []        # 入口の後ろへ移し終えたホスト。1台ずつ足す
```

## トークンが残る場所

入口にまとめても、Cloudflare のDNS編集トークンは次の3か所に残ります。

| 場所 | 理由 |
| --- | --- |
| 入口（services-01）の Caddy | 全サービスの証明書を取る |
| Proxmox ホスト（ACMEプラグイン） | `pve.apextox.dpdns.org:8006` は復旧経路なので、入口を通さず自分で証明書を持つ |
| Kubernetes の cert-manager | `*.functions.k8s` のワイルドカード証明書。クラスタは使うときだけ動かす |

## 1台ずつ移す

**前提**: インベントリが NetBox へ統一済みであること（[Ansibleのインベントリ](services.md#inventory)）。入口は中継先のアドレスを、中継先は入口のアドレスを、インベントリから引きます。

移す順は **monitor-01 → media-01 → cloud-01 → identity** を勧めます。identity は全サイトのSSOに関わるので最後にします。

1台（例: `monitor-01`）につき次の順です。**手順2から4のあいだ、そのホストの名前は数分つながりません。**

1. `dns.yaml` の `edge.backends` に `monitor-01` を足す
2. そのホストを配備する（内部CAの証明書に切り替わり、CAの証明書が `platform/ansible/files/backend-ca/monitor-01.crt` へ書かれる。Cloudflare のトークンはホストから消える）

    ```bash
    sops exec-env platform/sops/netbox-inventory.sops.yaml \
      '.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/monitoring.yml'
    ```

3. 入口を配備する（入口がその名前の証明書を取り、中継を始める。名前が入口を指す前でも、入口のアドレスへ直接聞いて中継を確かめる）

    ```bash
    sops exec-env platform/sops/netbox-inventory.sops.yaml \
      '.venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/edge.yml'
    ```

4. 名前を入口へ向ける

    ```bash
    tools/tf 20-dns apply
    ```

5. ブラウザーと[監視](monitoring.md)（blackbox）で確かめ、`dns.yaml` と `backend-ca/monitor-01.crt` をコミットする

各ホストの配備に使うPlaybookは、monitor-01 が `monitoring.yml`、media-01 が `media-tls.yml`、cloud-01 が `cloud.yml`、identity が `identity.yml` です。

## 戻す

`edge.backends` からそのホストを外し、そのホストを配備 → 入口を配備 → `tools/tf 20-dns apply` の順に流します。ホストは Cloudflare のトークンを受け取り直し、自分で証明書を取ります。

## 困ったとき

| 症状 | 原因と対処 |
| --- | --- |
| 入口の配備が「backend is not in this inventory or …crt is missing」で止まる | 中継先を先に配備していない、または `seed.ini` で流した。中継先を配備してから、NetBox のインベントリで流す |
| 入口経由が 502 | 入口が中継先のCAを確かめられない（ホストを作り直してCAが変わった）、または中継先のアプリが落ちている。前者はそのホストを配備し直して `backend-ca/<ホスト>.crt` を更新し、入口を配備し直す |
| 中継先のアプリから見た接続元が全部入口のアドレスになる | そのホストの Caddy が入口を信頼していない。`edge.backends` にホストが入った状態で配備し直す |
| SSOの画面へ飛ばず、同じ名前へ何度も転送される | identity を入口の後ろへ移したのに、入口を配備し直していない（入口が `/outpost.goauthentik.io/*` を identity へ渡す設定を持っていない） |
| 入口（services-01）が止まると全サービスに入れない | 入口は1台なので仕様。Proxmox（`pve.apextox.dpdns.org:8006`）とルータ（LAN内の `192.168.10.1`）は入口を通らないので、そこから復旧する |

## 関連

- [接続先一覧](../reference/urls.md)
- [ネットワーク・公開範囲・SSO](../architecture/network-auth.md)
- [確認と、はまりどころ](verify.md)
