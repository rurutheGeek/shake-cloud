#!/bin/bash
# eufyCam S4 のライブ配信を HA 向けに連続実行する。
#   セッション（leo_live.py）→ 捕捉ファイル → 中継（relay.py・常駐）→ Mediamtx(RTSP)
# カメラは数十秒で映像を止めるため、セッションは切れるたびに張り直す。中継は
# セッションと独立に常駐し、合間は最後のフレームで埋めて RTSP を途切れさせない。
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${LEO_OUT:-/var/tmp/live}"
RTSP="${LEO_RTSP:-rtsp://127.0.0.1:8554/eufy}"
# 録画用（映像＋音声）。空にすると映像のみの 1 本だけになる。
RTSP_AV="${LEO_RTSP_AV:-rtsp://127.0.0.1:8554/eufy_av}"
# HA のカード用スナップショット（HTTP）。0 で無効。
MJPEG_PORT="${LEO_MJPEG_PORT:-8888}"
# 視聴者がいないときのセッション間隔。バッテリーを節約したいときは大きくする。
IDLE_WAIT="${LEO_IDLE_WAIT:-15}"
PY="${LEO_PYTHON:-python3}"
FFMPEG="${FFMPEG:-/tmp/ffmpeg}"
# 視聴者の有無は Mediamtx の API（RTSP の読み手の数）で見る。中継が常時 publish
# するので、ログの「no one is publishing」はもう出ない。
MTX_API="${LEO_MTX_API:-http://127.0.0.1:9997}"

demand() {
    "$PY" - "$MTX_API" <<'PYEOF'
import json, sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1] + '/v3/paths/list', timeout=3) as r:
        items = json.load(r).get('items', [])
except Exception:
    sys.exit(1)
sys.exit(0 if any(i.get('readers') for i in items if i.get('name', '').startswith('eufy')) else 1)
PYEOF
}
set -a
# 実機 VM では /var/tmp/.env、コンテナでは compose の environment から来る。
if [ -f /var/tmp/.env ]; then
    # shellcheck disable=SC1091
    . /var/tmp/.env
fi
set +a
mkdir -p "$OUT"

cleanup() {
    for _pid in "${RELAY_PID:-}" "${MJPEG_SERVER_PID:-}"; do
        [ -n "$_pid" ] && kill -TERM -- -"$_pid" 2>/dev/null
    done
    [ -n "${HTTP_PID:-}" ] && kill "$HTTP_PID" 2>/dev/null
    [ -n "${LIVE_PID:-}" ] && kill "$LIVE_PID" 2>/dev/null
    exit 0
}
trap cleanup INT TERM

MTX_HOST="${RTSP#rtsp://}"
MTX_HOST="${MTX_HOST%%/*}"
MTX_HOST="${MTX_HOST%%:*}"
if ! (exec 3<>/dev/tcp/"${MTX_HOST:-127.0.0.1}"/8554) 2>/dev/null; then
    echo 'Mediamtx (:8554) がありません。先に起動してください' >&2
    exit 1
fi

n=0
wait_s=15
ensure_helpers() {
    if [ -z "${RELAY_PID:-}" ] || ! kill -0 "$RELAY_PID" 2>/dev/null; then
        setsid env LEO_OUT="$OUT" "$PY" -u "$DIR/relay.py" --out "$OUT" \
            --rtsp "$RTSP" --rtsp-av "$RTSP_AV" --ffmpeg "$FFMPEG" >> "$OUT/relay.log" 2>&1 &
        RELAY_PID=$!
    fi
    [ "${MJPEG_PORT:-0}" != "0" ] || return 0
    # 中継が書く snapshot.jpg を MJPEG として配る（HA の MJPEG カメラ用）。
    if [ -z "${MJPEG_SERVER_PID:-}" ] || ! kill -0 "$MJPEG_SERVER_PID" 2>/dev/null; then
        setsid env SNAPSHOT_FILE="$OUT/snapshot.jpg" MJPEG_PORT="${MJPEG_STREAM_PORT:-8555}" \
            MJPEG_BIND="${LEO_MJPEG_BIND:-0.0.0.0}" \
            "$PY" "$DIR/mjpeg_server.py" >> "$OUT/mjpeg_server.log" 2>&1 &
        MJPEG_SERVER_PID=$!
    fi
    if [ -z "${HTTP_PID:-}" ] || ! kill -0 "$HTTP_PID" 2>/dev/null; then
        setsid "$PY" -m http.server "$MJPEG_PORT" --bind "${LEO_MJPEG_BIND:-0.0.0.0}" --directory "$OUT" \
            >> "$OUT/http.log" 2>&1 &
        HTTP_PID=$!
    fi
}
while :; do
    n=$((n + 1))
    ensure_helpers
    rm -f "$OUT"/vf_*.bin "$OUT"/session_keys.json "$OUT"/rawkcp.bin
    # 中継は session_id の変化で新しいセッションの捕捉へ付け替える。
    echo "$n-$(date +%s)" > "$OUT/session_id.tmp" && mv "$OUT/session_id.tmp" "$OUT/session_id"
    started=$(date +%s)
    echo "--- session $n $(TZ=Asia/Tokyo date +%T) wait=${wait_s}s"
    LEO_OUT="$OUT" "$PY" -u "$DIR/leo_live.py" > "$OUT/session.log" 2>&1 &
    LIVE_PID=$!
    wait "$LIVE_PID"
    media=$(grep -c 'MEDIA\[' "$OUT/session.log" 2>/dev/null || true)
    ended=$(date +%s)
    echo "$(TZ=Asia/Tokyo date +%H:%M:%S),$media,$((ended - started)),$wait_s" >> "$OUT/sessions.csv"
    # 短時間に何度も起こすとカメラが新しいセッションを無視する。映像が取れた
    # 回は短く、取れなかった回は倍々で間隔を空ける（上限 5 分）。
    if [ "${media:-0}" -gt 0 ]; then
        wait_s="$IDLE_WAIT"
    else
        wait_s=$((wait_s * 2))
        [ "$wait_s" -gt 300 ] && wait_s=300
    fi
    # 視聴中は間を詰める。ただし失敗が続くときはバックオフを尊重する
    #（カメラは短間隔の起床を無視するため、連打は逆効果）。
    if demand; then
        demand_wait="${LEO_DEMAND_WAIT:-5}"
        if [ "${media:-0}" -gt 0 ]; then
            wait_s="$demand_wait"
        elif [ "$wait_s" -lt "$demand_wait" ]; then
            wait_s="$demand_wait"
        fi
        echo "  demand: 視聴中 -> ${wait_s}s 後に起こす"
    fi
    for _ in $(seq "$wait_s"); do
        sleep 1
        if [ "$wait_s" -gt "${LEO_DEMAND_WAIT:-15}" ] && [ $((SECONDS % 3)) = 0 ] && demand; then
            echo "  demand: 待機中に視聴開始 -> すぐ起こす"
            break
        fi
    done
done
