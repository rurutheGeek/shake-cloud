#!/bin/bash
# game1（Bazzite）のセーブ・設定を、ホストの6TB HDDへ日付つきtar.zstで取る。
# ゲーム本体・Ollamaモデル・steamapps/common は含めない（再取得できる）。
#
# 使い方（game1のデスクトップ端末で、sudoではなく自分のユーザーで実行する）:
#   1. docs/operations/backup.md の手順で /srv/game1/backup をNFSマウントする
#   2. ./game1-saves-backup.sh
# 古い世代は KEEP 個まで残して消す。
set -euo pipefail

DEST=${DEST:-/srv/game1/backup}
KEEP=${KEEP:-4}

# ここを自分の環境に合わせる。`du -sh <path>` で大きさを確かめてから足す。
# Steamのセーブは userdata。ゲーム本体は steamapps/common（含めない）。
SAVE_PATHS=(
  "$HOME/.local/share/Steam/userdata"
  "$HOME/.local/share/azahar"
  "$HOME/.var/app/org.azahar_emu.Azahar"
  "$HOME/.config"
  "$HOME/Documents"
)

if ! mountpoint -q "$DEST"; then
  echo "ERROR: $DEST がマウントされていません（docs/operations/backup.md を先に）" >&2
  exit 1
fi

existing=()
for path in "${SAVE_PATHS[@]}"; do
  if [ -e "$path" ]; then
    existing+=("$path")
  else
    echo "skip (not found): $path" >&2
  fi
done
if [ "${#existing[@]}" -eq 0 ]; then
  echo "ERROR: 存在する保存対象がありません。SAVE_PATHS を編集してください" >&2
  exit 1
fi

stamp=$(date +%Y%m%d-%H%M%S)
out="$DEST/game1-saves-$stamp.tar.zst"
echo "creating $out"
status=0
tar --zstd -cf "$out" --warning=no-file-changed "${existing[@]}" || status=$?
# tarは「読み込み中にファイルが変わった」で1を返す。失敗は2以上。
if [ "$status" -gt 1 ]; then
  echo "ERROR: tar failed ($status)" >&2
  exit "$status"
fi

mapfile -t old < <(ls -1t "$DEST"/game1-saves-*.tar.zst 2>/dev/null | tail -n +$((KEEP + 1)))
for file in "${old[@]}"; do
  echo "pruning $file"
  rm -f -- "$file"
done
ls -lh "$DEST"/game1-saves-*.tar.zst | tail -n "$KEEP"
