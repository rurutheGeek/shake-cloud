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

<!-- tools/render-network-map.py が network.yaml と NetBox から作る。手で編集しない。 -->

```mermaid
flowchart TB
  internet(["インターネット"])
  n_flint3{{"Flint 3<br>192.168.10.1"}}
  internet --- n_flint3
  subgraph seg_server["サーバー VLAN 10<br>192.168.10.0/24"]
    n_aterm["aterm<br>192.168.10.2<br>停止中"]
    n_apextox["apextox<br>192.168.10.10"]
    n_tarakoserver["tarakoserver<br>192.168.10.11"]
    n_shakeserver["shakeserver<br>192.168.10.12"]
    n_i_a086e5d5c8d7fa02a("win11pro<br>192.168.10.100<br>停止中")
    n_i_a06df9a2dfd1ce6db("media-01<br>192.168.10.101")
    n_i_0ea2471fe598df437("web-01<br>192.168.10.102")
    n_i_62f1d8395418e26c2("android-01<br>192.168.10.104")
    n_i_45384ba60468699f2("apps-01<br>192.168.10.105")
    n_i_bec54e3a0169b3660("game1<br>192.168.10.127")
    n_core_01("core-01<br>192.168.10.200")
    n_probe_01("probe-01<br>192.168.10.201")
    n_i_2b24ffb4f17090146("dev-01<br>192.168.10.202")
    n_i_5d72923eec77db989("dev-02<br>192.168.10.203")
    n_cloud_01("cloud-01<br>192.168.10.205")
    n_k8s_cp_01("k8s-cp-01<br>192.168.10.207")
    n_k8s_worker_02("k8s-worker-02<br>192.168.10.208")
    n_k8s_worker_01("k8s-worker-01<br>192.168.10.209")
    n_monitor_01("monitor-01<br>192.168.10.210")
  end
  n_flint3 --- seg_server
  subgraph seg_management["管理（予約） VLAN 20<br>192.168.20.0/24"]
    empty_management["（まだ無い）"]
  end
  subgraph seg_dmz["DMZ VLAN 30<br>192.168.30.0/24"]
    empty_dmz["（まだ無い）"]
  end
  n_flint3 --- seg_dmz
  subgraph seg_personal["個人端末 VLAN 40<br>192.168.40.0/24"]
    n_redmi_pad_se_8_7["redmi-pad-se-8-7<br>192.168.40.33"]
    n_su3["su3<br>192.168.40.45"]
    n_persothegeek["persothegeek<br>192.168.40.85"]
    n_iphone["iphone<br>192.168.40.90"]
    n_ouchithegeek["ouchithegeek<br>192.168.40.97"]
  end
  n_flint3 --- seg_personal
  subgraph seg_iot["ネット専用 VLAN 50<br>192.168.50.0/24"]
    n_printer["printer<br>192.168.50.3"]
    n_unknown_43["unknown-43<br>192.168.50.43"]
    n_alexa["alexa<br>192.168.50.46"]
    n_unknown_84["unknown-84<br>192.168.50.84"]
    n_eufycam_s4["eufycam-s4<br>192.168.50.98"]
    n_switchbot_hubmini_ca2a09["switchbot-hubmini-ca2a09<br>192.168.50.99"]
  end
  n_flint3 --- seg_iot
  style seg_management stroke-dasharray: 5 5
  style seg_dmz stroke-dasharray: 5 5
```

| 形 | 意味 |
| --- | --- |
| 四角 | 物理の機器 |
| 角丸 | VM |
| 点線の枠 | 未作成・予約 |

区画間の通信は [VLAN 分離](operations/vlan.md)、Flint 3 の設定は [Flint 3](operations/flint3.md)。
