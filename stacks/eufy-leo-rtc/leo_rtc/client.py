"""Native leo_rtc signaling client.

This is the reverse-engineered client used to wake and negotiate a live stream
with a standalone eufy battery camera (eufyCam S4 / T8172). It talks the same
UDP protocol as the mobile app's libmega_media_sdk.so to the camera's
signaling servers.

Scope: discover, login, call (including the wake fields) and the info/hangup
exchanges. Media transport (WebRTC SDP/ICE, DTLS/SCTP or SRTP, H.264) is not
implemented yet; see docs/development/H05-eufy-leo-rtc.md.

Safety: this client never logs in with the Eufy account. It uses the camera's
device id and license, so it does not invalidate the eufy-security-ws session.
Do not put DID/license values in Git or logs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import socket
import struct
import time
from dataclasses import dataclass, field

from . import crypto, protocol
from .sdpinfo import build_sdp_info


class LeoRtcError(RuntimeError):
    pass


# The EU signaling host from the camera's cloud record. The discover response
# returns the concrete server_addr; this default only bootstraps discovery.
DEFAULT_SIGNAL_HOST = 'webrtc-signal-eu.eufylife.com'


@dataclass
class Message:
    type: int
    code: int
    response: int
    body_type: int
    seq: int
    timestamp: int
    body: bytes
    attach: bytes = b''
    attach_plain: bytes = b''
    attach_json: dict | None = None
    reserved: int = 0
    flag: int = 0
    header_len: int = protocol.HEADER_LEN
    crc_ok: bool = True
    raw_header: bytes = b''

    @property
    def type_name(self) -> str:
        return protocol.TYPE_NAMES.get(self.type, f'type_{self.type}')

    def call_body(self) -> protocol.CallBody | None:
        if self.body_type != protocol.BODY_CALL:
            return None
        try:
            return protocol.CallBody.parse(self.body)
        except ValueError:
            return None

    @property
    def uuid(self) -> str:
        return self.body[6:0x2A].split(b'\0')[0].decode(errors='replace')

    @property
    def candidate(self) -> str | None:
        """The device's ICE candidate from a file_candidate info message."""
        if not self.attach_json:
            return None
        return self.attach_json.get('file_candidate')

    @property
    def candidate_num(self) -> int | None:
        if not self.attach_json:
            return None
        return self.attach_json.get('file_candidate_num')


@dataclass
class Session:
    server_addr: str
    session_key: bytes
    contact: str
    seq: int
    route: int
    candidates: list[str] = field(default_factory=list)


