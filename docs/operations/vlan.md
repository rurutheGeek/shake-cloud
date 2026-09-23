---
title: VLAN 分離への切替
updated: 2026-09-12
section: 運用手順
audience: 管理者
tags:
  - ops
  - network
---

# VLAN 分離への切替

> **更新日** 2026-09-12 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 宣言と手順を用意済み。実機の切替は未実施（物理スイッチ/ルータの作業と、Proxmox ホストの bridge 変更を含む）。

管理面（Proxmox・API・認証・台帳・Garage）と、利用者VMを VLAN で分けます。**この文書は切替の手順書で、実機はまだ触っていません。**

## 方式: 管理はタグなしのまま、利用者VMだけ VLAN に載せる

VLAN を切るとき、**ホストと基盤VMの管理IPは今のタグなし（ネイティブVLAN）のまま**にし、**利用者VM（`cloud` プール）だけをタグ付き VLAN** に載せます。こうすると:

- Proxmox ホスト・identity・cloud-01・services-01・storage-s3 の到達性を変えずに済む（切替で一番危険な「管理を失う」を避けられる）。
- 分離したい対象は利用者VMなので、そこだけタグを付ければ目的を達成できる。
- `network.yaml` の `vlan.management.vlan_id` は **null のまま**、`vlan.cloud.vlan_id` にだけ値を入れる。

4区分（管理・内部・開発・公開入口）まで一気に分けるのは後段です。まず cloud だけを分けます。

## 前提（すべて揃うまで切替しない）

- ルータ/スイッチで VLAN を作れること。切替後も管理端末からホスト・基盤VMへ届くこと。
- **Proxmox ホストの物理コンソールか IPMI を手元に用意する。** bridge を変更するので、誤ると SSH も API も届かなくなる。
- 利用者VM用の **VLAN ID** と **サブネット**（例: VLAN 20、`192.168.20.0/24`、gateway `192.168.20.1`）を決める。
- 物理スイッチのホスト接続ポートを、**トランク（管理VLANはタグなし、cloud VLANはタグ付き）** にする。

## 手順

### 1. 物理スイッチ/ルータ（人）

1. cloud VLAN（例: 20）を作り、gateway（例: `192.168.20.1`）を持たせる。
2. ホストのポートをトランクにし、管理VLANは**タグなし**、cloud VLANは**タグ付き**で通す。
3. **この時点でホスト・基盤VM・利用者VMが今までどおり届くことを確認する**（まだ何も変わっていないはず）。

### 2. Proxmox の bridge を VLAN 対応にする（人・物理コンソール推奨）

`vmbr0` を `bridge-vlan-aware yes` にする（GUI の「VLAN aware」チェック、または `/etc/network/interfaces`）。**ホストの管理IPは今までどおりタグなし**のまま。

```bash
# 例（ホスト上。物理コンソールか、切れても戻れる経路で）
grep -q 'bridge-vlan-aware yes' /etc/network/interfaces || \
  sed -i '/iface vmbr0/,/^$/ s/^\(\s*\)bridge-stp/\1bridge-vlan-aware yes\n\1bridge-stp/' /etc/network/interfaces
ifreload -a
ip -4 addr show vmbr0     # 192.168.10.10/24 が残っていること
```

確認できたら、`site.yaml` を実機から作り直して `network.bridge_vlan_aware` を更新する:

```bash
set -a && . .local/pve-readonly.env && set +a
python3 tools/site-yaml.py --api     # note: bridge vmbr0 vlan_aware=true になる
```

```bash
tools/tf 10-platform plan -detailed-exitcode   # 差分なし
```

### 3. 宣言を埋める（cloud だけタグ付き）

`platform/terraform/network.yaml`:

```yaml
cloud:
  prefix: 192.168.20.0/24           # cloud VLAN のサブネット
  range_start: 192.168.20.100/24
  range_end: 192.168.20.180/24
vlan:
  management:
    vlan_id: null                   # 管理はタグなしのまま
  cloud:
    vlan_id: 20                     # 利用者VMの VLAN
```

```bash
tools/tf 10-platform plan            # NetBox の IP Range が cloud VLAN のサブネットへ移る
tools/tf 10-platform apply
```

`vlan.management.vlan_id` を設定した場合は、**bridge が vlan-aware でないと plan が precondition で止まります**（`managed-host` モジュール）。半端な状態で作らないための歯止めです。

### 4. クラウドAPI を配備する

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook \
     -i platform/ansible/inventory.netbox.yml platform/ansible/cloud.yml'
```

`render_site.py` が `network.vlan_id`（cloud）と `network.bridge_vlan_aware` を `site.json` へ入れる。**API は、cloud VLAN を設定したのに bridge が未対応なら起動を拒否します**（`site.Validate`）。以後、APIが作るVMは `net0` に `tag=<cloud vlan>` が付きます。

確認: 新しく使い捨てVMを1台作り、Proxmox の config で `net0` に `tag=20` が付き、ゲストへ SSH できること。SG も従来どおり効くこと。

```bash
tools/verify-instances.py     # 作成→SSH→削除まで。残骸なし
```

### 5. 既存の利用者VM（game1 など）

既存VMは NIC にタグが付いていません。利用するなら、停止して1回タグを付けて載せ替える（または作り直す）。

```bash
# 例: game1（VMID 100）。値は実際のMAC・bridge・VLANに合わせる
ssh root@192.168.10.10 'qm set 100 -net0 virtio=BC:24:11:F1:A4:EF,bridge=vmbr0,firewall=1,tag=20'
```

アドレスも cloud VLAN のサブネットへ移す（seed ISO／静的に設定している場合）。

## 元に戻す（ロールバック）

**まず `vlan.cloud.vlan_id` を null に戻して API を配備し直す**（新規VMがタグなしに戻る）。

```bash
# network.yaml の vlan.cloud.vlan_id を null に戻す
tools/tf 10-platform apply
# cloud.yml を再実行して site.json を戻す
```

既存VMのタグを外す:

```bash
ssh root@192.168.10.10 'qm set 100 -net0 virtio=BC:24:11:F1:A4:EF,bridge=vmbr0,firewall=1'
```

bridge の `bridge-vlan-aware` は、タグを使わなくなってから外す。**管理が届かなくなる操作は、必ず物理コンソールの前で行い、直後に到達性を確認する。**

## この段階で分離されないもの（残り）

- 内部サービス（S3・DB・ゲーム）と公開入口は、まだ管理VLAN・管理LAN上です。4区分に分けるのは後段。
- 同一VLAN内はルータを通らないため、Proxmox の VM ファイアウォール（セキュリティグループ）と、将来の Cilium NetworkPolicy を併用します（[ネットワーク・SSO](../architecture/network-auth.md)）。
- Garage の管理API（`:3903`）は、VLAN 切替後も**利用者VLANから届きうる**ので、到達先をクラウドAPIだけに絞るのは別途 VM ファイアウォールで行います。
