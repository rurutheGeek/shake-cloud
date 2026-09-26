"""leo_rtc signaling protocol framing.

Reverse-engineered from libmega_media_sdk.so (`RTC/src/webrtc/rtc_protocol.c`).
The wire format is a 0x3c-byte little-endian header followed by an optional
body. UDP packets are wrapped in an obfuscation envelope (ProtocolSetObfuscate
Header) and the whole inner message is XORed with a 16-byte key.

Everything here is pure framing. Crypto lives in crypto.py, the session state
machine in client.py.
"""

from __future__ import annotations

import os
import random
import struct
from dataclasses import dataclass

PROTOCOL_VERSION = 3
HEADER_LEN = 0x3C
BODY_CALL = 7
BODY_LOGIN_CHALLENGE = 3
BODY_LOGIN_REPLY = 4
OBFUSCATED = 2

TYPE_LOGIN = 1
TYPE_CALL = 2
TYPE_ACK = 3
TYPE_INFO = 4
TYPE_HANGUP = 5
TYPE_UPDATE = 6
TYPE_WAKEUP = 7
TYPE_REPORT = 8
TYPE_DISCOVER = 9
TYPE_PING = 10
TYPE_MESSAGE = 0x0B
TYPE_LOGOUT = 0x0C
TYPE_CONTROL = 0x0D

TYPE_NAMES = {
    TYPE_LOGIN: 'login',
    TYPE_CALL: 'call',
    TYPE_ACK: 'ack',
    TYPE_INFO: 'info',
    TYPE_HANGUP: 'hangup',
    TYPE_UPDATE: 'update',
    TYPE_WAKEUP: 'wakeup',
    TYPE_REPORT: 'report',
    TYPE_DISCOVER: 'discover',
    TYPE_PING: 'ping',
    TYPE_MESSAGE: 'message',
    TYPE_LOGOUT: 'logout',
    TYPE_CONTROL: 'control',
}

# call_type values used by ClientSendCall.
CALL_PLAIN = 0
CALL_CMD = 1
CALL_CHANNEL_P2P = 3
CALL_FILE_P2P = 4
CALL_PRIV1 = 5
CALL_PRIV_P2P = 6

# CRC16/XMODEM table as used by rtc_protocol.c.
_CRC_TABLE = (
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
)


def crc16(data: bytes, crc: int = 0) -> int:
    for byte in data:
        crc = (_CRC_TABLE[((crc >> 12) ^ (byte >> 4)) & 0xF] ^ ((crc << 4) & 0xFFFF)) & 0xFFFF
        crc = (_CRC_TABLE[((crc >> 12) ^ (byte & 0xF)) & 0xF] ^ ((crc << 4) & 0xFFFF)) & 0xFFFF
    return crc


def obfuscate(inner: bytes, key: bytes | None = None, pad: int | None = None) -> bytes:
    """Wrap an inner message in the UDP obfuscation envelope."""
    key = os.urandom(16) if key is None else key
    if len(key) != 16:
        raise ValueError('obfuscation key must be 16 bytes')
    pad = random.randrange(256) if pad is None else pad
    out = bytearray(0x16 + len(inner) + pad)
    struct.pack_into('<H', out, 0, 8)
    struct.pack_into('<H', out, 2, len(inner) + pad)
    out[4:0x14] = key
    out[0x14] = pad
    out[0x15] = random.randrange(256)
    for i, byte in enumerate(inner):
        out[0x16 + i] = byte ^ key[i & 0xF]
    for i in range(pad):
        out[0x16 + len(inner) + i] = os.urandom(1)[0]
    return bytes(out)


def deobfuscate(packet: bytes) -> bytes | None:
    """Strip the obfuscation envelope; None when the packet is not obfuscated."""
    if len(packet) < 0x16 or struct.unpack_from('<H', packet, 0)[0] != 8:
        return None
    total = struct.unpack_from('<H', packet, 2)[0]
    key, pad = packet[4:0x14], packet[0x14]
    inner_len = total - pad
    if inner_len < 0 or 0x16 + inner_len > len(packet):
        return None
    return bytes(packet[0x16 + i] ^ key[i & 0xF] for i in range(inner_len))


def build_header(
    msg_type: int,
    timestamp: int,
    seq: int,
    route: int,
    *,
    client_id: int = 6,
    contact: str = '',
    body: bytes = b'',
    body_type: int = 0,
    response: int = 0,
    code: int = 0,
    net_type: int = 0,
    encrypted: int = 0,
    reserved: int = 0,
) -> bytes:
    """Build an inner message header (and append `body`)."""
    header = bytearray(HEADER_LEN)
    struct.pack_into('<H', header, 0x00, PROTOCOL_VERSION)
    struct.pack_into('<H', header, 0x04, msg_type)
    struct.pack_into('<H', header, 0x06, len(body))
    struct.pack_into('<I', header, 0x08, timestamp)
    header[0x0C] = 7
    header[0x0D] = client_id & 0xFF
    header[0x0E] = response & 0xFF
    header[0x0F] = net_type & 0xFF
    struct.pack_into('<H', header, 0x10, code)
    header[0x12] = encrypted & 0xFF
    encoded = contact.encode()
    if len(encoded) > 0x10:
        raise ValueError('contact must fit in 16 bytes')
    header[0x14:0x14 + len(encoded)] = encoded
    header[0x28] = 0x14
    header[0x29] = body_type & 0xFF
    header[0x2A] = seq & 0xFF
    header[0x2B] = route & 0xFF
    header[0x2C] = reserved & 0xFF
    struct.pack_into('<H', header, 0x39, 0x0300)
    header[0x3B] = OBFUSCATED
    struct.pack_into('<H', header, 0x02, crc16(bytes(header[4:HEADER_LEN]) + body))
    return bytes(header) + body


