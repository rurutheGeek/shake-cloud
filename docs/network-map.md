---
title: ネットワーク図
updated: 2026-10-14
section: 入口
audience: 全員
tags:
  - hub
  - network
---

# ネットワーク図

> **更新日** 2026-10-14 ・ **区分** 入口 ・ **読む人** 全員

[netmap.apextox.dpdns.org](https://netmap.apextox.dpdns.org)（tarakoserver、Authentik でログイン）。開くたびに実機の設定を読み直す。

| 画面 | 中身 | 読む先 |
| --- | --- | --- |
| 区画 | 区画ごとの範囲・DHCP・有線ポート・SSID・機器、区画のあいだの通信 | Flint 3、NetBox |
| 区画間の通信 | 送信元 × 宛先の表。セルを開くと該当するルール | Flint 3 |
| 物理の接続 | ONU → Flint 3 の各ポート（VLAN）→ 機器 → K11 のブリッジ → VM（VLAN タグ） | Flint 3、NetBox、Proxmox |
| VM のファイアウォール | VM ごとの既定と許可（セキュリティグループ） | Proxmox |
| Tailscale | アクセス制限、端末、流している経路 | Tailscale |

| 読む先 | 鍵 |
| --- | --- |
| Flint 3 | `netmap` 専用の SSH 鍵。`/etc/shakecloud/netmap-dump` しか実行できない。名前に key・password・secret・psk を含む値は出さない |
| Proxmox | `monitoring@pve!monitoring`（PVEAuditor） |
| NetBox | `platform/sops/netbox.sops.yaml` |
| Tailscale | `platform/sops/tailscale.sops.yaml` の API トークン（90 日で切れる） |

```bash
sops exec-env platform/sops/netbox-inventory.sops.yaml \
  'ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/id_ed25519_pve .venv/bin/ansible-playbook -i platform/ansible/inventory.netbox.yml platform/ansible/netmap.yml'
```

コードは `stacks/netmap/`、配備は `platform/ansible/roles/netmap/`。
