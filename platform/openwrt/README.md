# platform/openwrt

**ルータ VM（`router-01`）の OpenWrt イメージを作る場所です。** 配備の全体像・
切替手順は [docs/operations/router.md](../../docs/operations/router.md)、開発計画は
[docs/development/N06-router.md](../../docs/development/N06-router.md) が正本です。

VM の宣言は `platform/terraform/router.yaml`、Terraform は
`platform/terraform/router/` にあります。ここはイメージ（OS + 設定）だけを
持ちます。

## 構成

| ファイル | 内容 |
| --- | --- |
| `openwrt.yaml` | ビルド宣言。**正本。** 版・Image Builder の URL とチェックサム・追加パッケージ・出力名 |
| `build.sh` | 取得 → 検証 → 展開 → 設定を焼いてイメージを作る |
| `rootfs/` | イメージへ焼くファイル。`/etc/shakecloud/config/` が UCI 設定の正本で、初回起動時に `/etc/config/` へコピーする |
| `rootfs/etc/hotplug.d/iface/` | UCI で書けない補完。`90-mape-ports`（MAP-E の 240 ポートと icmp の SNAT）、`91-lan-prefix-route`（委譲 /64 を `br-lan` へ）。**どちらも実行ビットが要る** |
| `rootfs/etc/ndppd.conf` | WAN 側の近隣要請への代理応答。odhcpd の `ndp relay` は使わない（[N06](../../docs/development/N06-router.md)） |
| `dist/` | ビルド成果物（Git 管理外）。Terraform の router モジュールが取り込む |
| `.build/` | Image Builder の展開先（Git 管理外） |

## ビルド

```bash
platform/openwrt/build.sh
```

- Image Builder は `openwrt.yaml` の日付入りリリースを固定し、sha256 を検証します。
- 設定は `rootfs/` をそのまま焼きます（UCI を後から SSH で入れる必要はありません）。
- 管理者の SSH 公開鍵は `platform/terraform/access.yaml` から生成します。**秘密鍵は置きません。**
- 必要なもの: `curl` `sha256sum` `tar`（zstd 対応）または `zstd` `make` `gzip`
  `python3` + PyYAML。**Image Builder 自身も prereq を見る**ので `gawk` `bzip2`
  `unzip` `perl` `file` も要ります（`build.sh` が先に弾きます）。Debian なら:

  ```bash
  sudo apt-get install -y make gawk bzip2 unzip file
  ```

  2026-09-20 時点の dev-b には `make` `gawk` `bzip2` が入っておらず、入れてから
  ビルドしました。

出力は `dist/openwrt-router.raw` です。Proxmox の import content は `.raw` を
受けるため、Image Builder の `.img.gz` を伸長してから置きます。

## 設定を変える

1. `rootfs/etc/shakecloud/config/` の UCI ファイルを直す。
2. `platform/openwrt/build.sh` で作り直す。
3. `tools/tf router apply` でイメージを差し替えて VM を作り直す（`dist/` の中身が
   変わると Terraform が新イメージとして扱います）。

稼働中のルータへ一時的に反映するときは、`rootfs/etc/shakecloud/` を scp して
`/etc/shakecloud/apply` を実行する手順を [operations/router.md](../../docs/operations/router.md)
に書いています。**UCI の正本は常にこのディレクトリ**で、ルータ上の手編集はしません。
