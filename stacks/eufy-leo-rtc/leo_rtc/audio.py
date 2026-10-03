"""音声ストリームの再構成（leo_rtc メディア層）。

実測（2026-09-29）:
- 音声は映像とは別の RTP ストリーム: `90 ef`（PT=111）・SSRC `228448e9`・ヘッダ 20 バイト
  （RTP 12B + 拡張 4B `bede 0001` + 拡張データ 4B）。RTP タイムスタンプは 3072 刻み
  （16kHz で 192ms = 3 個の ADTS フレーム）。
- ペイロードは IDR と同じ AES-128-GCM（鍵 = セッションの `crypto_key`、IV = `crypto_iv`、
  AAD なし、`ct=body[:-25]`・`tag=body[-25:-9]`）。平文は ADTS（`ff f1`）の AAC-LC。
"""

from __future__ import annotations

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AUDIO_RTP_HEADER_LEN = 20
AUDIO_RTP_MAGIC = b"\x90\xef"
AUDIO_SSRC = bytes.fromhex("228448e9")
AUDIO_TAG_LEN = 16
AUDIO_TRAILER_LEN = 9
ADTS_SYNC = b"\xff\xf1"


def parse_audio_rtp(packet: bytes) -> tuple[int, int, bytes]:
    """音声 RTP パケットを (seq, timestamp, payload) に分解する。"""
    if len(packet) < AUDIO_RTP_HEADER_LEN or packet[:2] != AUDIO_RTP_MAGIC:
        raise ValueError("not a leo_rtc audio packet")
    seq = int.from_bytes(packet[2:4], "big")
    ts = int.from_bytes(packet[4:8], "big")
    return seq, ts, packet[AUDIO_RTP_HEADER_LEN:]


def decrypt_audio(payload: bytes, key: bytes, iv: bytes) -> bytes:
    """音声ペイロードを復号して ADTS バイト列を返す。"""
    for trailer in (AUDIO_TRAILER_LEN,) + tuple(t for t in range(0, 33) if t != AUDIO_TRAILER_LEN):
        end = len(payload) - trailer
        if end < AUDIO_TAG_LEN + 1:
            continue
        ct = payload[: end - AUDIO_TAG_LEN]
        tag = payload[end - AUDIO_TAG_LEN : end]
        try:
            return AESGCM(key).decrypt(iv, ct + tag, b"")
        except Exception:
            continue
    raise ValueError("audio decrypt failed (tag mismatch)")


def adts_info(frame: bytes) -> dict:
    """ADTS ヘッダ（7 バイト）を解析する。"""
    if len(frame) < 7 or frame[:2] != ADTS_SYNC:
        raise ValueError("not an ADTS frame")
    profile = (frame[2] >> 6) & 0x3
    sf_index = (frame[2] >> 2) & 0xF
    channels = ((frame[2] & 0x1) << 2) | ((frame[3] >> 6) & 0x3)
    return {
        "profile": profile,
        "sampling_frequency_index": sf_index,
        "sample_rate": (96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050,
                        16000, 12000, 11025, 8000, 7350, 0, 0, 0)[sf_index],
        "channels": channels,
    }
