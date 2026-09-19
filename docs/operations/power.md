---
title: 電源と UPS
updated: 2026-09-13
section: 運用手順
audience: 管理者
tags:
  - ops
  - power
---

# 電源と UPS

> **更新日** 2026-09-13 ・ **区分** 運用手順 ・ **読む人** 管理者

**状態**: 手順書。UPS（CyberPower CP1200PFCLCDJP）の状態取得は NUT で配備済み（M01。`pve_nut` ロール＋`platform/ansible/pve-nut.yml`、読み取り専用）。K11 の電源を UPS のバッテリー側へ入れる作業と、低電池時の自動シャットダウン（upsmon）は未実施。

家庭内の電源工事や停電のとき、**いきなりコンセントやブレーカーを切らない**ための手順です。K11（Proxmox ホスト）とその上のゲストを安全に止めます。

## いまの電源構成

- K11（Proxmox ホスト、`192.168.10.126`）が1台。その上に基盤VM（identity・cloud-01・services-01・storage-s3・Kubernetes の各ノード）と利用者VMが載っています。
- 管理経路（ルータ・スイッチ・監視ラズパイ）は K11 とは別の電源です（[ネットワーク・公開範囲・SSO](../architecture/network-auth.md)）。
- **目標:** K11 を UPS の**バッテリー側**コンセントへ入れ、停電でも安全に停止できるようにする。

## UPS を間に入れる（稼働中に抜き差ししない）

1. UPS を**壁コンセント**へつなぎ、充電する（負荷はまだつながない）。
2. 後述の「安全な電源の切り方」で K11 を停止する。
3. K11 と周辺機器のプラグを、UPS の**バッテリー側**コンセントへ挿す（サージ保護だけの口と間違えない）。
4. UPS の電源を入れ、K11 を起動する。
5. `on_boot: true` の VM が自動起動します。状態を確認します。

> **稼働中にプラグを抜き差ししない。** 瞬断でも SSD やデータベースが壊れます。

## 安全な電源の切り方（この順番）

**1. 作業とジョブを止める**

AWX の実行中ジョブ、ポータルの非同期タスク（VM 作成など）が無いことを確認します。

**2. Kubernetes を止める**

```bash
tools/k8s down      # worker → control plane の順に ACPI で停止
tools/k8s status    # 3台とも stopped になるまで確認
```

**3. ホストを止める**

```bash
ssh root@192.168.10.126 'shutdown -h now'
```

Proxmox は**ホストの停止時に残りのゲストも止めます**（`on_boot` の逆順、ACPI、既定のタイムアウト付き）。`shutdown` が返ってきてもまだ落ちていないので、電源ランプが消えるまで待ちます。Proxmox の Web UI の「Shutdown」でも同じです。

**`Stop`（強制電源断）は最終手段。** ACPI が効かないときだけ使い、使ったら次回起動後にデータを確認します。個別に止めたいときは、ゲストの中で `sudo poweroff` が確実です。

**4. 完全に落ちたのを確認してから電源を切る**

```bash
ssh root@192.168.10.126 'qm list; pct list'   # running が無いこと
```

ホストと全ゲストが停止したのを確認してから、**UPS／ブレーカーの電源を切ります。**

**5. クラウド管理下の VM は利用者のもの**

game1 や利用者VMは**ポータル／CLI で所有者が停止**します（管理者が勝手に削除・停止しない）。ホスト停止時は他のゲストと一緒に止まりますが、次に使う人が電源を入れ直します。

## 復電したとき

