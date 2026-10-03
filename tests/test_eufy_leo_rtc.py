"""Offline checks for the native leo_rtc client.

What breaks without these: the framing/CRC would not match the camera's
protocol (the camera silently drops packets), the login key derivation would
fail (no session), or secrets/credentials would leak into Git.
"""

import importlib.util
from pathlib import Path
import struct
import sys
import unittest

from cryptography.hazmat.primitives.asymmetric import padding, rsa


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/eufy-leo-rtc'


def load_package():
    sys.path.insert(0, str(STACK))
    for name in list(sys.modules):
        if name == 'leo_rtc' or name.startswith('leo_rtc.'):
            del sys.modules[name]
    return importlib.import_module('leo_rtc')


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.leo = load_package()
        self.protocol = self.leo.protocol

    def test_crc16_matches_the_xmodem_check_value(self):
        self.assertEqual(self.protocol.crc16(b'123456789'), 0x31C3)

    def test_obfuscation_round_trips_and_ignores_plain_packets(self):
        inner = b'\x00' * 0x3C + b'payload'
        packet = self.protocol.obfuscate(inner, key=b'0123456789abcdef', pad=7)
        self.assertEqual(self.protocol.deobfuscate(packet), inner)
        self.assertIsNone(self.protocol.deobfuscate(inner))

    def test_header_round_trips_with_body_and_crc(self):
        body = self.protocol.CallBody(uuid='FF005abc', contact='contact-1', attach=b'x' * 32).build()
        header = self.protocol.build_header(
            self.protocol.TYPE_CALL, 1790172749, 7, 42, contact='T8172P102603060C', body=body,
            body_type=self.protocol.BODY_CALL, net_type=1, encrypted=1,
        )
        parsed = self.protocol.parse_header(header)
        self.assertTrue(parsed['crc_ok'])
        self.assertEqual(parsed['type'], self.protocol.TYPE_CALL)
        self.assertEqual(parsed['seq'], 7)
        self.assertEqual(parsed['route'], 42)
        self.assertEqual(parsed['body'], body)
        self.assertEqual(parsed['contact'], 'T8172P102603060C')

    def test_call_body_carries_the_wakeup_reserved_byte(self):
        body = self.protocol.CallBody(uuid='FF005abc', contact='c', attach=b'y' * 16, reserved=3).build()
        parsed = self.protocol.CallBody.parse(body)
        self.assertEqual(parsed.reserved, 3)
        self.assertEqual(parsed.attach, b'y' * 16)
        self.assertEqual(parsed.uuid, 'FF005abc')
        self.assertFalse(parsed.no_attach)

    def test_device_messages_with_the_shorter_header_are_detected(self):
        # Some firmware writes the body one byte earlier (0x3b). The body length
        # is the discriminator; without this, the whole device reply is dropped.
        body = self.protocol.CallBody(uuid='FF005abc', contact='contact-1', attach=b'z' * 16).build()
        packet = bytearray(self.protocol.build_header(
            self.protocol.TYPE_INFO, 1790176646, 76, 103, contact='T8172P102603060C', body=body,
        ))
        del packet[0x3B]  # drop the obfuscation-flag byte used by the app header
        packet[0x0F] = 0
        struct.pack_into('<H', packet, 0x02, self.protocol.crc16(bytes(packet[4:0x3B]) + body))
        parsed = self.protocol.parse_header(bytes(packet))
        self.assertEqual(parsed['header_len'], 0x3B)
        self.assertTrue(parsed['crc_ok'])
        self.assertEqual(parsed['body'], body)

    def test_call_uuid_matches_the_client_send_call_format(self):
        uid = self.protocol.call_uuid(5, 'SN', 'DID', 'LIC', 123)
        self.assertEqual(uid[:5], 'FF005')
        self.assertEqual(len(uid), 0x24)
        body = self.protocol.CallBody(uuid=uid, contact='c' * 32).build()
        self.assertEqual(body[0x06:0x2A].decode(), uid)


