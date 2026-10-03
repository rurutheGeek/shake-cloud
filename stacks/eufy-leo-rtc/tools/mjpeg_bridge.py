"""受信パケットを MJPEG(HTTP) に変換して配信する（HA 橋渡し・開発用）。

入力は live_capture.py が保存する形式（[4 バイト長][RTP パケット] の繰り返し）。
追記中のファイルにも対応し（--follow）、ffmpeg の簡易 HTTP サーバで MJPEG を配信する。
Home Assistant からは MJPEG カメラ（http://<host>:<port>/）として参照できる。

I スライス（IDR）は E2E 暗号化されているため、セッションの `crypto_key`/`crypto_iv`
（環境変数 `EUFY_MEDIA_KEY`/`EUFY_MEDIA_IV`）があれば復号してから渡す。
無い場合は IDR が壊れて参照が取れず、灰色〜ゴーストになる。

使い方:
  EUFY_MEDIA_KEY=<crypto_key> EUFY_MEDIA_IV=<crypto_iv> \
    python3 tools/mjpeg_bridge.py /tmp/appstream.bin --port 8888
  # HA: camera - platform: mjpeg / mjpeg_url: http://dev-b:8888/
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from leo_rtc.video import (Depacketizer, HEVC_PARAMETER_SETS, decrypt_idr,
                            decrypt_parameter_nal, to_annexb)


def iter_packets(path: str, follow: bool):
    fh = open(path, 'rb')
    while True:
        head = fh.read(4)
        if len(head) < 4:
            if follow:
                time.sleep(0.2)
                continue
            return
        (ln,) = struct.unpack('<I', head)
        pkt = fh.read(ln)
        if len(pkt) < ln:
            if follow:
                fh.seek(-(len(head) + len(pkt)), 1)
                time.sleep(0.2)
                continue
            return
        yield pkt


def _split_packets(data: bytearray) -> list[bytes]:
    """raw 形式（RTP 連結）からパケットを取り出す。境界は magic+SSRC の候補位置。

    最後の 1 個は未完の可能性があるため data に残す（追記されたら次回処理する）。
    """
    offs = []
    i = 0
    while True:
        cands = [x for x in (data.find(b'\x90\x61', i), data.find(b'\x90\xe1', i)) if x >= 0]
        if not cands:
            break
        i = min(cands)
        if i + 24 <= len(data) and data[i + 8:i + 12] == b'\x0d\xc1\xa8\x15':
            offs.append(i)
        i += 1
    out = []
    while len(offs) >= 2:
        a, b = offs[0], offs[1]
        out.append(bytes(data[a:b]))
        del data[:b]
        offs = [x - b for x in offs[1:]]
    return out


# カメラはセッション中に解像度（レンズ）を切り替える。出力サイズを固定しないと
# libx264 が途中でエラー（-22）になり publish が止まる（実測）。レターボックスで 720p。
SCALE_FILTER = ('scale=1280:720:force_original_aspect_ratio=decrease,'
                'pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p')

# 何フレーム先が届くまで確定を待つか（断片の入れ替わり対策）。
# 遅れて届く断片が確定後に来ると参照欠けで映像が崩れるため、環境変数で調整できる。
FRAME_LAG = int(os.environ.get('LEO_FRAME_LAG', '12'))


def iter_raw_live(paths, follow: bool, poll: float = 0.15, stop=None):
    """raw 形式（vf_9061.bin・vf_90e1.bin 等）を追記しながら ts でマージして返す。

    live_capture.py はプレフィックスごとに別ファイルへ書くため、複数ファイルを
    受け取り、RTP タイムスタンプの安定ソート（同一 ts は到着順）で 1 パケットずつ
    返す（1 フレーム遅延）。順序を並べ替えると復号が壊れる（実測）。
    """
    data = {p: bytearray() for p in paths}
    off = {p: 0 for p in paths}
    buf: list[tuple[bytes, bytes]] = []
    last_ts: bytes | None = None
    while True:
        got = False
        for p in paths:
            try:
                with open(p, 'rb') as fh:
                    fh.seek(off[p])
                    chunk = fh.read()
            except OSError:
                continue
            if not chunk:
                continue
            got = True
            off[p] += len(chunk)
            data[p] += chunk
            for pkt in _split_packets(data[p]):
                buf.append((pkt[4:8], pkt))
        if buf:
            buf.sort(key=lambda x: x[0])  # ts の安定ソート（同一 ts は到着順）
            if last_ts is not None and int.from_bytes(buf[-1][0], 'big') + 0x100000 < int.from_bytes(last_ts, "big"):
                # セッション再接続で ts がリセットした: バッファを全部流す
                while buf:
                    pkt = buf.pop(0)[1]
                    last_ts = pkt[4:8]
                    yield pkt
                continue
            # 同一フレームの断片は入れ替わって届く。確定は「さらに数フレーム先が
            # 届いてから」にして、遅れた断片も同じフレームに混ぜてから流す。
            # これをやらないと参照欠けで映像が崩れる（実測）。
            groups: list[list] = []
            for item in buf:
                if not groups or groups[-1][0] != item[0]:
                    groups.append([item[0], 1])
                else:
                    groups[-1][1] += 1
            if len(groups) > FRAME_LAG:
                cut = groups[-FRAME_LAG][0]
                while buf and buf[0][0] < cut:
                    pkt = buf.pop(0)[1]
                    last_ts = pkt[4:8]
                    yield pkt
        if not got:
            if not follow:
                buf.sort(key=lambda x: x[0])
                while buf:
                    yield buf.pop(0)[1]
                return
            if stop is not None and stop():
                # 確定待ちの末尾フレームも出し切る
                buf.sort(key=lambda x: x[0])
                while buf:
                    yield buf.pop(0)[1]
                return
            time.sleep(poll)


def iter_audio_live(path: str, follow: bool, keys, poll: float = 0.15, stop=None):
    """raw 音声ファイル（vf_90ef.bin）を追記しながら復号した ADTS を返す。"""
    from leo_rtc.audio import decrypt_audio, parse_audio_rtp

    data = bytearray()
    off = 0
    while True:
        keys.reload()
        try:
            with open(path, 'rb') as fh:
                fh.seek(off)
                chunk = fh.read()
        except OSError:
            chunk = b''
        if chunk:
            off += len(chunk)
            data += chunk
            offs = []
            i = 0
            while True:
                i = data.find(b'\x90\xef', i)
                if i < 0:
                    break
                if i + 24 <= len(data) and data[i + 8:i + 12] == bytes.fromhex('228448e9'):
                    offs.append(i)
                i += 1
            while len(offs) >= 2:
                a, b = offs[0], offs[1]
                pkt = bytes(data[a:b])
                del data[:b]
                offs = [x - b for x in offs[1:]]
                if not keys.ok:
                    continue
                try:
                    _seq, _ts, payload = parse_audio_rtp(pkt)
                    yield decrypt_audio(payload, keys.key, keys.iv)
                except ValueError:
                    continue
        elif not follow:
            return
        elif stop is not None and stop():
            return
        else:
            time.sleep(poll)


def load_keys_file(path: str):
    """session_keys.json（leo_live.py が書く）から crypto_key/iv を読む。"""
    try:
        with open(path) as fh:
            j = json.load(fh)
        k, v = j.get('key'), j.get('iv')
        if k and v:
            return k.encode(), v.encode()
    except (OSError, ValueError):
        pass
    return None


class KeyRing:
    """crypto_key/iv を固定値かファイルから供給する。ファイルは更新を検知して読み直す。"""

    def __init__(self, key=None, iv=None, path: str | None = None):
        self.key = key
        self.iv = iv
        self._path = path
        self._mtime: float | None = None
        if path:
            self.reload()

    @property
    def ok(self) -> bool:
        return bool(self.key and self.iv)

    def reload(self, force: bool = False) -> bool:
        if not self._path:
            return False
        try:
            mtime = os.stat(self._path).st_mtime
        except OSError:
            return False
        if not force and mtime == self._mtime:
            return False
        got = load_keys_file(self._path)
        if not got:
            return False
        self.key, self.iv = got
        self._mtime = mtime
        print('crypto_key/iv を %s から読み込みました' % self._path)
        return True


def iter_annexb(packets, keys):
    """RTP パケット列を復号済みの HEVC Annex-B（ffmpeg へそのまま渡せる塊）にする。

    先頭の IDR より前は捨て、最初の塊の前にパラメータセットを付ける。
    """
    dep = Depacketizer()
    started = False
    first_params: dict[int, bytes] = {}
    last_ts: int | None = None
    for pkt in packets:
        keys.reload()
        ts = int.from_bytes(pkt[4:8], 'big')
        if last_ts is not None and ts + 0x100000 < last_ts:
            # セッション再接続（ts リセット）: デパケッタイザを作り直す
            dep = Depacketizer()
            first_params = {}
            keys.reload(force=True)
        last_ts = ts
        try:
            nals = dep.feed(pkt)
        except ValueError:
            continue
        if not nals:
            continue
        out = []
        for n in nals:
            t = (n[0] >> 1) & 0x3F
            if t in (32, 33, 34):
                if keys.ok:
                    try:
                        n = decrypt_parameter_nal(n, keys.key, keys.iv)
                    except ValueError:
                        continue
                first_params.setdefault(t, n)
                # パラメータはワイヤどおりその場に流す。最初の IDR 前に古い組を
                # 差し込むと、解像度切替（レンズ切替）で SPS/PPS が食い違い破損する
                # （実測: カメラの解像度切替後にノイズ映像になった）。
                out.append(n)
                continue
            if t in (19, 20):
                if keys.ok:
                    try:
                        n = decrypt_idr(n, keys.key, keys.iv)
                    except ValueError:
                        continue
                out.append(n)
                continue
            out.append(n)
        if not out:
            continue
        if not started:
            prefix = b''.join(b'\x00\x00\x00\x01' + first_params[t]
                              for t in (32, 33, 34) if t in first_params)
            started = True
            yield prefix or HEVC_PARAMETER_SETS
        yield to_annexb(out, parameters=b'')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='パケット列を MJPEG(HTTP) で配信する')
    ap.add_argument('input', nargs='+', help='live_capture.py 形式、または --raw で vf_*.bin（複数可）')
    ap.add_argument('--raw', action='store_true',
                    help='入力は raw 形式（RTP 連結。vf_9061.bin と vf_90e1.bin を両方渡す）')
    ap.add_argument('--port', type=int, default=8888)
    ap.add_argument('--audio-raw', default=None,
                    help='raw 音声ファイル（vf_90ef.bin）を追記追従して復号し、RTSP/TS 出力へ混ぜる')
    ap.add_argument('--snapshot', default=None,
                    help='最新フレームをこの JPEG へ書き続ける（HA の still_image_url 用）。'
                         '--rtsp と併用すると、配信と同じ映像から書く')
    ap.add_argument('--rtsp', default=None,
                    help='MJPEG の代わりに RTSP へ publish する（例 rtsp://mediamtx:8554/eufy。'
                         'HA の generic camera / Frigate から参照）')
    ap.add_argument('--ffmpeg', default=os.environ.get('FFMPEG', 'ffmpeg'))
    ap.add_argument('--follow', action='store_true', help='追記中のファイルを追従する')
    ap.add_argument('--fps', type=int, default=10)
    ap.add_argument('--key', default=os.environ.get('EUFY_MEDIA_KEY'), help='crypto_key（16 文字）')
    ap.add_argument('--iv', default=os.environ.get('EUFY_MEDIA_IV'), help='crypto_iv（12 文字）')
    ap.add_argument('--wait-file', default=None,
                    help='このファイルにデータが入るまで ffmpeg を起動しない（音声の到着を待つ等）')
    ap.add_argument('--keys-file', default=None,
                    help='leo_live.py が書く session_keys.json（更新を検知して読み直す）')
    args = ap.parse_args(argv)

    keys_path = args.keys_file
    if keys_path is None and args.raw:
        guess = os.path.join(os.path.dirname(os.path.abspath(args.input[0])), 'session_keys.json')
        keys_path = guess if os.path.exists(guess) else None
    keys = KeyRing(args.key.encode() if args.key else None,
                   args.iv.encode() if args.iv else None, keys_path)

    ffmpeg = args.ffmpeg if os.path.sep in args.ffmpeg else (shutil.which(args.ffmpeg) or args.ffmpeg)
    if args.snapshot:
        out_args = ['-f', 'image2', '-update', '1', '-r', str(max(1, args.fps)), args.snapshot]
        vcodec = ['-c:v', 'mjpeg', '-q:v', '5']
    elif args.rtsp:
        out_args = ['-f', 'rtsp', '-rtsp_transport', 'tcp', args.rtsp]
        # HLS/WebRTC はキーフレーム境界でしかセグメントを作れない。既定の GOP は
        # 250 フレーム（10fps で 25 秒）なので 2 秒へ短縮する。
        vcodec = ['-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
                  '-g', str(max(10, args.fps * 2)),
                  '-keyint_min', str(max(10, args.fps * 2)), '-sc_threshold', '0']

    else:
        out_args = ['-f', 'mpjpeg', '-listen', '1', 'http://0.0.0.0:%d/' % args.port]
        # mpjpeg は JPEG 専用。H.264 を渡すと多重化に失敗する。
        vcodec = ['-c:v', 'mjpeg', '-q:v', '5']
    audio_pipe = None
    if args.audio_raw and not keys.ok and not keys_path:
        print('WARNING: --audio-raw には --key/--iv が必要です（音声は復号できません）')
    elif args.audio_raw:
        if not args.rtsp:
            print('WARNING: MJPEG は音声を運べません。--rtsp と併用してください（音声は無視）')
        else:
            import threading

            rfd, wfd = os.pipe()
            audio_pipe = (rfd, wfd)

            def _pump():
                # 音声入力が先に EOF すると ffmpeg は映像ごと終了してしまう
                # （pipe:3 の End of file）。fd はプロセス終了まで開いたままにする。
                try:
                    for adts in iter_audio_live(args.audio_raw, args.follow, keys):
                        os.write(wfd, adts)
                except Exception as error:
                    print('audio pump stopped:', error)

            threading.Thread(target=_pump, daemon=True).start()

    in_args = ['-f', 'hevc', '-i', 'pipe:0']
    map_args = ['-map', '0:v']
    if audio_pipe is not None:
        in_args += ['-f', 'aac', '-i', 'pipe:3']
        map_args += ['-map', '1:a', '-c:a', 'aac', '-b:a', '32k']
    preexec = None
    if audio_pipe is not None:
        read_fd = audio_pipe[0]

        def preexec():
            os.dup2(read_fd, 3)

        # ffmpeg は両方の入力にデータが来るまで出力（RTSP 接続）を始めない。
        # 音声がまだ空の間に起動すると待ち続けるので、最初の音声が届くまで待つ。
        waited = 0.0
        while args.follow and waited < 300.0:
            try:
                if os.path.getsize(args.audio_raw) > 0:
                    break
            except OSError:
                pass
            time.sleep(0.5)
            waited += 0.5

    proc = subprocess.Popen(
        [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y'] + in_args + map_args
        + ['-vf', 'fps=%d,%s' % (args.fps, SCALE_FILTER)] + vcodec + out_args,
        stdin=subprocess.PIPE,
        pass_fds=(audio_pipe[0],) if audio_pipe else (),
        preexec_fn=preexec)
    # ffmpeg 5.1 は入力が空のまま起動すると probe に失敗して即終了する
    # （"Cannot determine format ... after EOF"）。追記モードでは最初の
    # データが溜まるまで待ってから起動する。
    if args.follow:
        waited = 0.0
        while waited < 40.0:
            ready = False
            try:
                ready = os.path.getsize(args.input[0]) > 30_000
            except OSError:
                pass
            if ready and args.wait_file:
                try:
                    ready = os.path.getsize(args.wait_file) > 0
                except OSError:
                    ready = False
            if ready:
                break
            time.sleep(0.5)
            waited += 0.5

    import signal

    def _terminate(_signum, _frame):
        try:
            proc.terminate()
        except OSError:
            pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGINT, _terminate)
    packets = iter_raw_live(args.input, args.follow) if args.raw else iter_packets(args.input[0], args.follow)
    try:
        for blob in iter_annexb(packets, keys):
            dump = os.environ.get('LEO_DUMP_H265')
            if dump:
                with open(dump, 'ab') as dfh:
                    dfh.write(blob)
            try:
                proc.stdin.write(blob)
            except BrokenPipeError:
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
