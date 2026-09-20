# 電源と UPS

更新日: 2026-09-20。状態: **手順書。UPS（CyberPower CP1200PFCLCDJP）の監視（NUT）と低電池の自動シャットダウン（upsmon）は配備済み（M01。`pve_nut` ロール＋`platform/ansible/pve-nut.yml`）。K11 の電源プラグを UPS のバッテリー側へ入れる物理作業は未実施。K11 のハング自動復旧（SP5100 TCO watchdog）は 2026-09-20 に適用済み。**

家庭内の電源工事や停電のとき、**いきなりコンセントやブレーカーを切らない**ための手順です。K11（Proxmox ホスト）とその上のゲストを安全に止めます。

## いまの電源構成

- K11（Proxmox ホスト、`192.168.10.10`）が1台。その上に基盤VM（identity・cloud-01・services-01・storage-s3・Kubernetes の各ノード）と利用者VMが載っています。
- 管理経路（ルータ・スイッチ・監視ラズパイ）は K11 とは別の電源です（[ネットワーク・公開範囲・SSO](../architecture/network-auth.md)）。
- **目標:** K11 を UPS の**バッテリー側**コンセントへ入れ、停電でも安全に停止できるようにする。

## K11 が固まったときの自動復旧（watchdog）

K11 がハングするとルータ VM も止まり、家中のネットが落ちます。手で再起動するまで
戻りません。そこで **ハードウェア watchdog（SP5100 TCO）** を有効にしています
（2026-09-20 適用。ホスト側の設定で、Ansible 管理外）。

- PVE の `watchdog-mux` が `/etc/default/pve-ha-manager` の
  `WATCHDOG_MODULE=sp5100_tco` で TCO を開き、**10秒タイムアウトで毎秒 KEEPALIVE**
- ホストが固まると約10秒でハードウェアリセット → 起動 → `on_boot`＋起動順1 で
  `router-01` が自動起動し、**ネットは約1〜2分で戻る**
- クリーン停止時は MAGICCLOSE（`options=0x8180`）で解除されるので、
  シャットダウンを妨げない
- panic でも自動再起動するように `kernel.panic=10` / `kernel.panic_on_oops=1`
  （`/etc/sysctl.d/90-panic.conf`）

```bash
ssh root@192.168.10.10 'systemctl is-active watchdog-mux; wdctl | head -4; sysctl kernel.panic kernel.panic_on_oops'
# Identity: SP5100 TCO timer / Timeout: 10 seconds が出れば有効
```

**引き金は game1（VM 100）の iGPU パススルーです。** 開始/停止の直後にホストが
ハングした実績が 2026-09-20 に複数回あります（01:28・01:31・01:34・01:40・14:57）。
メモリ・ディスク・温度・I/O は実測でシロ（OOM・I/Oエラーなし、SMART PASS）。
game1 を停止/起動するときは、この自動復旧が働く前提で行ってください。

**なぜ落ちるか**: iGPU `c6:00.0` は FLR に非対応で、リセット手段が**バスリセット
しかありません**（`cat /sys/bus/pci/devices/0000:c6:00.0/reset_method` → `bus`）。
`c6:00` は APU 内のひとつの部品で、ホストが使用中の USB（`.3`/`.4`。UPS と
キーボードがここ）・暗号チップ（`.2`）・音声（`.5`/`.6`）が同居しています。
VM 停止時に GPU を戻そうとしてバスリセットが走ると、この一族が道連れになり、
ホストがログを 1 行も残さず即死します。

**まずやること**: `qm stop` をやめ、**`qm shutdown 100 --timeout 120`** を使う
（[router.md](router.md) の K11 メンテナンス節）。ゲストの systemd が amdgpu を
正規手順で手放してから QEMU が終わるので、危険なリセットに入りにくくなります。
それでも落ちる場合の候補は、カーネルパラメータ `initcall_blacklist=sysfb_init`
（ホストが iGPU を使わないようにする）、`hostpci0` への `disable_vga=1`、
`reset_method` を空にしてバスリセット自体を封じる udev ルール（代償: VM を
停止したら次の起動までにホスト再起動が要る）、そして**ルータを K11 の外へ
出す**ことです。

