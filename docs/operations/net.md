---
title: net-01（Tailscale subnet router）
updated: 2026-10-01
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
---

# net-01（Tailscale subnet router）

> **更新日** 2026-10-01 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: Tailscaleへ参加済み（apply・再plan・再実行とも確認済み）。ルート承認とtailnet DNS（AdGuard Home）は2026-10-01に適用済み。宅外端末での実機検証が未了。

`net-01` は、宅外から管理LAN（`192.168.10.0/24`）へ戻るための Tailscale の
subnet router です。[N02](../development/N02-tailscale.md) の復旧経路を、
ラズパイではなく cloud VM で実現したもの。**Proxmox ホスト（K11）が落ちれば
この VM も落ちる**ため、カバーするのは VM 単位の故障までです。真の
アウトオブバンドが必要になったら、既存ルーターの VPN 機能か別ハードを
検討します（[VPN比較](../architecture/vpn.md)）。

## 実体

| 項目 | 値 |
| --- | --- |
| インスタンス | `i-88933be43f442c6f4`（`cloud` プール、`ruruthegeek`） |
| IP / ホスト名 | `192.168.10.103` / `net-01` |
| サイズ | 1vCPU / 512MiB / OS10GiB。データディスクなし |
| tailnet アドレス | `100.91.7.69`（`net-01.taild66374.ts.net`） |
| 宣言 | `platform/terraform/services/net`（apply済み、再 plan は No changes） |
| 構成 | `platform/ansible/net.yml` + `platform/ansible/roles/tailscale`（再実行は変更ゼロ）。管理画面側は `tools/tailscale-net.py` |
| グループ | `vpn`（`cloud-inventory.yml` の `i-88933be43f442c6f4`） |
| 広告ルート | `192.168.10.0/24`（`site.yaml` の `network.prefix` から取得）。承認済み（2026-10-01） |
| tailnet DNS | `192.168.10.1`（AdGuard Home）を唯一の global nameserver にし、`overrideLocalDNS` を有効化（MagicDNS は維持） |

SG は LAN から 22/tcp だけ。Tailscale の通信は端末側からの発信と中継で
成立するため、受信ポートの開放は不要です。

## 配備手順

1. Tailscale の管理画面 → Settings → Keys → Generate auth key
   - Pre-approved: on、Ephemeral: off、Reusable: 端末を作り直す前提なら on
   - Tags: `tag:vpn` を推奨（**タグ付き端末はキー期限が無効**。ACL に
     `tagOwners` の定義が必要）
   - **auth key の期限（最大90日）は端末のキー期限ではない。** 登録済みの
     端末は auth key が期限切れになっても接続を続ける。期限が要るのは
     再登録（VMの作り直し・`tailscale logout`）のときだけ。
   - タグなしで登録した場合は、参加後に管理画面で `net-01` の
     **key expiry を Disable** にする（既定は180日）。
2. `platform/sops/tailscale.sops.yaml` を作る（`.example` の手順どおり）
3. 実行する。Tailscale の認証キーと、クラウドinventory用のアクセスキーの
   **2つ**を、そのプロセスの環境変数としてだけ渡す（ファイルへ書かない）:

   ```bash
   TAILSCALE_AUTH_KEY=$(sops --decrypt --extract '["TAILSCALE_AUTH_KEY"]' platform/sops/tailscale.sops.yaml) \
   SHAKECLOUD_ACCESS_KEY=$(sops --decrypt --extract '["SHAKECLOUD_ACCESS_KEY"]' platform/sops/services.sops.yaml) \
   ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve \
   .venv/bin/ansible-playbook -i platform/ansible/inventory.cloud.py platform/ansible/net.yml
   ```

4. `tools/tailscale-net.py apply` で、ルート承認と tailnet DNS を宣言どおりにする
   （2026-10-01 適用済み）。管理画面のクリックではなく、差分を確認してから書く:

   ```bash
   TAILSCALE_API_TOKEN=$(sops --decrypt --extract '["TAILSCALE_API_TOKEN"]' platform/sops/tailscale.sops.yaml) \
   .venv/bin/python tools/tailscale-net.py apply
   ```

   API トークンは管理画面 → Settings → Keys → API access tokens で発行し、
   `platform/sops/tailscale.sops.yaml` へ入れる（期限は最大90日。切れたら再発行）。
   `status` は読むだけで、差分とポリシーの要約を出す。
