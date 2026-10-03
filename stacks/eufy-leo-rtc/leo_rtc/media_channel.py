"""メディアチャネル（2本目の 5-tuple）のフレーミング。

アプリ実測（2026-09-28）:
- パケットは ANKExV4 ラッパー: 9ecc | (総長/4-1) BE | SSRC | "ANKExV4\\x12" |
  カウンタ LE | マスク（コマンド 01aaaaaa / keepalive 04aaaaaa）| フレーム長 LE |
  チェックサム LE（フレーム全体の [12:] 総和、チェックサム欄は 0 扱い）| XZYH フレーム
- ライブ開始は「メディアチャネルへ 1003（XZYH 0x546）を送る」こと。カメラは 80cc を返し、
  続いて H.265 の映像（9061…、先頭 SEI "Hello,Axera"）を流す。映像は平文。
"""

from __future__ import annotations

import os
import struct

from . import cs2

MEDIA_MAGIC = b'ANKExV4\x12'
CAM_MAGIC = b'AZWCxV4\x12'
MASK_COMMAND = b'\x01\xaa\xaa\xaa'
MASK_KEEPALIVE = b'\x04\xaa\xaa\xaa'


def build_ank(frame: bytes, ssrc: int, counter: int, *, mask: bytes = MASK_COMMAND) -> bytes:
    """ANKExV4 ラッパー（チェックサム = [12:] のバイト和、欄は0扱い）。"""
    pad = (-(32 + len(frame))) % 4
    pkt = (b'\x9e\xcc' + struct.pack('>H', (32 + len(frame) + pad) // 4 - 1)
           + struct.pack('>I', ssrc) + MEDIA_MAGIC + struct.pack('<I', counter) + mask
           + struct.pack('<I', len(frame)) + b'\0\0\0\0' + frame + b'\0' * pad)
    checksum = sum(pkt[12:]) & 0xFFFFFFFF
    return pkt[:28] + struct.pack('<I', checksum) + pkt[32:]


def parse_ank(packet: bytes) -> tuple[int, int, bytes] | None:
    """(ssrc, counter, frame) を返す。カメラ側は AZWC マジック。"""
    if len(packet) < 32 or packet[:2] not in (b'\x9e\xcc', b'\x80\xcc'):
        return None
    magic = packet[8:16]
    if magic not in (MEDIA_MAGIC, CAM_MAGIC):
        return None
    ssrc, counter = struct.unpack_from('>I', packet, 4)[0], struct.unpack_from('<I', packet, 16)[0]
    length = struct.unpack_from('<I', packet, 24)[0]
    return ssrc, counter, packet[32:32 + length]


def build_keepalive(ssrc: int, counter: int) -> bytes:
    return build_ank(b'', ssrc, counter, mask=MASK_KEEPALIVE)


def new_ssrc() -> int:
    return struct.unpack('>I', os.urandom(4))[0]


class MediaCrypto:
    """CS2 の送受信（固定鍵）。"""

    def __init__(self, key: bytes = cs2.MEDIA_KEY):
        self.key = key

    def decrypt(self, data: bytes) -> bytes:
        return cs2.decrypt(data, self.key)

    def encrypt(self, data: bytes) -> bytes:
        return cs2.encrypt(data, self.key)


def build_heartbeat(seq: int, ts_ms: int) -> bytes:
    """1139 心拍（XZYH 0x473）のペイロード。

    アプリ実測（2026-09-30、pair2.pcap）: KCP チャネルで **約0.62秒ごと**に送る。
    フレーム = [フレーム長 LE32=16][1][時刻 LE32][1][連番 LE32] + XZYH 0x473 len0。
    これが無いとカメラがセッションを畳む可能性があるため、KCP 確立後すぐ始める。
    """
    frame = b'XZYH' + struct.pack('<HI', 0x473, 0) + b'\0' * 6
    return struct.pack('<IIIII', len(frame), 1, ts_ms & 0xFFFFFFFF, 1, seq & 0xFFFFFFFF) + frame
