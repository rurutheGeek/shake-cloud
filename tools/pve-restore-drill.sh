#!/usr/bin/env bash
# 復元ドリル。**Proxmox VE ホスト上で root として実行する。**
#
#   tools/pve-restore-drill.sh backup  --vmid 900 --storage <バックアップ先>
#   tools/pve-restore-drill.sh restore --vmid 900 --target-vmid 901 --archive <ファイル>
#   tools/pve-restore-drill.sh cleanup --target-vmid 901
#
# bring-up.md 手順3 の「バックアップファイルが存在するだけでなく復元できる」
# を機械的に踏むためのもの。復元VMは**NICを切断した状態で起動する**ので、
# 元のVMとIP/MACが衝突しない。
#
# 破壊的な操作は cleanup だけで、確認を求める。backup と restore は
# 既存VMを消さない。target-vmid が既に存在する場合は何もしない。
set -euo pipefail

die() { printf 'restore-drill: %s\n' "$*" >&2; exit 1; }
note() { printf 'restore-drill: %s\n' "$*"; }

command -v qm >/dev/null || die "qm が無い。Proxmox VE ホスト上で実行する"
[ "$(id -u)" = 0 ] || die "root で実行する"

action="${1:-}"; shift || true
vmid=""; target_vmid=""; storage=""; archive=""; assume_yes=0

while [ $# -gt 0 ]; do
  case "$1" in
    --vmid) vmid="$2"; shift 2 ;;
    --target-vmid) target_vmid="$2"; shift 2 ;;
    --storage) storage="$2"; shift 2 ;;
    --archive) archive="$2"; shift 2 ;;
    --yes) assume_yes=1; shift ;;
    *) die "不明な引数: $1" ;;
  esac
done

vm_exists() { qm status "$1" >/dev/null 2>&1; }

case "$action" in
  backup)
    [ -n "$vmid" ] || die "--vmid が必要"
    [ -n "$storage" ] || die "--storage が必要（**別媒体**を指定する。同じSSD上の別領域は故障対策にならない）"
    vm_exists "$vmid" || die "VMID $vmid が無い"
    note "VMID $vmid を $storage へバックアップする"
    vzdump "$vmid" --storage "$storage" --mode snapshot --compress zstd
    note "完了。次は restore で別VMIDへ戻す。--archive には上に出たファイル名を渡す"
    ;;

  restore)
    [ -n "$target_vmid" ] || die "--target-vmid が必要"
    [ -n "$archive" ] || die "--archive が必要"
    [ -f "$archive" ] || die "アーカイブが無い: $archive"
    [ "$target_vmid" != "$vmid" ] || die "復元先は元のVMIDと別にする"
    if vm_exists "$target_vmid"; then
      die "VMID $target_vmid は既に存在する。上書きしない。別のVMIDを使う"
    fi
    note "VMID $target_vmid へ復元する"
    qmrestore "$archive" "$target_vmid"
    # 元のVMと同じIP/MACで起動させない。bring-up.md 手順3の条件。
    note "復元VMの全NICを切断する"
    for index in 0 1 2 3; do
      value="$(qm config "$target_vmid" | sed -n "s/^net${index}: //p")" || true
      [ -n "$value" ] || continue
      case "$value" in
        *link_down=1*) : ;;
        *) qm set "$target_vmid" "--net${index}" "${value},link_down=1" ;;
      esac
    done
    note "NICを切断した状態で起動する"
    qm set "$target_vmid" --onboot 0
    qm start "$target_vmid"
    cat <<'EOS'

次にコンソール（Proxmox GUI の Console）から入り、検証用ファイルが
戻っていることを確認する。SSHは使えない（NICを切断しているため）。

  確認できたら:  tools/pve-restore-drill.sh cleanup --target-vmid <復元先>

EOS
    ;;

  cleanup)
    [ -n "$target_vmid" ] || die "--target-vmid が必要"
    vm_exists "$target_vmid" || die "VMID $target_vmid が無い"
    name="$(qm config "$target_vmid" | sed -n 's/^name: //p')"
    if [ "$assume_yes" != 1 ]; then
      printf 'restore-drill: VMID %s (%s) を完全に削除する。よろしいか [yes/NO]: ' "$target_vmid" "${name:-no-name}"
      read -r answer
      [ "$answer" = yes ] || die "中止した"
    fi
    qm stop "$target_vmid" || true
    qm destroy "$target_vmid" --purge 1
    note "VMID $target_vmid を削除した"
    ;;

  *)
    die "使い方: $(basename "$0") {backup|restore|cleanup} [--vmid N] [--target-vmid N] [--storage S] [--archive F] [--yes]"
    ;;
esac