def detect_header_len(inner: bytes) -> int:
    """Return the wire header size (0x3c for the app, 0x3b for some firmware).

    The device firmware writes the body one byte earlier; the body length in
    the header is the reliable discriminator (H05, 2026-09-23).
    """
    if len(inner) < HEADER_LEN:
        return HEADER_LEN
    body_len = struct.unpack_from('<H', inner, 0x06)[0]
    if len(inner) - 0x3B == body_len:
        return 0x3B
    return HEADER_LEN


def parse_header(inner: bytes, header_len: int | None = None) -> dict:
    """Parse an inner message. Raises ValueError when it is too short."""
    if header_len is None:
        header_len = detect_header_len(inner)
    if len(inner) < header_len:
        raise ValueError('inner message shorter than header')
    body_len = struct.unpack_from('<H', inner, 0x06)[0]
    body = inner[header_len:header_len + body_len]
    return {
        'version': struct.unpack_from('<H', inner, 0x00)[0],
        'type': struct.unpack_from('<H', inner, 0x04)[0],
        'body_len': body_len,
        'timestamp': struct.unpack_from('<I', inner, 0x08)[0],
        'client_id': inner[0x0D],
        'response': inner[0x0E],
        'net_type': inner[0x0F],
        'code': struct.unpack_from('<H', inner, 0x10)[0],
        'encrypted': inner[0x12],
        'contact': inner[0x14:0x24].split(b'\0')[0].decode(errors='replace'),
        'body_type': inner[0x29],
        'seq': inner[0x2A],
        'route': inner[0x2B],
        'reserved': inner[0x2C],
        'crc_ok': struct.unpack_from('<H', inner, 0x02)[0] == crc16(inner[4:header_len] + body),
        'body': body,
        'header_len': header_len,
        'raw_header': inner[:header_len],
    }


@dataclass
class CallBody:
    """Body of a call/ack/hangup message (ProtocolSetCallBody2)."""

    param: int = 0
    uuid: str = ''
    contact: str = ''
    attach: bytes = b''
    no_attach: bool = False
    reserved: int = 0

    def build(self) -> bytes:
        attach = self.attach
        if len(attach) > 0xFFFF:
            raise ValueError('attach too long')
        body = bytearray(0x4C + len(attach))
        struct.pack_into('<I', body, 0x00, self.param)
        struct.pack_into('<H', body, 0x04, len(attach))
        # ProtocolSetCallBody2 caps uuid at 0x24 and contact at 0x20 bytes; the
        # 37-char uuid produced by ClientSendCall is truncated by the contact.
        uid = self.uuid.encode()[:0x24]
        body[0x06:0x06 + len(uid)] = uid
        contact = self.contact.encode()[:0x20]
        body[0x2A:0x2A + len(contact)] = contact
        body[0x4A] = 1 if (self.no_attach or not attach) else 0
        body[0x4B] = self.reserved & 0xFF
        body[0x4C:] = attach
        return bytes(body)

    @classmethod
    def parse(cls, body: bytes) -> 'CallBody':
        if len(body) < 0x4C:
            raise ValueError('call body too short')
        attach_len = struct.unpack_from('<H', body, 0x04)[0]
        attach = body[0x4C:0x4C + attach_len]
        if len(attach) != attach_len:
            raise ValueError('call body attach truncated')
        return cls(
            param=struct.unpack_from('<I', body, 0x00)[0],
            uuid=body[0x06:0x2A].split(b'\0')[0].decode(errors='replace'),
            contact=body[0x2A:0x4A].split(b'\0')[0].decode(errors='replace'),
            attach=attach,
            no_attach=body[0x4A] != 0,
            reserved=body[0x4B],
        )


def build_discover(timestamp: int, seq: int, route: int, sn: str) -> bytes:
    return build_header(TYPE_DISCOVER, timestamp, seq, route, contact=sn)


def call_uuid(call_type: int, sn: str, did: str, license: str, usec: int) -> str:
    """ClientSendCall's uuid, truncated to the 0x24-byte wire field.

    ClientSendCall builds "FF00<call_type><md5(...)>" (37 chars) but
    ProtocolSetCallBody2 copies only 36 bytes, so the last md5 character never
    reaches the wire. The truncated value is what the server echoes back.
    """
    import hashlib

    digest = hashlib.md5(f'{sn}{did}{license}{usec}{call_type}'.encode()).hexdigest()
    return (f'FF00{call_type}{digest}')[:0x24]
