# net-01（Tailscale subnet router）

更新日: 2026-09-14。状態: **Tailscaleへ参加済み（apply・再plan・再実行とも確認済み）。管理画面でのルート承認・ACL・宅外検証が未了。**

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
| 構成 | `platform/ansible/net.yml` + `platform/ansible/roles/tailscale`（再実行は変更ゼロ） |
| グループ | `vpn`（`cloud-inventory.yml` の `i-88933be43f442c6f4`） |
| 広告ルート | `192.168.10.0/24`（`site.yaml` の `network.prefix` から取得） |

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

4. 管理画面の Machines で `net-01` の Subnet routes に `192.168.10.0/24` を**承認**（未了）
5. ACL で管理端末から管理LANへ許可する（例。未了）:

   ```json
   {"action": "accept", "src": ["group:admins"], "dst": ["192.168.10.0/24:*"]}
   ```

   `tag:vpn` を使う場合は `tagOwners` に `"tag:vpn": ["<管理者アカウント>"]` を足す。
6. 参加に使った auth key を失効させる（端末は切断されない。**未了**）

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

**未了。** ルート承認後、宅外端末から次を確認する。

- 通常状態で管理LANの名前に到達できる（`https://pve.apextox.dpdns.org` など）
- services-01 停止中でも Proxmox 管理へ入れる
- VPN 切替後に DNS が正しく解決される（split DNS の要否を含めて）
- 許可外利用者が管理レンジへ到達できない（ACL）

## 確認コマンド

```bash
terraform -chdir=platform/terraform/services/net fmt -check
terraform -chdir=platform/terraform/services/net validate   # dev override が必要
sops exec-env platform/sops/services.sops.yaml \
  '.venv/bin/ansible-inventory -i platform/ansible/inventory.cloud.py --graph'
ssh -i ~/.ssh/id_ed25519_pve debian@192.168.10.103 \
  'sudo tailscale status --json | python3 -m json.tool | head -20'
```
