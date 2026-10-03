"""カメラのセッションとは独立に、RTSP を途切れさせず配り続ける中継。

カメラは 1 接続あたり数十秒で映像を止め、次の接続まで間が空く。セッションごとに
publish し直すと HA のストリームワーカーが再接続のバックオフで窓を外し続けるため、
出力側の ffmpeg は 1 本を常駐させ、一定の 10fps・連続したタイムスタンプで流す。

  セッション（vf_*.bin）→ デコーダ ffmpeg（セッションごと）→ 生フレーム
      → 時計（10fps）→ 常駐エンコーダ ffmpeg → RTSP（映像のみ / 映像＋音声）
                                              → snapshot.jpg（MJPEG 経路用）

映像が来ない間は最後のフレームを繰り返し、音声は無音で埋める。
セッションの切替は supervisor が書く session_id で検知する。
"""

from __future__ import annotations

import argparse
import collections
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mjpeg_bridge import (KeyRing, SCALE_FILTER, iter_annexb,  # noqa: E402
                          iter_audio_live, iter_raw_live)

WIDTH, HEIGHT = 1280, 720
FRAME_BYTES = WIDTH * HEIGHT * 3 // 2  # yuv420p
AUDIO_RATE = 16000


def log(*parts) -> None:
    print(time.strftime('%H:%M:%S'), *parts, flush=True)


