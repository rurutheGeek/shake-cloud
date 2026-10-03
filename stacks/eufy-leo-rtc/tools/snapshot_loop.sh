#!/bin/bash
# カード用のスナップショットを実証済みの一括変換で作る。
#   vf_9061/vf_90e1 → packets_to_annexb（正しい順序・パラメータ）→ ffmpeg 1 フレーム
# ストリーミング復号は断片の入れ替わりで崩れることがあるため、確実な経路を使う。
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${LEO_OUT:-/state}"
PY="${LEO_PYTHON:-python3}"
FFMPEG="${FFMPEG:-ffmpeg}"
INTERVAL="${SNAPSHOT_INTERVAL:-0.7}"
while :; do
    if [ -s "$OUT/vf_9061.bin" ] && [ -s "$OUT/session_keys.json" ]; then
        KEYS=$(python3 -c "import json;d=json.load(open('$OUT/session_keys.json'));print(d['key'],d['iv'])" 2>/dev/null)
        # shellcheck disable=SC2086  # key と iv を空白で意図的に分割する
        set -- $KEYS
        if [ $# -eq 2 ]; then
            "$PY" "$DIR/packets_to_annexb.py" --format raw --key "$1" --iv "$2" \
                -o "$OUT/snap.h265" "$OUT/vf_9061.bin" "$OUT/vf_90e1.bin" >/dev/null 2>&1
            if [ -s "$OUT/snap.h265" ]; then
                # できるだけ新しいフレームを 1 枚（末尾 0.3 秒から）
                "$FFMPEG" -hide_banner -loglevel error -sseof -0.3 -i "$OUT/snap.h265" \
                    -frames:v 1 -q:v 4 -y "$OUT/snapshot.raw.jpg" >/dev/null 2>&1
                if [ -s "$OUT/snapshot.raw.jpg" ]; then
                    cp "$OUT/snapshot.raw.jpg" "$OUT/snapshot.jpg.tmp" && \
                        mv "$OUT/snapshot.jpg.tmp" "$OUT/snapshot.jpg"
                fi
            fi
        fi
    fi
    sleep "$INTERVAL"
done
