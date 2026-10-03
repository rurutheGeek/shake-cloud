"""XZYH + AES-128-GCM のコマンド封筒（leo_rtc メディア/制御層）。

実測（2026-09-27/28）:
- KCP 版: `XZYH` + `<cmd LE16>` + `<総長 LE32>` + `[0x0a,0,0,1,0,0]` + `[tag 16]` +
  `[iv 12]` + `<counter LE32>` + `[暗号文]`。AAD は `"eufy security"`。
- メディア（ANKExV4）版: 同じだが counter 無し。ライブ開始の 1003（cmd 0x546）はこの形。
"""

from __future__ import annotations

import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b'eufy security'
XZYH = b'XZYH'
CMD_HEADER_TAIL = bytes([0x0A, 0, 0, 1, 0, 0])
TAG_LEN = 16
IV_LEN = 12


def build_command_frame(command: int, plain: bytes, key: bytes, counter: int,
                        iv: bytes | None = None) -> bytes:
    """KCP チャネル用のコマンド封筒（counter 付き）。"""
    iv = os.urandom(IV_LEN) if iv is None else iv
    sealed = AESGCM(key).encrypt(iv, plain, AAD)
    tag, ct = sealed[-TAG_LEN:], sealed[:-TAG_LEN]
    return (XZYH + struct.pack('<H', command) + struct.pack('<I', len(ct) + TAG_LEN)
            + CMD_HEADER_TAIL + tag + iv + struct.pack('<I', counter) + ct)


def build_media_frame(command: int, plain: bytes, key: bytes, iv: bytes | None = None) -> bytes:
    """メディアチャネル用のコマンド封筒（counter なし）。"""
    iv = os.urandom(IV_LEN) if iv is None else iv
    sealed = AESGCM(key).encrypt(iv, plain, AAD)
    tag, ct = sealed[-TAG_LEN:], sealed[:-TAG_LEN]
    return (XZYH + struct.pack('<H', command) + struct.pack('<I', len(ct) + TAG_LEN)
            + CMD_HEADER_TAIL + tag + iv + ct)


def parse_frame(frame: bytes, *, with_counter: bool = True) -> dict:
    """封筒を分解する（暗号文は復号しない）。counter の有無は呼び出し側が指定する。"""
    if len(frame) < 16 or frame[:4] != XZYH:
        raise ValueError('not an XZYH frame')
    command = struct.unpack_from('<H', frame, 4)[0]
    total = struct.unpack_from('<I', frame, 6)[0]
    body = frame[16:]
    if len(body) < total:
        raise ValueError('truncated XZYH frame')
    tag = body[:TAG_LEN]
    iv = body[TAG_LEN:TAG_LEN + IV_LEN]
    rest = body[TAG_LEN + IV_LEN:]
    if with_counter:
        counter = struct.unpack_from('<I', rest, 0)[0]
        ct = rest[4:]
    else:
        counter = None
        ct = rest
    return {'command': command, 'tag': tag, 'iv': iv, 'counter': counter, 'ciphertext': ct}


def decrypt_frame(frame: bytes, key: bytes, *, with_counter: bool = True) -> bytes:
    """封筒を復号して平文を返す。"""
    parsed = parse_frame(frame, with_counter=with_counter)
    return AESGCM(key).decrypt(parsed['iv'], parsed['ciphertext'] + parsed['tag'], AAD)
