#!/usr/bin/env bash
# ルータ VM 用の OpenWrt イメージを Image Builder で作る。
#
#   platform/openwrt/build.sh
#
# 宣言の正本は platform/openwrt/openwrt.yaml。成果物は同ディレクトリの
# dist/ へ出る（Git 管理外）。VM への取り込みは
# platform/terraform/router/ の Terraform が行う。
#
# 再現性のため、Image Builder は日付入りリリースを固定し、チェックサムを
# 検証してから展開する。パッケージはビルド時に配布元フィードから取得する
# （ポイントリリースのフィードは不変なので、同じ版なら同じ構成になる）。
#
# 必要なもの: curl sha256sum tar（zstd 対応の tar か zstd）make gzip python3 + PyYAML。
# Image Builder 自身も prereq を見るので gawk・bzip2・unzip・perl・file が要る
# （Debian なら apt-get install make gawk bzip2 unzip file）。下のループで
# **先に**弾く。ここを通さないと make の奥で失敗して原因が読みにくい。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OPENWRT="$ROOT/platform/openwrt"
SPEC="$OPENWRT/openwrt.yaml"
BUILD="$OPENWRT/.build"
DIST="$OPENWRT/dist"
ACCESS="$ROOT/platform/terraform/access.yaml"

die() { printf 'build: %s\n' "$*" >&2; exit 1; }

for tool in curl sha256sum tar make gzip python3 gawk bzip2 unzip perl file; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool が無い"
done

# --- 宣言を読む（YAML を sh へ） ---
eval "$(python3 - "$SPEC" <<'PY'
import shlex, sys, yaml

spec = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))
builder = spec['imagebuilder']
values = {
    'version': spec['version'],
    'url': builder['url'],
    'archive': builder['file_name'],
    'checksum': builder['checksum'],
    'profile': spec['profile'],
    'target': spec['target'],
    'partsize': str(spec['rootfs_partition_mib']),
    'packages': ' '.join(spec['packages']),
    'output_image': spec['output_image'],
    'output_manifest': spec['output_manifest'],
}
for key, value in values.items():
    print(f'{key}={shlex.quote(value)}')
PY
)"

[ -f "$ACCESS" ] || die "platform/terraform/access.yaml が無い"

mkdir -p "$BUILD" "$DIST"

# --- Image Builder を取得し、チェックサムを検証する ---
archive="$BUILD/$archive"
if [ ! -f "$archive" ] || ! printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c - >/dev/null 2>&1; then
  echo "== 取得: $url"
  curl --fail --location --output "$archive.part" "$url"
  printf '%s  %s\n' "$checksum" "$archive.part" | sha256sum -c - \
    || die "チェックサムが一致しない。配布元と openwrt.yaml を確認する"
  mv "$archive.part" "$archive"
fi
echo "== Image Builder: $version ($archive 検証済み)"

# --- 展開 ---
rm -rf "$BUILD/imagebuilder"
if tar --zstd -tf "$archive" >/dev/null 2>&1; then
  tar --zstd -xf "$archive" -C "$BUILD"
elif command -v zstd >/dev/null 2>&1; then
  zstd -dc "$archive" | tar -xf - -C "$BUILD"
else
  die "tar の --zstd も zstd コマンドも無い。zstd を入れる"
fi
extracted="$(find "$BUILD" -maxdepth 1 -mindepth 1 -type d -name 'openwrt-imagebuilder-*' | head -1)"
[ -n "$extracted" ] || die "展開先が見つからない"
mv "$extracted" "$BUILD/imagebuilder"

# --- イメージへ焼くファイルを作る ---
overlay="$BUILD/rootfs"
rm -rf "$overlay"
mkdir -p "$overlay"
cp -a "$OPENWRT/rootfs/." "$overlay/"

# 管理者の SSH 公開鍵。正本は access.yaml で、秘密鍵は置かない。
# これが無いと切替前にコンソール以外で入れない。
mkdir -p "$overlay/etc/dropbear"
python3 - "$ACCESS" > "$overlay/etc/dropbear/authorized_keys" <<'PY'
import sys, yaml

keys = yaml.safe_load(open(sys.argv[1], encoding='utf-8'))['admin_ssh_public_keys']
sys.stdout.write('\n'.join(keys) + '\n')
PY

chmod 755 "$overlay/etc/shakecloud/apply" \
          "$overlay/etc/uci-defaults/97-shakecloud-adguard" \
          "$overlay/etc/uci-defaults/98-shakecloud-ndppd" \
          "$overlay/etc/uci-defaults/99-shakecloud-router"
chmod 644 "$overlay/etc/dropbear/authorized_keys" \
          "$overlay"/etc/shakecloud/config/*

# --- ビルド ---
echo "== make image PROFILE=$profile ($packages)"
make -C "$BUILD/imagebuilder" image \
  PROFILE="$profile" \
  PACKAGES="$packages" \
  FILES="$overlay" \
  ROOTFS_PARTSIZE="$partsize" \
  BIN_DIR="$DIST"

board="${target%/*}"
subtarget="${target#*/}"
# BIN_DIR へは targets/ を挟まず、この名前で直接出る。
image_gz="$DIST/openwrt-$version-$board-$subtarget-generic-ext4-combined.img.gz"
[ -f "$image_gz" ] || image_gz="$(find "$DIST" -maxdepth 1 -name '*-ext4-combined.img.gz' | head -1)"
[ -n "$image_gz" ] && [ -f "$image_gz" ] || die "ext4-combined イメージができなかった"

# Proxmox の import content は .raw / .qcow2 / .vmdk を受ける（.img.gz は不可）。
# Image Builder の .img.gz には gzip ストリームの後ろに minisign 署名が付く。
# gzip は「decompression OK, trailing garbage ignored」で終了コード 2 を返すが、
# 展開結果は完全なので、その場合だけ許す。
if ! gzip -dc "$image_gz" > "$DIST/$output_image.tmp" 2>"$BUILD/gzip.err"; then
  if ! grep -q 'decompression OK' "$BUILD/gzip.err"; then
    cat "$BUILD/gzip.err" >&2
    rm -f "$DIST/$output_image.tmp" "$BUILD/gzip.err"
    die "gunzip に失敗した: $image_gz"
  fi
fi
rm -f "$BUILD/gzip.err"
mv "$DIST/$output_image.tmp" "$DIST/$output_image"

manifest="$(find "$DIST" -name '*.manifest' | head -1)"
[ -n "$manifest" ] && cp "$manifest" "$DIST/$output_manifest"

echo "== 完了"
echo "   image : $DIST/$output_image"
sha256sum "$DIST/$output_image"
echo "   next  : tools/tf router plan   # platform/terraform/router が取り込む"
