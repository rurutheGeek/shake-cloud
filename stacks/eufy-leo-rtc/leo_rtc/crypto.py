"""leo_rtc crypto primitives.

Reverse-engineered from libmega_media_sdk.so (`RTC/src/webrtc/rtc_crypto.c`)
and the login handshake in `rtc_signal_client.c`.

The login handshake:
  1. client sends a body-less login; the server answers 401 with a body_type=3
     body: AES-ECB(challenge, key=derive("&#%@!_eufy_anker", packet_id)) where
     the challenge is the hex RSA modulus of a 1024-bit key, e=65537.
  2. the client answers body_type=4: [RSA-PKCS1v15(new_aes_key, n, e)]
     [u16 len][AES-ECB("did:license", key=derive(new_aes_key, packet_id))].
  3. the session then uses new_aes_key (packet_id = message timestamp) for the
     encrypted attach payloads.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import hashes  # noqa: F401  (kept for parity)
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_KEY = b'&#%@!_eufy_anker'


def derive_aes_key(key: bytes | str, packet_id: int) -> bytes:
    """Reproduce NewRTCCryptoByString's key derivation."""
    if isinstance(key, str):
        key = key.encode()
    material = bytearray(16)
    material[:min(len(key), 16)] = key[:16]
    digits = str(packet_id).encode()
    if len(digits) < 16:
        material[16 - len(digits):16] = digits
    return bytes(material)


def aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    if len(key) != 16:
        raise ValueError('AES-128 key must be 16 bytes')
    padded = data + b'\0' * ((-len(data)) % 16)
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    if len(key) != 16:
        raise ValueError('AES-128 key must be 16 bytes')
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return decryptor.update(data) + decryptor.finalize()


def decrypt_challenge(body: bytes, packet_id: int) -> int:
    """Decrypt the 401 body and return the server RSA modulus."""
    challenge = aes_ecb_decrypt(body, derive_aes_key(DEFAULT_KEY, packet_id))
    modulus = int(challenge.rstrip(b'\0'), 16)
    if modulus.bit_length() < 512:
        raise ValueError('challenge does not look like an RSA modulus')
    return modulus


def login_reply(session_key: bytes, packet_id: int, did: str, license: str, modulus: int) -> bytes:
    """Build the body_type=4 login reply."""
    public = rsa.RSAPublicNumbers(65537, modulus).public_key()
    rsa_ct = public.encrypt(session_key, padding.PKCS1v15())
    token = f'{did}:{license}'.encode()
    aes_ct = aes_ecb_encrypt(token, derive_aes_key(session_key, packet_id))
    return rsa_ct + len(aes_ct).to_bytes(2, 'little') + aes_ct