### 自動復帰は「落ちる直前の状態」に合わせます

ホストが落ちると `shakecloud-guests restore` が、直前に動いていたゲストを
起こします（`onboot=1` でないものも戻すための補助）。

素朴に作ると、**止めた直後に落ちたゲストが復活します**。スナップショットは
毎分なのに、game1 の停止で起きるハングは**数秒後**に来るので、記録は
「running」のまま固まるからです。実際 2026-09-20 08:44:53 に game1 が
自動起動していました。

そこで `restore` は Proxmox のタスクログ（`/var/log/pve/tasks/`）も読みます。
**スナップショットより後に停止・シャットダウンされたゲストは起こしません。**
いったん止めて起動し直したものは、最後が起動なので普通に戻します。結果として
復帰する組は「ホストが落ちた瞬間に動いていた組」に一致します。

```bash
# 復帰時に何を起こし、何を見送ったか
ssh root@192.168.10.10 'journalctl -b 0 -u shakecloud-guests.service | tail'
# start 401: rc=0
# skip 100: qmstop after the last snapshot   ← 止めた直後に落ちた場合
```

判定は `tests/test_pve_guest_state.py` が実機なしで検査します。タスクログが
読めないときは**復帰を優先**します（停電でゲストが上がってこないほうが困る
ため）。

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
ssh root@192.168.10.10 'shutdown -h now'
```

Proxmox は**ホストの停止時に残りのゲストも止めます**（`on_boot` の逆順、ACPI、既定のタイムアウト付き）。`shutdown` が返ってきてもまだ落ちていないので、電源ランプが消えるまで待ちます。Proxmox の Web UI の「Shutdown」でも同じです。

**`Stop`（強制電源断）は最終手段。** ACPI が効かないときだけ使い、使ったら次回起動後にデータを確認します。個別に止めたいときは、ゲストの中で `sudo poweroff` が確実です。

**4. 完全に落ちたのを確認してから電源を切る**

```bash
ssh root@192.168.10.10 'qm list; pct list'   # running が無いこと
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

## 停電で自動停止させる（実装済み）

**NUT の監視（`upsd` と読み取り専用ユーザー）と `upsmon` は配備済みです。** Proxmox ホストの `platform/ansible/pve-nut.yml`（ロール `pve_nut`）が入れ、monitor-01 の nut_exporter が `192.168.10.10:3493` を読んで Grafana に出します（M01）。低電池では `upsmon`（primary）が `/usr/local/sbin/pve-ups-shutdown` を root で実行し、次の順で止めます。

1. **猶予 60 秒**（`pve_nut_shutdown_grace_seconds`）。実行中ジョブの確認は自動ではできないため、短いジョブの完了を待つ。
2. **k8s worker**（tags `k8s-worker` のVM）を ACPI で停止し、最大 180 秒待つ（`pve_nut_k8s_stop_timeout`）。
3. **k8s control plane**（tags `k8s-cp`）を同じく停止（etcd を先に止めない順）。
4. **ホストを `shutdown -h now`**。残りのゲストは Proxmox が止める。

```bash
# 動作確認（実際には止めない）
ssh root@192.168.10.10 'PVE_UPS_SHUTDOWN_DRY_RUN=1 /usr/local/sbin/pve-ups-shutdown'
ssh root@192.168.10.10 'systemctl status nut-monitor; upsc cyberpower@localhost ups.status'
```

- `monitor` ユーザーは読み取り専用のまま。upsmon 専用ユーザー（`upsmon`）を分けてあり、パスワードは `monitoring.sops.yaml` の `NUT_UPSMON_PASSWORD`。
- **長い AWX ジョブは停電時に失われます。** 猶予は 60 秒なので、停電前に止められるものは手順どおり止めてください。
- あわせて **BIOS の "Restore on AC Power Loss" を Power On** にすると、復電後に自動で起動します。VM の起動順は `hosts.yaml` の `on_boot` と Proxmox の Startup order で決めます。

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
