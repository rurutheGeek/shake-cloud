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
        aes_len = (len(token_plain) + 15) // 16 * 16
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