def black_frame() -> bytes:
    return b'\x10' * (WIDTH * HEIGHT) + b'\x80' * (WIDTH * HEIGHT // 2)


class Session:
    """1 セッション分の復号。映像・音声を生データのキューへ積む。"""

    def __init__(self, out_dir: str, ffmpeg: str, fps: int, frames, audio):
        self.out = out_dir
        self.ffmpeg = ffmpeg
        self.fps = fps
        self.frames = frames
        self.audio = audio
        self.stopped = threading.Event()
        self.procs: list[subprocess.Popen] = []
        self.keys = KeyRing(path=os.path.join(out_dir, 'session_keys.json'))

    def start(self) -> None:
        for target in (self._video, self._audio):
            threading.Thread(target=target, daemon=True).start()

    def stop(self) -> None:
        # 入力を閉じてデコーダに残りを出し切らせ、固まった場合だけ後で落とす。
        self.stopped.set()
        threading.Timer(10.0, self._kill).start()

    def _kill(self) -> None:
        for proc in self.procs:
            try:
                proc.kill()
            except OSError:
                pass

    def _spawn(self, args) -> subprocess.Popen:
        # 既定の probe（5MB）だと 1 セッション分が溜まる前に終わり 1 枚も出ない（実測）。
        # -fflags nobuffer は復号エラー（緑フレーム）を招くため付けない（handover H05）。
        low = ['-probesize', '32768', '-analyzeduration', '0']
        proc = subprocess.Popen([self.ffmpeg, '-hide_banner', '-loglevel', 'error'] + low + args,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.procs.append(proc)
        return proc

    def _pump(self, proc, blobs) -> None:
        try:
            for blob in blobs:
                if self.stopped.is_set():
                    break
                proc.stdin.write(blob)
                proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    def _video(self) -> None:
        paths = [os.path.join(self.out, n) for n in ('vf_9061.bin', 'vf_90e1.bin')]
        packets = iter_raw_live(paths, True, stop=self.stopped.is_set)
        count = 0
        # 壊れた断片でデコーダが落ちても、同じ捕捉の次の IDR から作り直す。
        while True:
            proc = self._spawn(['-max_error_rate', '1', '-f', 'hevc', '-i', 'pipe:0',
                                '-vf', 'fps=%d,%s' % (self.fps, SCALE_FILTER),
                                '-f', 'rawvideo', '-pix_fmt', 'yuv420p', 'pipe:1'])
            pump = threading.Thread(target=self._pump, args=(proc, iter_annexb(packets, self.keys)),
                                    daemon=True)
            pump.start()
            while True:
                frame = proc.stdout.read(FRAME_BYTES)
                if len(frame) < FRAME_BYTES:
                    break
                self.frames.append(frame)
                count += 1
                if count == 1:
                    log('session: first frame')
            proc.wait()
            if self.stopped.is_set():
                break
            log('session: decoder exited (%s), restarting' % proc.returncode)
            # 送り側は書き込み失敗で抜ける。抜けるまで待ってから次へ渡す。
            pump.join(5)
            time.sleep(0.2)
        log('session: video ended, frames=%d' % count)

    def _audio(self) -> None:
        path = os.path.join(self.out, 'vf_90ef.bin')
        proc = self._spawn(['-f', 'aac', '-i', 'pipe:0',
                            '-f', 's16le', '-ac', '1', '-ar', str(AUDIO_RATE), 'pipe:1'])
        threading.Thread(target=self._pump,
                         args=(proc, iter_audio_live(path, True, self.keys, stop=self.stopped.is_set)),
                         daemon=True).start()
        while True:
            chunk = proc.stdout.read(640)
            if not chunk:
                break
            self.audio.extend(chunk)


class Relay:
    def __init__(self, args):
        self.args = args
        self.fps = args.fps
        # 映像は復号が塊で届くので少し溜めてから一定間隔で出す（揺れの吸収）。
        self.frames: collections.deque = collections.deque(maxlen=self.fps * 6)
        self.audio = bytearray()
        self.last = black_frame()
        self.session: Session | None = None
        self.session_id: str | None = None
        self.encoder: subprocess.Popen | None = None
        self.audio_w: int | None = None
        self.snapshot_raw = os.path.join(args.out, 'snapshot.raw.jpg')

    def start_encoder(self) -> None:
        a = self.args
        rfd, wfd = os.pipe()
        gop = str(self.fps * 2)
        venc = ['-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
                '-g', gop, '-keyint_min', gop, '-sc_threshold', '0', '-b:v', '2500k',
                '-maxrate', '3000k', '-bufsize', '3000k', '-pix_fmt', 'yuv420p']
        cmd = [a.ffmpeg, '-hide_banner', '-loglevel', 'warning', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-s', '%dx%d' % (WIDTH, HEIGHT),
               '-r', str(self.fps), '-i', 'pipe:0',
               '-f', 's16le', '-ar', str(AUDIO_RATE), '-ac', '1', '-i', 'pipe:3',
               '-filter_complex', '[0:v]split=3[v1][v2][v3]']
        # 映像のみ（HA のスナップショットが音声付きで失敗するため別に出す）
        cmd += ['-map', '[v1]'] + venc + ['-f', 'rtsp', '-rtsp_transport', 'tcp', a.rtsp]
        if a.rtsp_av:
            cmd += ['-map', '[v2]', '-map', '1:a'] + venc + [
                '-c:a', 'aac', '-b:a', '32k', '-f', 'rtsp', '-rtsp_transport', 'tcp', a.rtsp_av]
        else:
            cmd += ['-map', '[v2]', '-f', 'null', '-']
        cmd += ['-map', '[v3]', '-r', str(a.snapshot_fps), '-c:v', 'mjpeg', '-q:v', '5',
                '-f', 'image2', '-update', '1', '-atomic_writing', '1', self.snapshot_raw]
        self.encoder = subprocess.Popen(cmd, stdin=subprocess.PIPE, pass_fds=(rfd,),
                                        preexec_fn=lambda: os.dup2(rfd, 3))
        os.close(rfd)
        self.audio_w = wfd
        log('encoder started pid=%d' % self.encoder.pid)

    def stop_encoder(self) -> None:
        if self.encoder is None:
            return
        try:
            self.encoder.kill()
            self.encoder.wait(5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if self.audio_w is not None:
            try:
                os.close(self.audio_w)
            except OSError:
                pass
        self.encoder = None
        self.audio_w = None

    def check_session(self) -> None:
        try:
            with open(os.path.join(self.args.out, 'session_id')) as fh:
                sid = fh.read().strip()
        except OSError:
            return
        if sid and sid != self.session_id:
            if self.session is not None:
                self.session.stop()
            self.session_id = sid
            self.session = Session(self.args.out, self.args.ffmpeg, self.fps, self.frames, self.audio)
            self.session.start()
            log('session %s: attached' % sid)

    def publish_snapshot(self) -> None:
        # MJPEG サーバと still_image_url が読む snapshot.jpg を差し替える。
        final = os.path.join(self.args.out, 'snapshot.jpg')
        try:
            st = os.stat(self.snapshot_raw)
            if st.st_size > 0 and st.st_mtime_ns != getattr(self, '_snap_mtime', None):
                self._snap_mtime = st.st_mtime_ns
                tmp = final + '.tmp'
                shutil.copyfile(self.snapshot_raw, tmp)
                os.replace(tmp, final)
        except OSError:
            pass

    def audio_loop(self) -> None:
        """音声は別スレッドで実時間どおりに書く。

        ffmpeg は起動時に入力を 1 本ずつ probe するため、映像と同じスレッドで
        書くと互いのパイプ待ちで固まる（実測）。
        """
        step = 0.1
        audio_bytes = int(AUDIO_RATE * 2 * step)
        next_tick = time.monotonic()
        while True:
            fd = self.audio_w
            if len(self.audio) >= audio_bytes:
                chunk = bytes(self.audio[:audio_bytes])
                del self.audio[:audio_bytes]
            else:
                chunk = b'\x00' * audio_bytes
            if len(self.audio) > AUDIO_RATE * 2 * 3:
                del self.audio[:len(self.audio) - AUDIO_RATE * 2]
            if fd is not None:
                try:
                    os.write(fd, chunk)
                except OSError:
                    time.sleep(0.5)
                    next_tick = time.monotonic()
                    continue
            next_tick += step
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -1.0:
                next_tick = time.monotonic()

    def run(self) -> None:
        period = 1.0 / self.fps
        threading.Thread(target=self.audio_loop, daemon=True).start()
        primed = False
        next_tick = time.monotonic()
        last_check = 0.0
        while True:
            if self.encoder is None or self.encoder.poll() is not None:
                self.stop_encoder()
                self.start_encoder()
                next_tick = time.monotonic()
            now = time.monotonic()
            if now - last_check > 0.5:
                self.check_session()
                last_check = now
            # 復号側の揺れを吸収するため、数フレーム溜まってから出し始める。
            if not primed and len(self.frames) >= self.args.prebuffer:
                primed = True
            if primed and self.frames:
                self.last = self.frames.popleft()
            elif primed:
                primed = False  # 枯れた: 最後のフレームを繰り返して次を待つ
            # 溜まりすぎたら遅延を詰める
            while len(self.frames) > self.fps * 3:
                self.frames.popleft()
            try:
                self.encoder.stdin.write(self.last)
                self.encoder.stdin.flush()
            except (BrokenPipeError, OSError):
                log('encoder pipe broken, restarting')
                self.stop_encoder()
                continue
            self.publish_snapshot()
            next_tick += period
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -1.0:
                next_tick = time.monotonic()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', default=os.environ.get('LEO_OUT', '/state'))
    ap.add_argument('--rtsp', default=os.environ.get('LEO_RTSP', 'rtsp://127.0.0.1:8554/eufy'))
    ap.add_argument('--rtsp-av', default=os.environ.get('LEO_RTSP_AV', ''))
    ap.add_argument('--ffmpeg', default=os.environ.get('FFMPEG', 'ffmpeg'))
    ap.add_argument('--fps', type=int, default=int(os.environ.get('LEO_RELAY_FPS', '10')))
    ap.add_argument('--snapshot-fps', type=int, default=int(os.environ.get('LEO_SNAPSHOT_FPS', '5')))
    ap.add_argument('--prebuffer', type=int, default=int(os.environ.get('LEO_RELAY_PREBUFFER', '5')))
    args = ap.parse_args(argv)
    relay = Relay(args)

    def _term(_signum, _frame):
        if relay.session is not None:
            relay.session.stop()
        relay.stop_encoder()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
    relay.run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