1. 壁 → UPS の順で通電する。
2. K11 を起動する（電源ボタン）。
3. **常時動く基盤**（identity・cloud-01・services-01・storage-s3）は `onboot` で自動起動します。**それ以外（Kubernetes・開発VM・game1）は「切れる前に動いていた組」だけを `shakecloud-guests` が戻します**（[停電時に動いていたVMを戻す](#停電時に動いていたvmを戻す実装済み)）。Kubernetes が戻った場合は Flux が Git と同期し直します。worker-02（予備）は手動です。
4. 動作確認:
   - `https://cloud.apextox.dpdns.org/healthz` → 200
   - `https://auth.apextox.dpdns.org`（ログイン）
   - `https://netbox.apextox.dpdns.org`、`https://awx.apextox.dpdns.org`
   - `tools/k8s status` が `running`
5. k8s の中身は Flux が Git から合わせ直します。AWX・CNPG・Knative が Ready になるまで数分かかります（[Kubernetes クラスタ](kubernetes.md#止めると何が止まるか)）。

<a id="停電時に動いていたvmを戻す実装済み"></a>
## 停電時に動いていたVMを戻す（実装済み）

`onboot: true` は「決まったVM」しか戻せません。**「切れたときに動いていたVM」をそのまま戻す**仕組みを Proxmox ホストへ入れてあります（Ansible ロール `pve_guest_state`）。

- **`shakecloud-guests.service`**: 起動時に、記録した組のうちまだ動いていないVMを `qm start` します。停止時は `pve-guests` がVMを止める**前**に、いま動いている組を記録します。
- **`shakecloud-guests-snapshot.timer`**: 1分ごとに記録します。**ハード停電でも直前の状態が残ります。**
- 記録先は `/var/lib/shakecloud/guests-running`（VMID の一覧）。

配備（**root SSH が通る管理マシン**で実行）:

```bash
cp platform/ansible/pve.ini.example platform/ansible/pve.ini   # 初回のみ。実値を入れる
.venv/bin/ansible-playbook -i platform/ansible/pve.ini platform/ansible/pve-guests.yml
```

- 確認: `cat /var/lib/shakecloud/guests-running` と `systemctl status shakecloud-guests`。
- **ホスト自体が復電後に起動するには、BIOS の "Restore on AC Power Loss" を `Power On`（または `Last State`）に**してください。OSからは設定できません。
- 手動で停止したVMは次の記録から外れるので、次回の起動では戻りません（意図どおり）。
- **`onboot` を付けるのは常時動く基盤（identity・cloud-01・services-01・storage-s3）だけ**にしています。Kubernetes・開発VM・game1 は `onboot=0` で、保存された組から戻します（`tools/k8s down` で止めていた Kubernetes が電源再投入で勝手に戻る、を防ぐため。2026-09-12 に実際に起きました）。
- game1 は起動時に **CD が移動前の `local:iso` を指していて起動できませんでした**。`cloud-images:iso/bazzite-stable-live-amd64.iso` へ直してあります（ISO を `cloud-images` へ移したときの取り残し）。

## 停電で自動停止させる（任意・推奨）

**NUT の読み取り（`upsd` と読み取り専用ユーザー）は配備済みです。** Proxmox ホストの `platform/ansible/pve-nut.yml`（ロール `pve_nut`）が入れ、monitor-01 の nut_exporter が `192.168.10.126:3493` を読んで Grafana に出します（M01）。低電池時に自動で落とす `upsmon` はまだ有効にしていません。

**残りの作業（低電池での自動シャットダウン）の骨子:**

1. `nut-client`（`upsmon`）を入れ、`/etc/nut/upsmon.conf` に
   `MONITOR <ups>@localhost 1 <user> <pass> master` と
   `SHUTDOWNCMD "/sbin/shutdown -h +0"`、`MINSUPPLIES 1`、`FINALDELAY 5` を書く。
2. `systemctl enable --now nut-monitor` と `upsc <ups>` で確認。

あわせて **BIOS の "Restore on AC Power Loss" を Power On** にすると、復電後に自動で起動します。VM の起動順は `hosts.yaml` の `on_boot` と Proxmox の Startup order で決めます。

> NUT はホストで動かします。ホストが落ちるときに Proxmox がゲストも止めるので、ゲスト側に別々の NUT は要りません。

## 容量と選び方の目安

- **K11 と周辺の消費電力を実測**してから VA/W を選ぶ（アイドルは数十W、ゲームやビルドで上がる）。UPS の**実効W**（VA×力率）で見る。
- **バッテリー側コンセント**を使う。レーザープリンタ・掃除機・ドライヤーなどはつながない。
- 電源アダプタが敏感なら**正弦波**の UPS を選ぶ（疑似正弦波で異音・再起動する機器がある）。
- **ラズパイ・ルータ・スイッチを別の小さな UPS に載せる**と、停電中も管理経路と VPN が残ります（[復旧経路](../architecture/network-auth.md)）。

## 関連

- [Kubernetes クラスタ（止めると何が止まるか）](kubernetes.md#止めると何が止まるか)
- [クラウドAPIの構築（管理DBのバックアップ）](cloud.md)
- [NetBox の使い方（バックアップ）](netbox.md)
- [配備・Git管理・ストレージ・復旧](../architecture/operations.md)
