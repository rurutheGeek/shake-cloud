"""ICE（STUN）メッセージの組立（leo_rtc トランスポート層）。

実測（2026-09-27/28）:
- バインディング要求: `0x0001` + MAGIC + tid、`USERNAME`(0x0006)、優先度(0xc057)、
  制御役(0x802a)、候補(0x0024/0x0025)、`MESSAGE-INTEGRITY`(0x0008, HMAC-SHA1)、
  `FINGERPRINT`(0x8028, CRC32^0x5354554E)。
- 応答: `0x0101` + `XOR-MAPPED-ADDRESS`(0x0020) + MI + FP。
- 制御役はクライアント（ICE-CONTROLLING 0x802a / USE-CANDIDATE 0x0025）。
"""

from __future__ import annotations

import binascii
import hashlib
import hmac
import os
import socket
import struct

MAGIC = 0x2112A442
FP_XOR = 0x5354554E
CONTROLLING_PRIORITY = 0x6E7F1EFF


def attr(kind: int, value: bytes) -> bytes:
    """STUN 属性（4 バイト境界にパディング）。"""
    return struct.pack('>HH', kind, len(value)) + value + b'\0' * ((-len(value)) % 4)


def add_mi(message: bytearray, pwd: bytes) -> None:
    """MESSAGE-INTEGRITY を末尾に付ける（長さフィールドを更新）。"""
    struct.pack_into('>H', message, 2, len(message) - 20 + 24)
    message += attr(0x0008, hmac.new(pwd, bytes(message), hashlib.sha1).digest())


def add_fp(message: bytearray) -> None:
    """FINGERPRINT を末尾に付ける（長さフィールドを更新）。"""
    struct.pack_into('>H', message, 2, len(message) - 20 + 8)
    message += attr(0x8028, struct.pack('>I', (binascii.crc32(bytes(message)) & 0xFFFFFFFF) ^ FP_XOR))


def stun_request(tid: bytes, ufrag: str, pwd: bytes, controlled: bool = False) -> bytes:
    """ICE バインディング要求。

    アプリ実測（pair2.pcap）では **ICE-CONTROLLED（0x8029）で USE-CANDIDATE 無し**。
    こちらが CONTROLLING（0x802a＋USE-CANDIDATE）だとカメラが 400 を返す（実測）。
    """
    m = bytearray(struct.pack('>HHI', 1, 0, MAGIC) + tid)
    m += attr(0x0006, f'{ufrag}:{ufrag}'.encode())
    m += attr(0xC057, b'\x00\x01\x00\x00')
    if controlled:
        m += attr(0x8029, os.urandom(8))       # ICE-CONTROLLED
    else:
        m += attr(0x802A, os.urandom(8))       # ICE-CONTROLLING
        m += attr(0x0025, b'')                 # USE-CANDIDATE
    m += attr(0x0024, struct.pack('>I', CONTROLLING_PRIORITY))
    add_mi(m, pwd)
    add_fp(m)
    return bytes(m)


def stun_response(tid: bytes, peer: tuple[str, int], pwd: bytes) -> bytes:
    """カメラからの要求に対する応答（XOR-MAPPED-ADDRESS 付き）。"""
    m = bytearray(struct.pack('>HHI', 0x0101, 0, MAGIC) + tid)
    address, port = peer
    m += attr(0x0020, b'\0\1' + struct.pack('>H', port ^ (MAGIC >> 16))
              + struct.pack('>I', struct.unpack('>I', socket.inet_aton(address))[0] ^ MAGIC))
    add_mi(m, pwd)
    add_fp(m)
    return bytes(m)