class CryptoTests(unittest.TestCase):
    def setUp(self):
        self.leo = load_package()
        self.crypto = self.leo.crypto

    def test_key_derivation_embeds_the_packet_id_in_the_last_digits(self):
        key = self.crypto.derive_aes_key(self.crypto.DEFAULT_KEY, 1790172749)
        self.assertEqual(key, b'&#%@!_1790172749')

    def test_challenge_decrypts_to_the_server_modulus(self):
        packet_id = 1790172749
        modulus = int('F' * 256, 16)
        challenge = (f'{modulus:0256X}').encode() + b'\0' * 16
        body = self.crypto.aes_ecb_encrypt(challenge, self.crypto.derive_aes_key(self.crypto.DEFAULT_KEY, packet_id))
        self.assertEqual(self.crypto.decrypt_challenge(body, packet_id), modulus)

    def test_login_reply_carries_the_session_key_and_token(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        modulus = private.private_numbers().public_numbers.n
        session_key = b'abcdefghijklmnop'
        token_plain = b'DID:LIC'
        aes_len = 48  # アプリは token を 48 バイトにパディングする
        body = self.crypto.login_reply(session_key, 1234, 'DID', 'LIC', modulus)
        rsa_ct = body[:-2 - aes_len]
        length = int.from_bytes(body[len(rsa_ct):len(rsa_ct) + 2], 'little')
        self.assertEqual(length, aes_len)
        recovered = private.decrypt(rsa_ct, padding.PKCS1v15())
        self.assertEqual(recovered, session_key)
        token = self.crypto.aes_ecb_decrypt(
            body[-aes_len:], self.crypto.derive_aes_key(session_key, 1234),
        ).rstrip(b'\0')
        self.assertEqual(token, token_plain)


class SdpInfoTests(unittest.TestCase):
    def setUp(self):
        self.leo = load_package()

    def test_sdp_info_has_the_documented_layout(self):
        blob = self.leo.build_sdp_info(
            ufrag=b'ABCDE', pwd=b'P' * 23, crypto_key=b'K' * 16, crypto_iv=b'I' * 12,
            random32=lambda n: b'R' * n,
        )
        self.assertEqual(len(blob), 0x56)
        parsed = self.leo.sdpinfo.parse_sdp_info(blob)
        self.assertTrue(parsed['data_channel'])
        self.assertEqual(parsed['ufrag'], b'ABCDE')
        self.assertEqual(parsed['pwd'], b'P' * 23)
        self.assertEqual(parsed['crypto_key'], b'K' * 16)
        self.assertEqual(parsed['crypto_iv'], b'I' * 12)

    def test_sdp_info_is_random_by_default(self):
        self.assertNotEqual(self.leo.build_sdp_info(), self.leo.build_sdp_info())


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.leo = load_package()
        self.client = self.leo.LeoRtcClient('SN', 'DID', 'LIC', account='USER')

    def tearDown(self):
        self.client.close()

    def test_call_json_sets_boot_action_only_for_priv_p2p(self):
        self.client.session = self.leo.Session('host', b'0123456789abcdef', 'contact', 0, 1)
        priv1 = self.client.build_call_json(
            self.leo.CALL_PRIV1, 'contact', 1234, boot_action=2, sdp_info=b'\0' * 0x56)
        priv_p2p = self.client.build_call_json(
            self.leo.CALL_PRIV_P2P, 'contact', 1234, boot_action=2, sdp_info=b'\0' * 0x56)
        self.assertNotIn('boot_action', priv1)
        self.assertEqual(priv_p2p['boot_action'], 2)
        self.assertEqual(priv1['eufy_p2p_type'], 'priv1')
        self.assertEqual(priv1['call_type'], 'scall')
        self.assertEqual(priv_p2p['eufy_p2p_type'], 'priv_p2p')
        self.assertEqual(len(priv1['sdp_info']), 4 * ((0x56 + 2) // 3))

    def test_attach_encrypts_and_decrypts_with_the_session_key(self):
        self.client.session = self.leo.Session('host', b'0123456789abcdef', 'contact', 0, 1)
        attach = self.client.encrypt_attach(b'{"a":1}', 42)
        self.assertEqual(self.client.decrypt_attach(attach, 42), {'a': 1})

    def test_attach_decoder_ignores_zero_padding_and_trailing_bytes(self):
        # The camera pads with zeros and appends a few random bytes after the
        # JSON; a strict json.loads would drop the whole answer.
        self.client.session = self.leo.Session('host', b'0123456789abcdef', 'contact', 0, 1)
        attach = self.client.encrypt_attach(b'{"sdp":"x"}\x00\x00\xad\x16', 42)
        self.assertEqual(self.client.decrypt_attach(attach, 42), {'sdp': 'x'})

    def test_ack_info_echoes_the_body_and_attach_as_a_response(self):
        # The device retransmits its ICE candidates until the app answers with
        # an info 200 that echoes the body and the same JSON attach.
        self.client.session = self.leo.Session('host', b'0123456789abcdef', 'contact', 0, 1)
        body = self.leo.protocol.CallBody(
            uuid='FF005dev', contact='contact', attach=b'x' * 16).build()
        header = self.leo.protocol.build_header(
            self.leo.TYPE_INFO, 42, 3, 9, contact='T8172P102603060C', body=body,
            body_type=self.leo.protocol.BODY_CALL, encrypted=1)
        sent = []
        self.client.send = lambda inner, host=None: sent.append(inner)
        message = None
        # reconstruct the Message the same way recv() does
        parsed = self.leo.protocol.parse_header(header)
        message = self.leo.Message(type=parsed['type'], code=parsed['code'], response=parsed['response'],
                                   body_type=parsed['body_type'], seq=parsed['seq'],
                                   timestamp=parsed['timestamp'], body=parsed['body'])
        message.attach_plain = b'{"file_candidate":"a=candidate:1 1 UDP 1 192.168.10.98 1 typ host"}'
        self.client.ack_info(message)
        self.assertEqual(len(sent), 2)
        reply = self.leo.protocol.parse_header(sent[0])
        self.assertEqual(reply['response'], 1)
        self.assertEqual(reply['code'], 200)
        self.assertEqual(reply['body'][6:0x4C], body[6:0x4C])  # uuid/contact/flags
        echoed = self.client.decrypt_attach(reply['body'][0x4C:], reply['timestamp'])
        self.assertEqual(echoed, {'file_candidate': 'a=candidate:1 1 UDP 1 192.168.10.98 1 typ host'})


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.leo = load_package()

    def test_offer_sdp_carries_the_recovered_sdes_key_and_codecs(self):
        sdp = self.leo.build_offer_sdp('abcd', 'pwd', candidates=(
            'a=candidate:1 1 udp 2130706431 192.168.10.203 5000 typ host',))
        self.assertIn(f'inline:{self.leo.SRTP_KEY}', sdp)
        self.assertIn('a=rtpmap:99 H264/90000', sdp)
        self.assertIn('a=rtpmap:97 H265/90000', sdp)
        self.assertIn('a=ice-ufrag:abcd', sdp)
        self.assertIn('typ host', sdp)
        self.assertNotIn('a=fingerprint', sdp)  # SDES, not DTLS-SRTP


class SafetyTests(unittest.TestCase):
    def test_example_env_has_no_device_credentials(self):
        text = (STACK / '.env.example').read_text(encoding='utf-8')
        for line in text.splitlines():
            if line.startswith(('EUFY_DID=', 'EUFY_LICENSE=', 'EUFY_ACCOUNT=')):
                self.assertEqual(line.split('=', 1)[1], '', line)
        self.assertNotIn('EUFY_PASSWORD', text)

    def test_client_never_reads_account_credentials(self):
        source = (STACK / 'leo_rtc/client.py').read_text(encoding='utf-8')
        for needle in ('EUFY_PASSWORD', 'EUFY_USERNAME', 'password'):
            self.assertNotIn(needle, source)


if __name__ == '__main__':
    unittest.main()


class Cs2Tests(unittest.TestCase):
    """CS2 P2P 独自暗号（アプリ実測 pcap の既知ベクタで検証）。"""

    def test_known_app_packet_roundtrip(self):
        from leo_rtc import cs2

        ct = bytes.fromhex(
            'b0ce000672bb000100d86448002001c601060dc1a8153e2502010001b0ce0007'
        )
        pt = cs2.decrypt(ct)
        self.assertTrue(pt.startswith(b'\xf1\xce'))
        self.assertEqual((pt[2] << 8) | pt[3], 0x47)
        self.assertEqual(cs2.encrypt(pt), ct)

    def test_keepalive_frames_parse(self):
        from leo_rtc import media_channel as mc

        ka = mc.build_keepalive(0x11223344, 0)
        self.assertEqual(ka[:8], b'\x9e\xcc\x00\x07\x11\x22\x33\x44')
        self.assertEqual(ka[8:16], mc.MEDIA_MAGIC)
        got = mc.parse_ank(ka)
        self.assertIsNotNone(got)
        ssrc, counter, frame = got
        self.assertEqual((ssrc, counter, frame), (0x11223344, 0, b''))


class VideoReassemblyTests(unittest.TestCase):
    """ライブ映像の RTP/FU 再構成（実機のパケット構造で検証）。"""

    def setUp(self):
        load_package()
        from leo_rtc import video

        self.video = video

    def rtp(self, seq, ts, payload, ssrc=b'\x0d\xc1\xa8\x15'):
        return (b'\x90\x61' + struct.pack('>H', seq) + struct.pack('>I', ts)
                + ssrc + b'\xbe\xde\x00\x02' + b'\x00' * 8 + payload)

    def test_parse_rtp_reads_header_fields(self):
        pkt = self.rtp(0x1234, 0x00e381f4, b'\x62\x01\x13rest')
        seq, ts, ssrc, payload = self.video.parse_rtp(pkt)
        self.assertEqual((seq, ts, ssrc), (0x1234, 0x00e381f4, b'\x0d\xc1\xa8\x15'))
        self.assertEqual(payload, b'\x62\x01\x13rest')

    def test_fu_fragments_reassemble_to_one_nal(self):
        dep = self.video.Depacketizer()
        first = self.rtp(1, 100, b'\x62\x01\x93' + b'AAAA')
        mid = self.rtp(2, 100, b'\x62\x01\x13' + b'BB')
        last = self.rtp(3, 100, b'\x62\x01\x53' + b'CC')
        self.assertEqual(dep.feed(first), [])
        self.assertEqual(dep.feed(mid), [])
        nals = dep.feed(last)
        self.assertEqual(len(nals), 1)
        self.assertEqual(nals[0], b'\x26\x01' + b'AAAABBCC')

    def test_duplicate_packets_are_ignored(self):
        dep = self.video.Depacketizer()
        pkt = self.rtp(7, 55, b'\x4e\x01\x05Hello')
        self.assertEqual(dep.feed(pkt), [b'\x4e\x01\x05Hello'])
        self.assertEqual(dep.feed(pkt), [])

    def test_marker_bit_packet_is_accepted(self):
        pkt = b'\x90\xe1' + self.rtp(3, 100, b'\x62\x01\x41CC')[2:]
        seq, ts, _ssrc, payload = self.video.parse_rtp(pkt)
        self.assertEqual((seq, ts), (3, 100))
        self.assertEqual(payload, b'\x62\x01\x41CC')

    def test_marker_bit_final_fragment_reassembles(self):
        dep = self.video.Depacketizer()
        self.assertEqual(dep.feed(self.rtp(1, 100, b'\x62\x01\x93' + b'AAAA')), [])
        last = b'\x90\xe1' + self.rtp(2, 100, b'\x62\x01\x53' + b'CC')[2:]
        self.assertEqual(dep.feed(last), [b'\x26\x01' + b'AAAACC'])

    def test_interleaved_duplicates_are_ignored(self):
        dep = self.video.Depacketizer()
        a = self.rtp(1, 100, b'\x62\x01\x93' + b'AAAA')
        b = self.rtp(2, 100, b'\x62\x01\x13' + b'BB')
        self.assertEqual(dep.feed(a), [])
        self.assertEqual(dep.feed(b), [])
        self.assertEqual(dep.feed(a), [])  # 再送（間に別パケットが挟まる重複）
        nals = dep.feed(self.rtp(3, 100, b'\x62\x01\x53' + b'CC'))
        self.assertEqual(nals, [b'\x26\x01' + b'AAAABBCC'])
        self.assertEqual(dep.incomplete, 0)

    def test_late_retransmission_does_not_corrupt_next_frame(self):
        dep = self.video.Depacketizer()
        self.assertEqual(dep.feed(self.rtp(1, 100, b'\x62\x01\x93' + b'AAAA')), [])
        self.assertEqual(dep.feed(self.rtp(2, 100, b'\x62\x01\x53' + b'CC')), [b'\x26\x01' + b'AAAACC'])
        # 前フレームの再送が次フレームの後に届いても無視される
        self.assertEqual(dep.feed(self.rtp(1, 100, b'\x62\x01\x93' + b'AAAA')), [])
        self.assertEqual(dep.feed(self.rtp(3, 200, b'\x4e\x01\x05SEI')), [b'\x4e\x01\x05SEI'])

    def test_annexb_starts_with_valid_parameter_sets(self):
        stream = self.video.to_annexb([b'\x26\x01slicedata'])
        self.assertTrue(stream.startswith(b'\x00\x00\x00\x01\x40\x01'))
        self.assertIn(b'\x00\x00\x00\x01\x42\x01', stream)
        self.assertIn(b'\x00\x00\x00\x01\x44\x01', stream)
        self.assertIn(b'\xff\xff', stream[:16])
        self.assertTrue(stream.endswith(b'\x00\x00\x00\x01\x26\x01slicedata'))

    def test_decrypt_idr_round_trip(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = b'Wtd312vgUx5AEEhE'
        iv = b'K' * 12
        pt = b'\xaf\x1f\x80' + bytes(range(64))
        blob = AESGCM(key).encrypt(iv, pt, b'')
        wire = b'\x26\x01' + blob + b'\x1e\x00\x00\x00\x00\x00\x00\x00\x00'
        out = self.video.decrypt_idr(wire, key, iv)
        self.assertEqual(out, b'\x26\x01' + pt)

    def test_decrypt_idr_passes_through_p_slice(self):
        nal = b'\x02\x01\xd0\x00\x0d\x8c' + b'x' * 8
        self.assertEqual(self.video.decrypt_idr(nal, b'k' * 16, b'i' * 12), nal)

    def test_decrypt_idr_rejects_bad_key(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        blob = AESGCM(b'key-aaaaaaaaaaaa').encrypt(b'i' * 12, b'\xaf\x1f\x80abc', b'')
        wire = b'\x26\x01' + blob + b'\x00' * 9
        with self.assertRaises(ValueError):
            self.video.decrypt_idr(wire, b'key-bbbbbbbbbbbb', b'i' * 12)

    def test_decrypt_parameter_nal_round_trip(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = b'Wtd312vgUx5AEEhE'
        iv = b'K' * 12
        pt = bytes.fromhex('0c01ffff014000000300800000030000030099ac09')
        wire = b'\x40\x01' + AESGCM(key).encrypt(iv, pt, b'')
        out = self.video.decrypt_parameter_nal(wire, key, iv)
        self.assertEqual(out, b'\x40\x01' + pt)


class AudioTests(unittest.TestCase):
    """音声ストリーム（別 RTP・ADTS AAC・IDR と同じ暗号）。"""

    def setUp(self):
        load_package()
        from leo_rtc import audio

        self.audio = audio

    def pkt(self, seq, ts, payload):
        return (b'\x90\xef' + struct.pack('>H', seq) + struct.pack('>I', ts)
                + bytes.fromhex('228448e9') + b'\xbe\xde\x00\x01' + b'\x92\x00\x64\x00'
                + payload)

    def test_parse_audio_rtp_reads_header_fields(self):
        seq, ts, payload = self.audio.parse_audio_rtp(self.pkt(3, 0x0c00, b'body'))
        self.assertEqual((seq, ts), (3, 0x0c00))
        self.assertEqual(payload, b'body')

    def test_decrypt_audio_round_trip(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = b'Wtd312vgUx5AEEhE'
        iv = b'K' * 12
        adts = b'\xff\xf1\x60\x40' + bytes(range(32))
        wire = AESGCM(key).encrypt(iv, adts, b'') + b'\x1e\x00\x00\x00\x00\x00\x00\x00\x00'
        self.assertEqual(self.audio.decrypt_audio(wire, key, iv), adts)

    def test_adts_info_parses_aac_lc_16k_mono(self):
        info = self.audio.adts_info(b'\xff\xf1\x60\x40' + b'\x00' * 4)
        self.assertEqual(info['profile'], 1)
        self.assertEqual(info['sample_rate'], 16000)
        self.assertEqual(info['channels'], 1)

    def test_adts_info_rejects_non_adts(self):
        with self.assertRaises(ValueError):
            self.audio.adts_info(b'\x00' * 8)


class HeartbeatTests(unittest.TestCase):
    """1139 心拍（XZYH 0x473）の組立。

    アプリは KCP で約 0.62 秒ごとに送る。落とすとセッションが早く終わる可能性が
    あるため、バイト列を実測（pair2.pcap）どおりに固定する。
    """

    def setUp(self):
        self.leo = load_package()

    def test_heartbeat_matches_the_capture(self):
        from leo_rtc import media_channel as mc
        blob = mc.build_heartbeat(0x8555, 0x6ABB3C2E)
        self.assertEqual(len(blob), 36)
        self.assertEqual(blob[:20], bytes.fromhex('1000000001000000 2e3cbb6a 01000000 55850000'.replace(' ', '')))
        self.assertEqual(blob[20:], bytes.fromhex('585a5948730400000000000000000000'))

    def test_heartbeat_sequence_is_little_endian(self):
        from leo_rtc import media_channel as mc
        blob = mc.build_heartbeat(1, 2)
        self.assertEqual(int.from_bytes(blob[16:20], 'little'), 1)
        self.assertEqual(int.from_bytes(blob[8:12], 'little'), 2)


class EnvelopeTests(unittest.TestCase):
    """XZYH + AES-128-GCM のコマンド封筒。"""

    def setUp(self):
        load_package()
        from leo_rtc import envelope

        self.env = envelope
        self.key = b'Wtd312vgUx5AEEhE'

    def test_command_frame_round_trip(self):
        plain = b'{"cmd":1003}'
        frame = self.env.build_command_frame(0x546, plain, self.key, 7)
        self.assertEqual(frame[:4], b'XZYH')
        self.assertEqual(struct.unpack_from('<H', frame, 4)[0], 0x546)
        self.assertEqual(self.env.decrypt_frame(frame, self.key, with_counter=True), plain)
        parsed = self.env.parse_frame(frame, with_counter=True)
        self.assertEqual(parsed['counter'], 7)

    def test_media_frame_has_no_counter(self):
        plain = b'{"cmd":1003}'
        frame = self.env.build_media_frame(0x546, plain, self.key)
        parsed = self.env.parse_frame(frame, with_counter=False)
        self.assertIsNone(parsed['counter'])
        self.assertEqual(self.env.decrypt_frame(frame, self.key, with_counter=False), plain)

    def test_rejects_bad_magic(self):
        with self.assertRaises(ValueError):
            self.env.parse_frame(b'XXXX' + b'\0' * 20)


class IceTests(unittest.TestCase):
    """ICE（STUN）メッセージの組立。"""

    def setUp(self):
        load_package()
        from leo_rtc import ice

        self.ice = ice

    def test_binding_request_has_controlling_and_use_candidate(self):
        tid = bytes(range(12))
        req = self.ice.stun_request(tid, 'pMUM2', b'p2p-password-23-byte!!!')
        self.assertEqual(req[0:2], b'\x00\x01')
        self.assertEqual(int.from_bytes(req[4:8], 'big'), self.ice.MAGIC)
        self.assertEqual(req[8:20], tid)
        for kind in (0x0006, 0xC057, 0x802A, 0x0024, 0x0025, 0x0008, 0x8028):
            self.assertIn(struct.pack('>H', kind), req)

    def test_response_xor_mapped_address_round_trip(self):
        tid = bytes(range(12))
        resp = self.ice.stun_response(tid, ('192.168.10.98', 37921), b'p2p-password-23-byte!!!')
        self.assertEqual(resp[0:2], b'\x01\x01')
        self.assertIn(struct.pack('>H', 0x0020), resp)


class KcpTests(unittest.TestCase):
    """KCP チャネルの送受信。"""

    def setUp(self):
        load_package()
        from leo_rtc import kcp

        self.kcp = kcp

    class FakeSock:
        def __init__(self):
            self.sent = []

        def sendto(self, data, peer):
            self.sent.append((data, peer))

    def test_push_builds_a_0x51_header(self):
        # アプリ実測のワイヤ: 32B 接頭辞（末尾 4B は 01 00 00 00）＋20B ヘッダ
        #（cmd/frg/wnd/ts/sn/una/len）＋ペイロード。以前は余分な u32 があった。
        sock = self.FakeSock()
        ch = self.kcp.KcpChannel(sock, ('127.0.0.1', 1))
        sn = ch.push(b'XZYHpayload')
        self.assertEqual(sn, 0)
        data, _peer = sock.sent[0]
        self.assertEqual(len(data), 32 + 20 + 11)
        self.assertEqual(data[28:32], b'\x01\x00\x00\x00')
        self.assertEqual(data[32], 0x51)
        self.assertEqual(struct.unpack_from('<H', data, 34)[0], 0x0200)  # wnd
        self.assertEqual(struct.unpack_from('<I', data, 40)[0], 0)       # sn
        self.assertEqual(data[52:], b'XZYHpayload')

    def test_push_auto_increments_sn(self):
        sock = self.FakeSock()
        ch = self.kcp.KcpChannel(sock, ('127.0.0.1', 1))
        ch.push(b'a')
        self.assertEqual(ch.push(b'b'), 1)

    def test_on_recv_acks_a_push(self):
        sock = self.FakeSock()
        ch = self.kcp.KcpChannel(sock, ('127.0.0.1', 1))
        packet = (self.kcp.kcp_prefix(1)
                  + struct.pack('<BBHIIII', 0x51, 0, 0x0200, 1234, 7, 0, 3) + b'abc')
        kind, sn, _una, payload = ch.on_recv(packet)
        self.assertEqual((kind, sn, payload), ('push', 7, b'abc'))
        self.assertEqual(sock.sent[0][0][32], 0x52)
        self.assertEqual(ch.una, 8)

    def test_notify_frame_shape(self):
        frame = self.kcp.notify(b'data', 42, 3)
        self.assertEqual(struct.unpack_from('<H', frame, 0)[0], 9)
        self.assertEqual(struct.unpack_from('<H', frame, 4)[0], 4)
        self.assertEqual(struct.unpack_from('<I', frame, 20)[0], 3)


class ReportTests(unittest.TestCase):
    """CS2 受信通知（DRWAck）の組立（RE の仕様で検証）。"""

    def setUp(self):
        load_package()
        from leo_rtc import report

        self.report = report

    def test_drw_ack_layout_matches_reverse_engineered_spec(self):
        frame = self.report.drw_ack([0x0102, 0x0304], flag=0)
        self.assertEqual(frame[0:2], b'\xf1\xd1')
        self.assertEqual(frame[2:4], (8).to_bytes(2, 'big'))
        self.assertEqual(frame[4:8], b'\xd1\x00\x00\x02')
        self.assertEqual(frame[8:], b'\x01\x02\x03\x04')

    def test_encrypted_drw_ack_round_trips_through_cs2(self):
        from leo_rtc import cs2

        seqs = [10, 11, 12, 65535]
        wire = self.report.enc_drw_ack(seqs, b'gfxEiUp1d43vwJQm')
        flag, parsed = self.report.parse_drw_ack(cs2.decrypt(wire, b'gfxEiUp1d43vwJQm'))
        self.assertEqual(flag, 0)
        self.assertEqual(parsed, seqs)

    def test_drw_ack_caps_the_sequence_list(self):
        frame = self.report.drw_ack(list(range(500)))
        flag, seqs = self.report.parse_drw_ack(frame)
        self.assertEqual(len(seqs), self.report.MAX_SEQS)
        self.assertEqual(seqs[-1], 499)


def load_bridge():
    path = STACK / 'tools' / 'mjpeg_bridge.py'
    spec = importlib.util.spec_from_file_location('mjpeg_bridge_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules['mjpeg_bridge_test'] = module
    spec.loader.exec_module(module)
    return module


class KeyRingTests(unittest.TestCase):
    """session_keys.json の読み込み。

    これが壊れると、セッション再接続のたびに鍵が食い違い、IDR が復号できず
    ブリッジが無映像になる。
    """

    def setUp(self):
        self.bridge = load_bridge()
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'session_keys.json'

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, key, iv):
        self.path.write_text('{"key": "%s", "iv": "%s"}' % (key, iv))

    def test_file_keys_are_loaded_and_mtime_change_reloads(self):
        self._write('0123456789abcdef', 'ABCDEFGHIJKL')
        ring = self.bridge.KeyRing(path=str(self.path))
        self.assertTrue(ring.ok)
        self.assertEqual(ring.key, b'0123456789abcdef')
        self.assertEqual(ring.iv, b'ABCDEFGHIJKL')
        # mtime が同じ間は再読込しない
        self.assertFalse(ring.reload())
        self._write('fedcba9876543210', 'MLKJIHGFEDCB')
        self.assertTrue(ring.reload(force=True))
        self.assertEqual(ring.key, b'fedcba9876543210')

    def test_missing_file_keeps_explicit_keys(self):
        ring = self.bridge.KeyRing(b'k' * 16, b'i' * 12, str(self.path))
        self.assertTrue(ring.ok)
        self.assertFalse(ring.reload())

    def test_broken_json_keeps_previous_keys(self):
        self._write('goodkeygoodkey1', 'goodivgoodiv')
        ring = self.bridge.KeyRing(path=str(self.path))
        self.assertTrue(ring.ok)
        self.path.write_text('not json')
        self.assertFalse(ring.reload(force=True))
        self.assertEqual(ring.key, b'goodkeygoodkey1')
