#!/usr/bin/env python3
"""snapshot.jpg を multipart/x-mixed-replace で配る小さなサーバー。

HA の MJPEG カメラ（mjpeg 統合）から見ると動画になる。RTSP/HLS が不安定な間の
確実な経路として使う。ファイルは snapshot_loop.sh が更新する。
"""

import argparse
import os
import socket
import threading
import time

BOUNDARY = 'eufyframe'


def stream(conn: socket.socket, path: str) -> None:
    last = None
    while True:
        try:
            info = os.stat(path)
            stamp = (info.st_mtime_ns, info.st_size)
            if stamp != last and info.st_size > 0:
                with open(path, 'rb') as handle:
                    data = handle.read()
                conn.sendall(b'--' + BOUNDARY.encode() + b'\r\n'
                             b'Content-Type: image/jpeg\r\nContent-Length: '
                             + str(len(data)).encode() + b'\r\n\r\n' + data + b'\r\n')
                last = stamp
            else:
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', default=os.environ.get('SNAPSHOT_FILE', '/state/snapshot.jpg'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('MJPEG_PORT', '8555')))
    parser.add_argument('--bind', default=os.environ.get('MJPEG_BIND', '0.0.0.0'))
    args = parser.parse_args()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.bind, args.port))
    server.listen(4)
    print('mjpeg server', args.bind, args.port, '->', args.snapshot, flush=True)
    while True:
        conn, _ = server.accept()
        conn.sendall(b'HTTP/1.0 200 OK\r\n'
                     b'Content-Type: multipart/x-mixed-replace; boundary=' + BOUNDARY.encode() + b'\r\n\r\n')
        threading.Thread(target=stream, args=(conn, args.snapshot), daemon=True).start()


if __name__ == '__main__':
    raise SystemExit(main())
