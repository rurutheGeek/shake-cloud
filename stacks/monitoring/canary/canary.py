"""おとり。待ち受けて、触られたことを JSON の 1 行にして標準出力へ書くだけ。

正規の利用者はこの IP を知らない。接続は全部、侵入後の探索か走査とみなす。
応答は最小限（バナーだけ）で、認証も処理もしない。
"""
import asyncio
import json
import os
import sys
import time

BANNERS = {
    22: b'SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u3\r\n',
    23: b'login: ',
    21: b'220 FTP server ready\r\n',
}
DEFAULT_PORTS = (21, 22, 23, 80, 445, 3306, 3389, 5900, 8080)
READ_LIMIT = 128
READ_TIMEOUT = 5.0


def ports():
    raw = os.environ.get('CANARY_PORTS', '')
    values = [int(item) for item in raw.replace(',', ' ').split()] if raw.strip() else DEFAULT_PORTS
    return tuple(values)


def record(port, peer, data):
    print(json.dumps({
        'event': 'touch',
        'port': port,
        'src': peer[0],
        'sport': peer[1],
        'data': data.decode('latin-1')[:READ_LIMIT],
        'time': int(time.time()),
    }, ensure_ascii=True), flush=True)


def handler(port):
    async def handle(reader, writer):
        peer = writer.get_extra_info('peername') or ('?', 0)
        data = b''
        try:
            banner = BANNERS.get(port)
            if banner:
                writer.write(banner)
                await writer.drain()
            data = await asyncio.wait_for(reader.read(READ_LIMIT), READ_TIMEOUT)
        except (asyncio.TimeoutError, ConnectionError, OSError):
            pass
        finally:
            record(port, peer, data)
            writer.close()
    return handle


async def main():
    servers = []
    for port in ports():
        servers.append(await asyncio.start_server(handler(port), '0.0.0.0', port))
    print(json.dumps({'event': 'start', 'ports': list(ports())}), flush=True)
    await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
