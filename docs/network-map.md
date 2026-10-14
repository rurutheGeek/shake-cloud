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

[クラウドのポータルの「ネットワーク」](https://cloud.apextox.dpdns.org/#network-view)。開くたびに台帳（NetBox）から読み直す。

| 取得方法 | 内容 |
| --- | --- |
| ポータル | 区画ごとの機器と VM |
| `shakecloud subnet map` | 同じ内容を表で |
| `GET /v1/network-map` | 同じ内容を JSON で |

区画の正本は `platform/terraform/network.yaml`、機器とアドレスの正本は NetBox。区画間の通信は [VLAN 分離](operations/vlan.md)、Flint 3 の設定は [Flint 3](operations/flint3.md)。