class LeoRtcClient:
    def __init__(
        self,
        sn: str,
        did: str,
        license: str,
        *,
        account: str = '',
        host: str | None = None,
        port: int = 5062,
        timeout: float = 5.0,
    ):
        if not sn or not did or not license:
            raise ValueError('sn, did and license are required')
        self.sn = sn
        self.did = did
        self.license = license
        self.account = account
        self.explicit_host = host
        self.host = host or DEFAULT_SIGNAL_HOST
        self.port = port
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)
        self.route = random.randrange(1, 256)
        self.seq = 0
        self.session: Session | None = None

    # -- plumbing ---------------------------------------------------------
    def close(self):
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _next_seq(self) -> int:
        self.seq = (self.seq + 1) & 0xFF
        return self.seq

    def send(self, inner: bytes, host: str | None = None):
        target = host or self.host
        if not target:
            raise LeoRtcError('no signaling host')
        self.sock.sendto(protocol.obfuscate(inner), (target, self.port))

    def recv(self, timeout: float | None = None) -> Message | None:
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            packet, _ = self.sock.recvfrom(8192)
        except socket.timeout:
            return None
        inner = protocol.deobfuscate(packet)
        if inner is None:
            # Some firmware relays its signaling messages without the
            # obfuscation envelope and with the 0x3b-byte header (H05).
            if len(packet) < 0x3B or struct.unpack_from('<H', packet, 0)[0] != protocol.PROTOCOL_VERSION:
                return None
            inner = packet
        try:
            parsed = protocol.parse_header(inner)
        except ValueError:
            return None
        message = Message(
            type=parsed['type'],
            code=parsed['code'],
            response=parsed['response'],
            body_type=parsed['body_type'],
            seq=parsed['seq'],
            timestamp=parsed['timestamp'],
            body=parsed['body'],
            reserved=parsed['reserved'],
            flag=parsed['net_type'],
            header_len=parsed['header_len'],
            crc_ok=parsed['crc_ok'],
            raw_header=parsed.get('raw_header', b''),
        )
        call_body = message.call_body()
        if call_body is not None and call_body.attach:
            message.attach = call_body.attach
            if self.session is not None:
                message.attach_plain = self.decrypt_attach_plain(call_body.attach, message.timestamp)
                message.attach_json = self._json_from_plain(message.attach_plain)
        return message

    # -- crypto helpers ---------------------------------------------------
    def encrypt_attach(self, payload: bytes, packet_id: int) -> bytes:
        if self.session is None:
            raise LeoRtcError('login first')
        return crypto.aes_ecb_encrypt(payload, crypto.derive_aes_key(self.session.session_key, packet_id))

    def decrypt_attach_plain(self, attach: bytes, packet_id: int) -> bytes:
        """Decrypt an attach; returns b'' when it cannot be decrypted."""
        if self.session is None:
            return b''
        try:
            plain = crypto.aes_ecb_decrypt(attach, crypto.derive_aes_key(self.session.session_key, packet_id))
        except Exception:
            return b''
        return plain.rstrip(b'\0')

    @staticmethod
    def _json_from_plain(plain: bytes) -> dict | None:
        # AES-ECB pads with zeros and the sender may leave a few random bytes
        # after the JSON, so decode the first JSON value instead of the whole
        # buffer.
        text = plain.decode(errors='ignore')
        start = text.find('{')
        if start < 0:
            return None
        try:
            value, _ = json.JSONDecoder().raw_decode(text[start:])
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def decrypt_attach(self, attach: bytes, packet_id: int) -> dict | None:
        return self._json_from_plain(self.decrypt_attach_plain(attach, packet_id))

    # -- protocol steps ---------------------------------------------------
    def discover(self) -> dict:
        self.send(protocol.build_discover(int(time.time()), self._next_seq(), self.route, self.sn))
        message = self.recv()
        if message is None or message.code != 200:
            raise LeoRtcError(f'discover failed: {message and message.code}')
        try:
            payload = json.loads(message.body.split(b'\0')[0])
        except ValueError as error:
            raise LeoRtcError('discover body is not JSON') from error
        if not self.explicit_host:
            self.host = payload.get('server_addr') or self.host
        candidates = [payload.get('server_addr')] + list(payload.get('saddrs', []))
        self.discover_response = payload
        self.call_hosts = [host for host in candidates if host]
        return payload

    def login(self) -> Session:
        if not getattr(self, 'call_hosts', None):
            self.discover()
        self.send(protocol.build_header(protocol.TYPE_LOGIN, int(time.time()), self._next_seq(), self.route, contact=self.sn))
        challenge = self.recv()
        if challenge is None or challenge.code != 0x191 or challenge.body_type != protocol.BODY_LOGIN_CHALLENGE:
            raise LeoRtcError(f'login challenge failed: {challenge and challenge.code}')
        # The server occasionally re-challenges right after a reply (for example
        # when a previous session for the same SN is still being torn down), so
        # answer up to three challenges before giving up.
        result = None
        for _ in range(3):
            packet_id = challenge.timestamp
            modulus = crypto.decrypt_challenge(challenge.body, packet_id)
            session_key = ''.join(
                random.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(16)
            ).encode()
            body = crypto.login_reply(session_key, packet_id, self.did, self.license, modulus)
            reply = protocol.build_header(
                protocol.TYPE_LOGIN,
                int(time.time()),
                self._next_seq(),
                self.route,
                contact=self.sn,
                body=body,
                body_type=protocol.BODY_LOGIN_REPLY,
            )
            self.send(reply)
            result = self.recv()
            if result is not None and result.code == 200:
                break
            if result is not None and result.code == 0x191 and result.body_type == protocol.BODY_LOGIN_CHALLENGE:
                challenge = result
                continue
            break
        if result is None or result.code != 200:
            raise LeoRtcError(f'login failed: {result and result.code}')
        contact = result.body[:32].split(b'\0')[0].decode(errors='replace')
        self.session = Session(
            server_addr=self.host,
            session_key=session_key,
            contact=contact,
            seq=self.seq,
            route=self.route,
            candidates=list(getattr(self, 'call_hosts', [])),
        )
        return self.session

    def build_call_json(self, call_type: int, contact: str, timestamp: int, *, boot_action: int = 0, sdp_info: bytes | None = None) -> dict:
        usec = int(time.time() * 1_000_000)
        account = hashlib.md5(f'0{self.account}{int(time.time())}'.encode()).hexdigest()
        token = base64.b64encode(
            self.encrypt_attach(f'{self.did}:{self.license}'.encode(), timestamp)
        ).decode()
        if call_type == protocol.CALL_PRIV1:
            call_name, p2p_type = 'scall', 'priv1'
        elif call_type == protocol.CALL_PRIV_P2P:
            call_name, p2p_type = 'call', 'priv_p2p'
        elif call_type == protocol.CALL_CHANNEL_P2P:
            call_name, p2p_type = 'call', 'channel_p2p'
        elif call_type == protocol.CALL_FILE_P2P:
            call_name, p2p_type = 'call', 'file_p2p'
        else:
            call_name, p2p_type = 'call', 'priv1'
        payload = {
            'account': account,
            'ftv': 20,
            'call_type': call_name,
            'eufy_p2p_type': p2p_type,
            'to': 'device',
            'eufy_from_contact': contact,
            'eufy_video_format': 2,
            'eufy_network_type': 1,
            'eufy_app_id': '',
            'token': token,
        }
        if sdp_info is not None:
            payload['sdp_info'] = base64.b64encode(sdp_info).decode()
        if call_type == protocol.CALL_PRIV_P2P and boot_action:
            payload['boot_action'] = boot_action
        return payload

    def call(
        self,
        call_type: int,
        *,
        boot_action: int = 0,
        wakeup_type: int = 0,
        sdp_info: bytes | None = None,
        hosts: list[str] | None = None,
    ) -> str:
        if self.session is None:
            self.login()
        timestamp = int(time.time())
        payload = self.build_call_json(call_type, self.session.contact, timestamp, boot_action=boot_action, sdp_info=sdp_info)
        attach = self.encrypt_attach(json.dumps(payload, separators=(',', ':')).encode(), timestamp)
        uuid = protocol.call_uuid(call_type, self.sn, self.did, self.license, int(time.time() * 1_000_000))
        body = protocol.CallBody(uuid=uuid, contact=self.session.contact, attach=attach, reserved=wakeup_type).build()
        message = protocol.build_header(
            protocol.TYPE_CALL,
            timestamp,
            self._next_seq(),
            self.route,
            contact=self.sn,
            body=body,
            body_type=protocol.BODY_CALL,
            net_type=1,
            encrypted=1,
        )
        for host in hosts or self.session.candidates or [self.host]:
            self.send(message, host)
        return uuid

    def wake(self, *, boot_action: int = 1, wakeup_type: int = 1, sdp_info: bytes | None = None) -> dict:
        """Send the priv1 scall that wakes a sleeping camera.

        The camera answers 100 then 200 with its address and TURN credentials
        (see H05). Returns the first 200 reply, or raises when none arrives.
        """
        sdp_info = build_sdp_info() if sdp_info is None else sdp_info
        uuid = self.call(protocol.CALL_PRIV1, boot_action=boot_action, wakeup_type=wakeup_type, sdp_info=sdp_info)
        deadline = time.time() + self.timeout * 6
        while time.time() < deadline:
            message = self.recv(timeout=max(0.5, deadline - time.time()))
            if message is None:
                continue
            if message.type == protocol.TYPE_CALL and message.code == 200:
                return {'uuid': uuid, 'message': message}
        raise LeoRtcError('no 200 answer to the wake call')

    def info(self, uuid: str, payload: dict | str, *, flag: int = 0) -> None:
        if self.session is None:
            raise LeoRtcError('login first')
        timestamp = int(time.time())
        raw = payload if isinstance(payload, str) else json.dumps(payload, separators=(',', ':'))
        attach = self.encrypt_attach(raw.encode(), timestamp)
        body = protocol.CallBody(uuid=uuid, contact=self.session.contact, attach=attach).build()
        message = protocol.build_header(
            protocol.TYPE_INFO,
            timestamp,
            self._next_seq(),
            self.route,
            contact=self.sn,
            body=body,
            body_type=protocol.BODY_CALL,
            net_type=1,
            encrypted=1,
        )
        self.send(message)

    def ack_info(self, message: Message) -> None:
        """Answer a device info request with the app's info 200 echo.

        ClientHandleInfo rebuilds the request header (resp=1, code=200), keeps
        the first 0x4c body bytes (uuid/contact) and re-encrypts the same
        decrypted attach with a fresh timestamp, then sends it twice 15ms
        apart. The device retransmits its candidates until it is answered.
        """
        if self.session is None:
            raise LeoRtcError('login first')
        if not message.attach_plain:
            return
        timestamp = int(time.time())
        attach = self.encrypt_attach(message.attach_plain, timestamp)
        body = bytearray(message.body[:0x4C])
        struct.pack_into('<H', body, 0x04, len(attach))
        body += attach
        reply = protocol.build_header(
            protocol.TYPE_INFO,
            timestamp,
            self._next_seq(),
            self.route,
            contact=self.sn,
            body=bytes(body),
            body_type=protocol.BODY_CALL,
            response=1,
            code=200,
            net_type=message.flag,
            encrypted=1,
        )
        self.send(reply)
        time.sleep(0.015)
        self.send(reply)

    def collect_candidates(self, uuid: str, *, timeout: float = 30.0) -> list[str]:
        """Read and ACK info requests until no new ICE candidate arrives."""
        candidates: list[str] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = self.recv(timeout=max(0.5, deadline - time.time()))
            if message is None:
                continue
            if message.type != protocol.TYPE_INFO or message.response != 0:
                continue
            # The firmware's session uuid can be longer than the 0x24-byte app
            # field; match on the call-type prefix instead of the full value.
            if not message.uuid.startswith(uuid[:5]):
                continue
            self.ack_info(message)
            if message.candidate is not None:
                candidates.append(message.candidate)
        return candidates

    def hangup(self, uuid: str) -> None:
        if self.session is None:
            raise LeoRtcError('login first')
        body = protocol.CallBody(uuid=uuid, contact=self.session.contact).build()
        message = protocol.build_header(
            protocol.TYPE_HANGUP,
            int(time.time()),
            self._next_seq(),
            self.route,
            contact=self.sn,
            body=body,
            body_type=protocol.BODY_CALL,
            net_type=1,
            encrypted=1,
        )
        self.send(message)