5. ACL で管理端末から管理LANへ許可する。**既定の allow-all の間は作業不要**
   （2026-10-01 時点で既定）。制限を入れるときは、tailnet DNS を使う端末が
   `192.168.10.1:53` へ届くようにする（例。未了）:

   ```json
   {"action": "accept", "src": ["group:admins"], "dst": ["192.168.10.0/24:*"]}
   ```

   `tag:vpn` を使う場合は `tagOwners` に `"tag:vpn": ["<管理者アカウント>"]` を足す。
6. 参加に使った auth key を失効させる（端末は切断されない。**未了**）

## tailnet DNS

- 広告ブロックを宅内・宅外で揃えるため、tailnet の global nameserver は
  **AdGuard Home（`192.168.10.1`）1つだけ**にし、`overrideLocalDNS` を有効にする。
  Tailscale 接続中の端末は、宅内 Wi-Fi でもモバイル回線でもこの resolver を使う
  （MagicDNS は有効のまま。`*.ts.net` は Tailscale が内部で解決する）。
- **split DNS は使わない。** AdGuard は `*.apextox.dpdns.org` も上流 DoH で
  引けるため、サフィックスごとの振り分けが要らない。
- 2026-10-01 より前は global nameserver が未設定のまま MagicDNS だけが有効で、
  `100.100.100.100` が全名前に SERVFAIL を返していた。スマホで Tailscale を
  繋ぐと「インターネットが繋がらない」ように見えた原因はこれ。
- AdGuard（router-01）か net-01 が停止すると、Tailscale 接続中の端末は
  名前解決できなくなる。予備 resolver を併記すると広告ブロックが漏れるため、
  あえて1つにしている。復旧時は IP 直打ちや `/etc/hosts` を使う。

## 再実行とローテーション

- 再実行は冪等（2026-09-14 実測: `changed=0`）。`tailscale debug prefs` と
  望む設定を比べ、変わるときだけ `tailscale up` を実行します。
- 認証キーのローテーション: 管理画面で旧キーを失効 → 新しいキーを SOPS へ
  入れて再実行（`tailscale up` が再認証）。
- 端末の失効: 管理画面で `net-01` を Remove。VM を作り直すと tailnet 上は
  別端末になるため、古い端末を残さない。
- VM の作り直し: `tools/tf services/net destroy` → `apply`。IP と
  インスタンスIDが変わるので `cloud-inventory.yml` を直す。

## 検証（N02の合格条件）

**一部完了（2026-10-01）。** dev-b（`accept-dns` 有効）で次を実測した。

- tailnet resolver が `192.168.10.1` になる（`tailscale dns status`）
- `100.100.100.100` が公開名（`example.com`）と内部名
  （`pve.apextox.dpdns.org` → `192.168.10.10`）を解決する
- `googleads.g.doubleclick.net` が AdGuard により `0.0.0.0` へ遮断される
- MagicDNS 名（`net-01.taild66374.ts.net` → `100.91.7.69`）が引ける
- ルート `192.168.10.0/24` が net-01 で承認されている

**未了:** 宅外（モバイル回線）のスマホ実機で、通常・services-01 停止・K11 停止の
各条件を確認する。許可外利用者が管理レンジへ到達できないこと（ACL）は、
ポリシーに制限を入れるときに確認する。

## 確認コマンド

```bash
terraform -chdir=platform/terraform/services/net fmt -check
terraform -chdir=platform/terraform/services/net validate   # dev override が必要
TAILSCALE_API_TOKEN=$(sops --decrypt --extract '["TAILSCALE_API_TOKEN"]' platform/sops/tailscale.sops.yaml) \
  .venv/bin/python tools/tailscale-net.py status
host example.com 100.100.100.100
host pve.apextox.dpdns.org 100.100.100.100
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.103 \
  'sudo tailscale status --json | python3 -m json.tool | head -20'
```
