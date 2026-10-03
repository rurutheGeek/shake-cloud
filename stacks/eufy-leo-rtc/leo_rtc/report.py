"""CS2 P2P の受信通知（DRWAck）の組立。

RE（libmega_media_sdk.so `cs2p2p_PPPP_DRWAck_Send` / `cs2p2p_PPPP_DRW_Write_Header`）:
  平文フレーム = `f1 d1 <BE16(count*2+4)> d1 <flag> <BE16(count)> <seq_i BE16>…`
  （Proto ヘッダ `f1 <cmd> <len BE16>` + DRW ヘッダ `d1 <flag> <count BE16>` + ack 列）。
  UDP へは CS2 固定鍵で暗号化して送る（アプリ実測と同一の暗号）。

注意: 実際のカメラが本通知をどう使うか（レート制御など）は未確定。送信経路は
メディア 5-tuple（`media_peer`）で、アプリは約 110 回/秒送っている。
"""

from __future__ import annotations

from . import cs2

DRW_MAGIC = 0xD1
MAX_SEQS = 82


def drw_ack(seqs, flag: int = 0) -> bytes:
    """DRWAck の平文フレームを組み立てる。"""
    seqs = list(seqs)[-MAX_SEQS:]
    body = bytes([DRW_MAGIC, flag]) + len(seqs).to_bytes(2, 'big')
    body += b''.join((s & 0xFFFF).to_bytes(2, 'big') for s in seqs)
    return b'\xf1\xd1' + len(body).to_bytes(2, 'big') + body


def enc_drw_ack(seqs, key: bytes = cs2.MEDIA_KEY, flag: int = 0) -> bytes:
    """CS2 暗号化済みの DRWAck フレーム（そのまま UDP へ送れる形）。"""
    return cs2.encrypt(drw_ack(seqs, flag), key)


def parse_drw_ack(frame: bytes):
    """平文 DRWAck を (flag, [seqs]) に分解する。"""
    if len(frame) < 8 or frame[0] != 0xF1 or frame[1] != 0xD1:
        raise ValueError('not a DRWAck frame')
    ln = int.from_bytes(frame[2:4], 'big')
    body = frame[4:4 + ln]
    if len(body) < 4 or body[0] != DRW_MAGIC:
        raise ValueError('bad DRWAck body')
    count = int.from_bytes(body[2:4], 'big')
    seqs = [int.from_bytes(body[4 + 2 * i:6 + 2 * i], 'big') for i in range(count)]
    return body[1], seqs
