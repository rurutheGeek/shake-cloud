"""The 86-byte sdp_info struct sent inside priv1/priv_p2p calls.

Reverse-engineered from WebrtcApp_SetCallSdp (channel+0x75d8, length 0x56).
It is a compact description of the client's ICE and media parameters:

  +0x00 u32  reserved (0)
  +0x04 u8   data channel flag (1)
  +0x05 u8   kcp flag (client config, 0 for the tested firmware)
  +0x06 [5]  ICE ufrag
  +0x0e [23] ICE pwd
  +0x26 [16] media AES key (crypto_key)
  +0x3a [12] media AES IV (crypto_iv)
  +0x46 [8]  zero padding
  +0x4e u32  random
  +0x52 u32  random

The struct is base64-encoded into the call JSON's "sdp_info" field. The media
keys are the ones the camera uses for the frame crypto (rtc_crypto.c); the ICE
fields are the client's ufrag/pwd for the WebRTC data channel.
"""

from __future__ import annotations

import os
import struct

SDP_INFO_LEN = 0x56
UFRAG_LEN = 5
PWD_LEN = 0x17
KEY_LEN = 0x10
IV_LEN = 0x0C


def build_sdp_info(
    *,
    data_channel: bool = True,
    kcp: int = 0,
    ufrag: bytes | None = None,
    pwd: bytes | None = None,
    crypto_key: bytes | None = None,
    crypto_iv: bytes | None = None,
    random32=None,
) -> bytes:
    """Build the sdp_info blob. Random values are generated when omitted."""
    random32 = os.urandom if random32 is None else random32

    def pick(value, length):
        value = os.urandom(length) if value is None else value
        if len(value) != length:
            raise ValueError(f'expected {length} bytes, got {len(value)}')
        return value

    buf = bytearray(SDP_INFO_LEN)
    struct.pack_into('<I', buf, 0x00, 0)
    # WebrtcApp_SetCallSdp sets +0x02, +0x03 and +0x04 to 1 for a
    # client-generated media key; +0x05 stays 0 in the tested firmware.
    buf[0x02] = 1 if data_channel else 0
    buf[0x03] = 1
    buf[0x04] = 1 if data_channel else 0
    buf[0x05] = kcp & 0xFF
    buf[0x06:0x06 + UFRAG_LEN] = pick(ufrag, UFRAG_LEN)
    buf[0x0E:0x0E + PWD_LEN] = pick(pwd, PWD_LEN)
    buf[0x26:0x26 + KEY_LEN] = pick(crypto_key, KEY_LEN)
    buf[0x3A:0x3A + IV_LEN] = pick(crypto_iv, IV_LEN)
    buf[0x4E:0x52] = random32(4)
    buf[0x52:0x56] = random32(4)
    return bytes(buf)


def parse_sdp_info(blob: bytes) -> dict:
    """Split an sdp_info blob into its fields (for tests and logs)."""
    if len(blob) != SDP_INFO_LEN:
        raise ValueError(f'sdp_info must be {SDP_INFO_LEN} bytes')
    return {
        'data_channel': blob[0x04] != 0,
        'kcp': blob[0x05],
        'ufrag': blob[0x06:0x0B],
        'pwd': blob[0x0E:0x25],
        'crypto_key': blob[0x26:0x36],
        'crypto_iv': blob[0x3A:0x46],
    }
