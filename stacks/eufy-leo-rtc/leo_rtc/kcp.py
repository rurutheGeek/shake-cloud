"""KCP（メディア制御チャネル）の最小実装（leo_rtc トランスポート層）。

実測（2026-09-28）:
- パケット = 32 バイト接頭辞（`<II` + 24 バイトゼロ）+ ヘッダ
  `[conv u32][cmd u8][frg u8][wnd u16][ts u32][sn u32][una u32][len u32]` + ペイロード。
- `cmd=0x51`(PUSH) を受けたら `0x52`(ACK) を返す。`sn`/`una` は制御チャネルの通し番号。
- XZYH フレーム（`notify`）をペイロードに載せて送る。
"""

from __future__ import annotations

import struct
import time


def kcp_timestamp() -> int:
    """KCP のタイムスタンプ（ミリ秒の下位 32 ビット）。"""
    return int(time.time() * 1000) & 0xFFFFFFFF


def notify(payload: bytes, ts: int, sn: int = 0) -> bytes:
    """XZYH 通知フレーム（type=9・24 バイトヘッド・チャネル 1）。"""
    return struct.pack('<HHIIII', 9, 24, len(payload), 1, ts, 1) + struct.pack('<I', sn) + payload


def kcp_prefix(conv: int = 1) -> bytes:
    """32 バイト接頭辞。アプリ実測は末尾 4 バイトが `01 00 00 00`（conv）。

    以前は全ゼロにしており、ヘッダの解釈が 4 バイトずれていた。
    """
    return struct.pack('<II', 1, 1) + b'\0' * 20 + struct.pack('<I', conv)


class KcpChannel:
    """1 本の KCP チャネル（送信の sn 管理と受信 ACK）。"""

    def __init__(self, sock, peer) -> None:
        self.sock = sock
        self.peer = peer
        self.sn = 0
        self.una = 0

    def push(self, payload: bytes, sn: int | None = None) -> int:
        """PUSH を送る（sn を省略すると自動採番）。

        ヘッダはアプリ実測どおり **20 バイト**（cmd/frg/wnd/ts/sn/una/len）。
        以前は先頭に余分な u32 を付けており、カメラに正しく解釈されなかった。
        """
        use = self.sn if sn is None else sn
        header = struct.pack('<BBHIIII', 0x51, 0, 0x0200, kcp_timestamp(), use, self.una, len(payload))
        self.sock.sendto(kcp_prefix(1) + header + payload, self.peer)
        if sn is None:
            self.sn += 1
        return use

    def on_recv(self, data: bytes) -> tuple:
        """受信パケットを (kind, sn, una, payload) に分解し、PUSH には ACK を返す。"""
        if len(data) < 52:
            return ('ack', 0, self.una, 0)
        cmd = data[32]
        ts, sn, una, length = struct.unpack_from('<IIII', data, 36)
        if cmd == 0x51:
            self.una = sn + 1
            # アプリ実測の ACK: `52 00 ff 01 <ts> <受信 sn をエコー> <una=sn+1> 0`。
            # sn を 0 固定にしていると、カメラは自分の送信が ACK されたと見なせない。
            self.sock.sendto(
                kcp_prefix(3)
                + struct.pack('<BBHIIII', 0x52, 0, 0x01FF, ts, sn, self.una, 0),
                self.peer)
            return ('push', sn, length, data[52:52 + length])
        return ('ack', sn, una, length)
