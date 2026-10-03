"""TURN（RFC 5766）クライアント。UDP ソケットと同じ形（sendto/recvfrom）で使う。

公式アプリはメディアを eufy の TURN（call 応答の `turn` の資格）経由で受けている
（pair2.pcap: 映像 24,198 パケットはすべて 75.2.46.73:3478 の ChannelData）。
カメラの直経路は約 11 秒で止まるため、同じく中継経由で受ける。

- Allocate は長期資格（USERNAME/REALM/NONCE/MESSAGE-INTEGRITY）で行う。
- 宛先ごとに CreatePermission を張り、データを受けた相手には ChannelBind する。
- 受信は ChannelData（0x4000〜0x7FFF）と Data indication（0x0017）を剥がして返す。
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import socket
import struct
import time

MAGIC = 0x2112A442
ALLOCATE, REFRESH, SEND, DATA, PERMISSION, CHANNEL_BIND = 0x0003, 0x0004, 0x0016, 0x0017, 0x0008, 0x0009


def _attr(kind: int, value: bytes) -> bytes:
    return struct.pack('>HH', kind, len(value)) + value + b'\0' * ((-len(value)) % 4)


def xor_address(address: str, port: int) -> bytes:
    raw = struct.unpack('>I', socket.inet_aton(address))[0] ^ MAGIC
    return b'\0\1' + struct.pack('>HI', port ^ (MAGIC >> 16), raw)


def parse_xor_address(value: bytes) -> tuple[str, int]:
    port = struct.unpack('>H', value[2:4])[0] ^ (MAGIC >> 16)
    raw = struct.unpack('>I', value[4:8])[0] ^ MAGIC
    return socket.inet_ntoa(struct.pack('>I', raw)), port


def parse_attrs(message: bytes) -> dict[int, bytes]:
    out: dict[int, bytes] = {}
    length = struct.unpack('>H', message[2:4])[0]
    i = 20
    end = min(len(message), 20 + length)
    while i + 4 <= end:
        kind, ln = struct.unpack('>HH', message[i:i + 4])
        out.setdefault(kind, message[i + 4:i + 4 + ln])
        i += 4 + ln + ((-ln) % 4)
    return out


class TurnError(RuntimeError):
    pass


class TurnSocket:
    """TURN 中継を UDP ソケットのように扱う。"""

    def __init__(self, server: tuple[str, int], user: str, password: str, bind_ip: str = '0.0.0.0'):
        self.server = server
        self.user = user.encode()
        self.password = password.encode()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        except OSError:
            pass
        self.sock.bind((bind_ip, 0))
        self.realm = b''
        self.nonce = b''
        self.key = b''
        self.relayed: tuple[str, int] | None = None
        self.mapped: tuple[str, int] | None = None
        self.permissions: dict[str, float] = {}
        self.channels: dict[tuple[str, int], int] = {}
        self.by_channel: dict[int, tuple[str, int]] = {}
        self.next_channel = 0x4001
        self.timeout = 0.05
        self.refreshed = 0.0

    # --- 送受信の下回り -------------------------------------------------
    def settimeout(self, value: float) -> None:
        self.timeout = value

    def getsockname(self):
        return self.sock.getsockname()

    def fileno(self) -> int:
        return self.sock.fileno()

    def _request(self, method: int, attrs: bytes, auth: bool = True) -> bytes:
        tid = os.urandom(12)
        body = bytearray(attrs)
        if auth and self.key:
            body += _attr(0x0006, self.user) + _attr(0x0014, self.realm) + _attr(0x0015, self.nonce)
        message = bytearray(struct.pack('>HHI', method, len(body), MAGIC) + tid + body)
        if auth and self.key:
            struct.pack_into('>H', message, 2, len(body) + 24)
            message += _attr(0x0008, hmac.new(self.key, bytes(message), hashlib.sha1).digest())
        return bytes(message)

    def _transact(self, method: int, attrs: bytes, retry_auth: bool = True) -> dict[int, bytes]:
        request = self._request(method, attrs)
        tid = request[8:20]
        deadline = time.time() + 3.0
        self.sock.settimeout(1.0)
        while time.time() < deadline:
            self.sock.sendto(request, self.server)
            try:
                data, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            if len(data) < 20 or data[8:20] != tid:
                continue  # 中継データや別の応答は取引中は捨てる
            kind = struct.unpack('>H', data[:2])[0]
            attrs_in = parse_attrs(data)
            if kind == method | 0x0100:
                return attrs_in
            if kind == method | 0x0110:
                code = attrs_in.get(0x0009, b'\0\0\0\0')
                number = code[2] * 100 + code[3]
                if number in (401, 438) and retry_auth:
                    self.realm = attrs_in.get(0x0014, self.realm)
                    self.nonce = attrs_in.get(0x0015, self.nonce)
                    self.key = hashlib.md5(self.user + b':' + self.realm + b':' + self.password).digest()
                    return self._transact(method, attrs, retry_auth=False)
                raise TurnError('TURN %#x failed: %d %r' % (method, number, code[4:]))
        raise TurnError('TURN %#x timed out' % method)

    # --- TURN 操作 -------------------------------------------------------
    def allocate(self) -> tuple[str, int]:
        request = _attr(0x0019, b'\x11\0\0\0') + _attr(0x000D, struct.pack('>I', 600))
        try:
            attrs = self._transact(ALLOCATE, request)
        except TurnError as error:
            # 437: 再送の行き違いで同じ 5-tuple に別の割当がある。ポートを変えて取り直す。
            if ': 437 ' not in str(error):
                raise
            bind_ip = self.sock.getsockname()[0]
            self.sock.close()
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            except OSError:
                pass
            self.sock.bind((bind_ip, 0))
            attrs = self._transact(ALLOCATE, request)
        self.relayed = parse_xor_address(attrs[0x0016])
        if 0x0020 in attrs:
            self.mapped = parse_xor_address(attrs[0x0020])
        self.refreshed = time.time()
        return self.relayed

    def refresh(self) -> None:
        self._transact(REFRESH, _attr(0x000D, struct.pack('>I', 600)))
        self.refreshed = time.time()

    def permit(self, address: str) -> None:
        self._transact(PERMISSION, _attr(0x0012, xor_address(address, 0)))
        self.permissions[address] = time.time()

    def bind_channel(self, peer: tuple[str, int]) -> int:
        number = self.next_channel
        self._transact(CHANNEL_BIND, _attr(0x000C, struct.pack('>HH', number, 0))
                       + _attr(0x0012, xor_address(*peer)))
        self.next_channel += 1
        self.channels[peer] = number
        self.by_channel[number] = peer
        return number

    def maintain(self) -> None:
        """許可（5 分）と割当（600 秒）を切らさない。"""
        now = time.time()
        if now - self.refreshed > 240:
            try:
                self.refresh()
            except TurnError as error:
                print('turn refresh failed:', error)
        for address, stamp in list(self.permissions.items()):
            if now - stamp > 240:
                try:
                    self.permit(address)
                except TurnError:
                    pass

    # --- ソケット互換 -----------------------------------------------------
    def sendto(self, data: bytes, peer: tuple[str, int]) -> int:
        address, port = peer
        if ipaddress.ip_address(address).is_private:
            return len(data)  # 中継は LAN の宛先へ届かない
        if address not in self.permissions:
            try:
                self.permit(address)
            except TurnError as error:
                print('turn permission failed:', address, error)
                self.permissions[address] = time.time()
        number = self.channels.get(peer)
        if number is not None:
            self.sock.sendto(struct.pack('>HH', number, len(data)) + data, self.server)
        else:
            body = _attr(0x0012, xor_address(address, port)) + _attr(0x0013, data)
            self.sock.sendto(struct.pack('>HHI', SEND, len(body), MAGIC) + os.urandom(12) + body, self.server)
        return len(data)

    def recvfrom(self, _size: int = 65535):
        self.sock.settimeout(self.timeout)
        data, _ = self.sock.recvfrom(65535)  # socket.timeout はそのまま上げる
        first = struct.unpack('>H', data[:2])[0] if len(data) >= 2 else 0
        if 0x4000 <= first <= 0x7FFF and len(data) >= 4:
            peer = self.by_channel.get(first)
            ln = struct.unpack('>H', data[2:4])[0]
            if peer is not None:
                return data[4:4 + ln], peer
        elif first == DATA and len(data) >= 20:
            attrs = parse_attrs(data)
            if 0x0012 in attrs and 0x0013 in attrs:
                peer = parse_xor_address(attrs[0x0012])
                if peer not in self.channels:
                    try:
                        self.bind_channel(peer)
                        print('turn channel bound', peer)
                    except TurnError as error:
                        print('turn channel bind failed:', error)
                return attrs[0x0013], peer
        raise socket.timeout()


class DualSocket:
    """直経路の UDP ソケットと TURN 中継を 1 つのソケットに見せる。

    宛先が LAN なら直経路、それ以外は中継で送る。受信は両方を待つ。
    カメラがどちらの候補を選んでも映像を受けられるようにする。
    """

    def __init__(self, direct: socket.socket, turn: TurnSocket):
        self.direct = direct
        self.turn = turn
        self.timeout = 0.05
        self.counts = {'direct': 0, 'turn': 0}

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def getsockname(self):
        return self.direct.getsockname()

    def sendto(self, data: bytes, peer: tuple[str, int]) -> int:
        if ipaddress.ip_address(peer[0]).is_private:
            return self.direct.sendto(data, peer)
        return self.turn.sendto(data, peer)

    def recvfrom(self, size: int = 65535):
        import select
        ready, _, _ = select.select([self.direct, self.turn.sock], [], [], self.timeout)
        if self.direct in ready:
            self.direct.settimeout(0)
            try:
                got = self.direct.recvfrom(size)
                self.counts['direct'] += 1
                return got
            except (BlockingIOError, socket.timeout):
                pass
        if self.turn.sock in ready:
            self.turn.timeout = 0.001
            got = self.turn.recvfrom(size)
            self.counts['turn'] += 1
            return got
        raise socket.timeout()
