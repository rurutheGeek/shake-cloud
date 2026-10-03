"""ライブ映像の RTP/FU 再構成（leo_rtc メディア層）。

- カメラ→アプリの映像パケットは RTP（V=2・PT=97・SSRC `0dc1a815`・拡張 `0xbede`）。
  ヘッダは 24 バイト（RTP 12B + 拡張 4B + 拡張データ 8B）。同じパケットが約 3 重複して届く。
- 各フレームの最終 FU 断片はマーカービット付き（byte1 = 0xE1、PT は 97 のまま）で届く。
  これを見落とすと全フレームの末尾断片が欠落し、デコードがゴースト化する。
- ペイロードは RFC 7798 の FU（PayloadHdr `62 01` = type 49、次 1 バイトが S/E/元 NAL 種別）。
- **I スライス（IDR, type 19/20）だけが E2E 暗号化**されている（P スライスは平文）。
  方式はパラメータセットと同じ AES-128-GCM（AAD なし、鍵 = セッションの `crypto_key`、
  IV = `crypto_iv`）。ワイヤ形式は `[ct][tag 16B][トレーラ 9B]`（`decrypt_idr` で復号）。
- VPS/SPS/PPS はこのストリームには含まれないため、実測値（アプリのデコード済み
  バッファから取得）を `HEVC_PARAMETER_SETS` として持つ。
"""

from __future__ import annotations

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RTP_HEADER_LEN = 24
RTP_MAGIC = b"\x90\x61"
RTP_MARKER_MAGIC = b"\x90\xe1"
FU_NAL_TYPE = 49
IDR_NAL_TYPES = (19, 20)
IDR_TAG_LEN = 16
IDR_TRAILER_LEN = 9
HEVC_PARAMETER_SETS = bytes.fromhex(
    "0000000140010c01ffff014000000300800000030000030099ac09"
    "00000001420101014000000300800000030000030099a001502005f1636b92cad9ae5c4dc14041410000030001000003000f3f8b1280"
    "000000014401c0e123c0cc90"
)


def parse_rtp(packet: bytes) -> tuple[int, int, bytes, bytes]:
    """RTP パケットを (seq, timestamp, ssrc, payload) に分解する。"""
    if len(packet) < RTP_HEADER_LEN or packet[:2] not in (RTP_MAGIC, RTP_MARKER_MAGIC):
        raise ValueError("not a leo_rtc media RTP packet")
    seq = int.from_bytes(packet[2:4], "big")
    ts = int.from_bytes(packet[4:8], "big")
    ssrc = packet[8:12]
    return seq, ts, ssrc, packet[RTP_HEADER_LEN:]


class Depacketizer:
    """FU 断片をフレーム単位で連結し、完成した NAL を返す。

    カメラは報告（0xce レポート等）に応じて同じパケットを再送するため、重複は
    **連続とは限らない**。(seq, ts) の最近傍セットで重複除去する。
    """

    DEDUP_WINDOW = 512

    def __init__(self) -> None:
        self._seen: set[tuple[int, int]] = set()
        self._seen_order: list[tuple[int, int]] = []
        self._ts: int | None = None
        self._type = 0
        self._hdr = b""
        self._buf = bytearray()
        self.incomplete = 0

    def _finish(self) -> bytes:
        nal = bytes([(self._hdr[0] & 0x81) | ((self._type << 1) & 0x7E), self._hdr[1]]) + bytes(self._buf)
        self._ts = None
        self._buf = bytearray()
        return nal

    def _is_duplicate(self, seq: int, ts: int) -> bool:
        key = (seq, ts)
        if key in self._seen:
            return True
        self._seen.add(key)
        self._seen_order.append(key)
        if len(self._seen_order) > self.DEDUP_WINDOW:
            self._seen.discard(self._seen_order.pop(0))
        return False

    def feed(self, packet: bytes) -> list[bytes]:
        """RTP パケット 1 個を入力し、完成した NAL のリストを返す。"""
        seq, ts, _ssrc, pl = parse_rtp(packet)
        if self._is_duplicate(seq, ts):
            return []
        if len(pl) < 3:
            return []
        out: list[bytes] = []
        nal_type = (pl[0] >> 1) & 0x3F
        if nal_type != FU_NAL_TYPE:
            if self._buf and ts != self._ts:
                out.append(self._finish())
            out.append(pl)
            return out
        fu = pl[2]
        if fu & 0x80:
            if self._buf:
                out.append(self._finish())
            self._ts, self._type, self._hdr = ts, fu & 0x3F, pl[0:2]
            self._buf = bytearray(pl[3:])
        elif self._buf and self._ts == ts:
            self._buf += pl[3:]
        else:
            self.incomplete += 1
            return out
        if fu & 0x40:
            out.append(self._finish())
        return out

    def flush(self) -> list[bytes]:
        """最後の未確定フレームを締め切って返す。"""
        return [self._finish()] if self._buf else []


def to_annexb(nals: list[bytes], *, parameters: bytes = HEVC_PARAMETER_SETS) -> bytes:
    """NAL 列を（先頭にパラメータセットを付けて）Annex B 形式へ変換する。"""
    out = bytearray(parameters)
    for nal in nals:
        out += b"\x00\x00\x00\x01"
        out += nal
    return bytes(out)


def decrypt_idr(nal: bytes, key: bytes, iv: bytes) -> bytes:
    """E2E 暗号化された IDR NAL を復号して返す（P スライスはそのまま渡してよい）。

    ワイヤ形式: `[NAL ヘッダ 2B][ct][GCM タグ 16B][トレーラ 9B]`。
    暗号はパラメータセットと同じ AES-128-GCM（AAD なし、鍵 = セッションの crypto_key、
    IV = crypto_iv）。トレーラ長は実測 9 バイトだが、念のため 0〜32 を順に試す。
    """
    nal_type = (nal[0] >> 1) & 0x3F
    if nal_type not in IDR_NAL_TYPES:
        return nal
    body = nal[2:]
    for trailer in (IDR_TRAILER_LEN,) + tuple(t for t in range(0, 33) if t != IDR_TRAILER_LEN):
        end = len(body) - trailer
        if end < IDR_TAG_LEN + 1:
            continue
        ct = body[: end - IDR_TAG_LEN]
        tag = body[end - IDR_TAG_LEN : end]
        try:
            pt = AESGCM(key).decrypt(iv, ct + tag, b"")
        except Exception:
            continue
        return bytes([(nal[0] & 0x81) | ((nal_type << 1) & 0x7E), nal[1]]) + pt
    raise ValueError("IDR decrypt failed (tag mismatch)")


def decrypt_parameter_nal(nal: bytes, key: bytes, iv: bytes) -> bytes:
    """ワイヤのパラメータセット（VPS/SPS/PPS）を復号する。

    ワイヤ形式: `[NAL ヘッダ 2B][ct][GCM タグ 16B]`（IDR と違いトレーラは無い）。
    """
    if len(nal) < 2 + IDR_TAG_LEN + 1:
        raise ValueError("parameter NAL too short")
    ct = nal[2:-IDR_TAG_LEN]
    tag = nal[-IDR_TAG_LEN:]
    pt = AESGCM(key).decrypt(iv, ct + tag, b"")
    return bytes([nal[0], nal[1]]) + pt
