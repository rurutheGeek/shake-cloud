"""受信側の RTCP（RR＋REMB＋XR）を受信状況から組み立てる。

公式アプリは映像受信中、約 4 回/秒でカメラへ次の複合 RTCP を送っている
（pair2.pcap 実測。平文・メディア経路）:

  81c9 0007 <送信者 SSRC=1> <対象 SSRC> <損失率 1B+累積損失 3B> <拡張最大 seq>
            <ジッタ> <LSR> <DLSR>                              … RR（32B）
  8fce 0005 <1> <0> 'REMB' 01 <exp/mantissa 3B> <対象 SSRC>   … REMB（24B）
  80cf 0004 <1> 04 00 0002 <NTP 8B>                           … XR RRTR（20B）

拡張最大 seq はその時点で受信している映像の seq と一致する。固定値（過去の捕捉の
リプレイ）では受信が進んでいないように見え、カメラは十数秒で送出を止める
（と推定）。音声は送信者 SSRC ff79f011 の RR（＋XR ヘッダ）を別に送る。
"""

from __future__ import annotations

import struct
import time

VIDEO_SSRC = 0x0DC1A815
AUDIO_SSRC = 0x228448E9
AUDIO_REPORTER = 0xFF79F011
# アプリが出していた REMB 値（01 1a 9a 3e: exp=6, mantissa≈0x1a9a3e → 約 110Mbps 相当の上限）
REMB_BITRATE = bytes.fromhex('011a9a3e')
NTP_EPOCH = 2208988800


def ntp_now() -> tuple[int, int]:
    now = time.time()
    return int(now) + NTP_EPOCH, int((now % 1) * (1 << 32)) & 0xFFFFFFFF


class StreamStats:
    """1 SSRC 分の受信統計（拡張最大 seq と直近の SR）。"""

    def __init__(self) -> None:
        self.max_seq: int | None = None
        self.cycles = 0
        self.lsr = 0
        self.sr_at = 0.0

    def on_rtp(self, seq: int) -> None:
        if self.max_seq is None:
            self.max_seq = seq
            return
        delta = (seq - self.max_seq) & 0xFFFF
        if 0 < delta < 0x8000:
            if seq < self.max_seq:
                self.cycles += 1
            self.max_seq = seq

    def on_sr(self, packet: bytes) -> None:
        if len(packet) >= 16:
            self.lsr = struct.unpack('>I', packet[10:14])[0]
            self.sr_at = time.time()

    @property
    def extended(self) -> int:
        return ((self.cycles << 16) | (self.max_seq or 0)) & 0xFFFFFFFF

    def dlsr(self) -> int:
        if not self.sr_at:
            return 0
        return int((time.time() - self.sr_at) * 65536) & 0xFFFFFFFF

    def block(self, ssrc: int, jitter: int = 0x800) -> bytes:
        return struct.pack('>IIIIII', ssrc, 0, self.extended, jitter, self.lsr, self.dlsr())


class ReceiverReports:
    """カメラからのパケットを見て統計を取り、送る RTCP を作る。"""

    def __init__(self) -> None:
        self.video = StreamStats()
        self.audio = StreamStats()

    def observe(self, packet: bytes) -> None:
        if len(packet) < 12:
            return
        b0, b1 = packet[0], packet[1]
        if b1 == 0xC8 and (b0 & 0xC0) == 0x80:  # SR
            ssrc = struct.unpack('>I', packet[4:8])[0]
            (self.audio if ssrc == AUDIO_SSRC else self.video).on_sr(packet)
            return
        if (b0 & 0xC0) != 0x80 or 72 <= (b1 & 0x7F) <= 76:
            return
        ssrc = struct.unpack('>I', packet[8:12])[0]
        seq = struct.unpack('>H', packet[2:4])[0]
        pt = b1 & 0x7F
        if ssrc == VIDEO_SSRC and pt == 0x61 & 0x7F:
            self.video.on_rtp(seq)
        elif ssrc == AUDIO_SSRC:
            self.audio.on_rtp(seq)

    def video_report(self) -> bytes | None:
        if self.video.max_seq is None:
            return None
        rr = struct.pack('>HHI', 0x81C9, 7, 1) + self.video.block(VIDEO_SSRC)
        remb = struct.pack('>HHII', 0x8FCE, 5, 1, 0) + b'REMB' + REMB_BITRATE + struct.pack('>I', VIDEO_SSRC)
        sec, frac = ntp_now()
        xr = struct.pack('>HHIBBHII', 0x80CF, 4, 1, 4, 0, 2, sec, frac)
        return rr + remb + xr

    def audio_report(self) -> bytes | None:
        if self.audio.max_seq is None:
            return None
        rr = struct.pack('>HHI', 0x81C9, 7, AUDIO_REPORTER) + self.audio.block(AUDIO_SSRC)
        return rr + struct.pack('>HHI', 0x80CF, 4, AUDIO_REPORTER)
