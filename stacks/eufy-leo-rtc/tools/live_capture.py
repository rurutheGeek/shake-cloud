"""ライブ映像キャプチャ（開発用ツール・実機で動作確認済み）。

eufyCam S4 を wake からライブ開始まで通し、カメラから届く映像 RTP を保存する。
- 動作実績フロー: 48B ログイン応答・boot_action=1・priv1 先行・1103・メディア 1003。
- 受信は SO_RCVBUF 8MB＋ドレインループで取りこぼしを抑える（1 ループで sock2 を 10 回処理）。
  ただし `net.core.rmem_max` が小さいとカーネルが 416KB 等へ切り詰めるため、実サイズを表示し
  4MB 未満なら警告する（IDR 欠落＝復号不能の主因。2026-09-29 実測）。
- 保存形式は [4 バイト長][RTP パケット]（packets_to_annexb.py / mjpeg_bridge.py で変換）。

使い方:
  cd stacks/eufy-leo-rtc
  LEO_OUT=/tmp EUFY_ENV=.env python3 tools/live_capture.py

DID・LICENSE・ACCOUNT は .env（0600）または環境変数だけに置く。カメラのバッテリーを
消費するため、必要な時間だけ動かし、終了時に hangup を送る。
"""
import binascii, hashlib, hmac, json, os, socket, struct, subprocess, sys, time, base64
sys.path.insert(0, '/home/ruru/project/shake-cloud/stacks/eufy-leo-rtc')
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from leo_rtc.client import LeoRtcClient
from leo_rtc.protocol import CALL_PRIV1, CALL_PRIV_P2P
from leo_rtc.sdpinfo import build_sdp_info
from leo_rtc import protocol

_env_path = os.environ.get('EUFY_ENV', os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
for line in (open(_env_path) if os.path.exists(_env_path) else []):
    line = line.strip()
    if line and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)


# --- app-style login reply: AES part padded to 48 bytes ---
import leo_rtc.crypto as _c
_orig_login_reply = _c.login_reply
def _login_reply48(session_key, packet_id, did, license, modulus):
    from cryptography.hazmat.primitives.asymmetric import padding as _pad
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
    public = _rsa.RSAPublicNumbers(65537, modulus).public_key()
    rsa_ct = public.encrypt(session_key, _pad.PKCS1v15())
    token = (f'{did}:{license}'.encode()).ljust(48, b'\0')
    aes_ct = _c.aes_ecb_encrypt(token, _c.derive_aes_key(session_key, packet_id))
    return rsa_ct + len(aes_ct).to_bytes(2, 'little') + aes_ct
_c.login_reply = _login_reply48

MAGIC = 0x2112A442
FP_XOR = 0x5354554E
APP_ID = 'a9d1ec8e0d2d4e46'
PERSIST_CONTACT = os.environ.get('EUFY_CONTACT', '')
OUT = os.environ.get('LEO_OUT', '/tmp')
_vf_handles = {}

UFRAG1 = b'probe'
PWD1 = b'probe-password-23-bytes'


def _rand_key():
    alphabet = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(alphabet[b % len(alphabet)] for b in os.urandom(16)).encode()


K1 = _rand_key()
IV1 = os.urandom(12)

UFRAG2 = b'pMUM2'
PWD2 = b'p2p-password-23-byte!!!'
K2 = _rand_key()
IV2 = os.urandom(12)


def ms():
    return int(time.time() * 1000) & 0xffffffff


def attr(k, v):
    return struct.pack('>HH', k, len(v)) + v + b'\0' * ((-len(v)) % 4)


def add_mi(m, p):
    struct.pack_into('>H', m, 2, len(m) - 20 + 24)
    m += attr(0x0008, hmac.new(p, bytes(m), hashlib.sha1).digest())


def add_fp(m):
    struct.pack_into('>H', m, 2, len(m) - 20 + 8)
    m += attr(0x8028, struct.pack('>I', (binascii.crc32(bytes(m)) & 0xFFFFFFFF) ^ FP_XOR))


def sreq(tid, ufrag, pwd):
    m = bytearray(struct.pack('>HHI', 1, 0, MAGIC) + tid)
    m += attr(0x0006, f'{ufrag}:{ufrag}'.encode())
    m += attr(0xc057, b'\x00\x01\x00\x00')
    m += attr(0x802a, os.urandom(8))
    m += attr(0x0024, struct.pack('>I', 0x6e7f1eff))
    m += attr(0x0025, b'')
    add_mi(m, pwd)
    add_fp(m)
    return bytes(m)


def sresp(tid, peer, pwd):
    m = bytearray(struct.pack('>HHI', 0x0101, 0, MAGIC) + tid)
    a, p = peer
    xp = p ^ (MAGIC >> 16)
    xa = struct.unpack('>I', socket.inet_aton(a))[0] ^ MAGIC
    m += attr(0x0020, b'\0\1' + struct.pack('>H', xp) + struct.pack('>I', xa))
    add_mi(m, pwd)
    add_fp(m)
    return bytes(m)


class KCP:
    def __init__(self, sock, peer):
        self.s = sock
        self.peer = peer
        self.sn = 0
        self.una = 0

    def push(self, payload, sn=None):
        use = self.sn if sn is None else sn
        prefix = struct.pack('<II', 1, 1) + b'\0' * 24
        hdr = struct.pack('<IBBHIIII', 1, 0x51, 0, 0x0200, ms(), use, self.una, len(payload))
        self.s.sendto(prefix + hdr + payload, self.peer)
        if sn is None:
            self.sn += 1
        return use

    def on_recv(self, data):
        cmd = data[36]
        ts2, sn, una, ln = struct.unpack_from('<IIII', data, 40)
        if cmd == 0x51:
            self.una = sn + 1
            self.s.sendto(
                struct.pack('<II', 3, 1) + b'\0' * 24
                + struct.pack('<IBBHIIII', 3, 0x52, 0, 0x0800, ts2, 0, self.una, 0),
                self.peer)
            return ('push', sn, ln, data[56:56 + ln])
        return ('ack', sn, una, ln)


def notify(p, ts, sn=0):
    return struct.pack('<HHIIII', 9, 24, len(p), 1, ts, 1) + struct.pack('<I', sn) + p


def enc_frame(cmd, plain, key, counter):
    # KCP variant: [XZYH][tag][iv][counter][ct]
    iv = os.urandom(12)
    tc = AESGCM(key).encrypt(iv, plain, b'eufy security')
    tag, ct = tc[-16:], tc[:-16]
    return (b'XZYH' + struct.pack('<H', cmd) + struct.pack('<I', len(tc) + 0x10)
            + bytes([0x0a, 0, 0, 1, 0, 0]) + tag + iv + struct.pack('<I', counter) + ct)


def enc_frame_media(cmd, plain, key):
    # media (ANKExV4) variant: [XZYH][tag][iv][ct]  (no counter)
    iv = os.urandom(12)
    tc = AESGCM(key).encrypt(iv, plain, b'eufy security')
    tag, ct = tc[-16:], tc[:-16]
    return (b'XZYH' + struct.pack('<H', cmd) + struct.pack('<I', len(tc) + 0x10)
            + bytes([0x0a, 0, 0, 1, 0, 0]) + tag + iv + ct)


def ank_frame(frame, ssrc, counter, mask=b'\x01\xaa\xaa\xaa'):
    pad = (-(32 + len(frame))) % 4
    pkt = (b'\x9e\xcc' + struct.pack('>H', (32 + len(frame) + pad) // 4 - 1) + struct.pack('>I', ssrc)
           + b'ANKExV4\x12' + struct.pack('<I', counter) + mask + struct.pack('<I', len(frame)) + b'\0\0\0\0'
           + frame + b'\0' * pad)
    return pkt[:28] + struct.pack('<I', sum(pkt[12:]) & 0xffffffff) + pkt[32:]


ORDER = os.environ.get('ORDER', 'p2p_first')
ORACLE_WAIT = float(os.environ.get('ORACLE_WAIT', '0'))

lip = subprocess.check_output(['hostname', '-I'], text=True).split()[0]
sock1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock1.bind((lip, 0))
sock1.settimeout(0.05)
port1 = sock1.getsockname()[1]
sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 受信バッファは大きいほど取りこぼしに強い。SO_RCVBUFFORCE（root のみ）→ SO_RCVBUF の順で試し、
# 実際に確保できたサイズを表示する（net.core.rmem_max が小さいと 8MB 要求でも 416KB 等に
# 切り詰められ、IDR バーストで溢れて IDR が復号不能になる。実測 2026-09-29）。
for opt in (getattr(socket, 'SO_RCVBUFFORCE', None), socket.SO_RCVBUF):
    if opt is None:
        continue
    try:
        sock2.setsockopt(socket.SOL_SOCKET, opt, 8 * 1024 * 1024)
    except OSError:
        continue
try:
    actual = sock2.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    print('media SO_RCVBUF = %d bytes' % actual)
    if actual < 4 * 1024 * 1024:
        print('  WARNING: 受信バッファが小さい（net.core.rmem_max を 32MB 等へ上げるか root で '
              'SO_RCVBUFFORCE を使う。小さいと IDR が欠落して復号できません）')
except OSError:
    pass
sock2.bind((lip, 0))
sock2.settimeout(0.05)
port2 = sock2.getsockname()[1]
print('sock1(KCP)', port1, 'sock2(media)', port2)

c = None
for attempt in range(4):
    c = LeoRtcClient(sn=os.environ['EUFY_SN'], did=os.environ['EUFY_DID'],
                     license=os.environ['EUFY_LICENSE'],
                     account=os.environ.get('EUFY_ACCOUNT', ''), timeout=8)
    c.__enter__()
    try:
        c.login()
        break
    except Exception as e:
        print('login retry', attempt, e)
        c.close()
        time.sleep(5)

# app-style: random hex contact at login (not the SN)
import hashlib as _h2
_CONTACT = _h2.md5(os.urandom(16)).hexdigest()
_orig_bh = protocol.build_header
def _bh(msg_type, timestamp, seq, route, **kw):
    if msg_type == protocol.TYPE_LOGIN and kw.get('contact') == c.sn:
        kw['contact'] = _CONTACT
    return _orig_bh(msg_type, timestamp, seq, route, **kw)
protocol.build_header = _bh
print('login contact ->', _CONTACT)

si1 = build_sdp_info(ufrag=UFRAG1, pwd=PWD1, crypto_key=K1, crypto_iv=IV1, kcp=6)
si2 = build_sdp_info(ufrag=UFRAG2, pwd=PWD2, crypto_key=K2, crypto_iv=IV2, kcp=6)

# app-style: both calls at the same instant (6ms apart), same account, retries with same uuid
CALL_TS = int(time.time())
CALL_ACCT = hashlib.md5(('0' + os.environ.get('EUFY_ACCOUNT', '') + str(CALL_TS)).encode()).hexdigest()
tok_plain = (os.environ['EUFY_DID'] + ':' + os.environ['EUFY_LICENSE']).encode().ljust(48, b'\0')
CALL_TOKEN = base64.b64encode(c.encrypt_attach(tok_plain, CALL_TS)).decode()
call_msgs = {}
_callseq = ((CALL_PRIV_P2P, si2, 'priv_p2p'), (CALL_PRIV1, si1, 'priv1')) if ORDER == 'p2p_first' else ((CALL_PRIV1, si1, 'priv1'), (CALL_PRIV_P2P, si2, 'priv_p2p'))
for ct, si, p2p in _callseq:
    payload = {
        'account': CALL_ACCT, 'ftv': 20, 'call_type': 'scall', 'eufy_p2p_type': p2p,
        'sdp_info': base64.b64encode(si).decode(), 'to': 'device',
        'eufy_from_contact': c.session.contact, 'eufy_video_format': 0, 'boot_action': 1,
        'eufy_network_type': 1, 'eufy_app_id': APP_ID, 'token': CALL_TOKEN,
    }
    attach = c.encrypt_attach(json.dumps(payload, separators=(',', ':')).encode(), CALL_TS)
    uuid = protocol.call_uuid(ct, c.sn, c.did, c.license, CALL_TS * 1000000 + ct)
    body = protocol.CallBody(uuid=uuid, contact=c.session.contact, attach=attach, reserved=0).build()
    msg = protocol.build_header(protocol.TYPE_CALL, CALL_TS, c._next_seq(), c.route,
                                contact=c.sn, body=body, body_type=protocol.BODY_CALL, net_type=2, encrypted=1,
                                reserved=2)
    call_msgs[p2p] = (uuid, msg)
print('SESSION CONTACT =', repr(c.session.contact))
u2, msg2 = call_msgs['priv_p2p']
u1, msg1 = call_msgs['priv1']
print('calls: p2p', u2[:20], 'priv1', u1[:20])
# app-like retry batches: (p2p,priv1) at t0; priv1 at +0.7; (p2p,priv1) at +4.0; (p2p,priv1) at +6.0
batch = [(0.0, (msg2, msg1)), (0.7, (msg1,)), (4.0, (msg2, msg1)), (6.0, (msg2, msg1))]
start = time.time()
import threading
host = (c.session.candidates or [c.host])[0]


def send_batches():
    for wait, msgs in batch:
        dt = start + wait - time.time()
        if dt > 0:
            time.sleep(dt)
        for m in msgs:
            c.send(m, host)


th = threading.Thread(target=send_batches, daemon=True)
th.start()

# collect replies for the first 8s
end = time.time() + 8
while time.time() < end:
    m = c.recv(timeout=max(0.1, end - time.time()))
    if m is None:
        continue
    if m.type == 2:
        ap = (m.attach_plain or b'').decode(errors='ignore')
        s2 = ap.find('{')
        j = None
        if s2 >= 0:
            try:
                j, _ = json.JSONDecoder().raw_decode(ap[s2:])
            except Exception:
                pass
        info = ''
        if j and j.get('sdp_info'):
            raw = base64.b64decode(j['sdp_info'])
            info = 'ufrag=%r key=%r pwd=%r iv=%r' % (raw[0x06:0x1e].split(b'\0')[0], raw[0x26:0x36],
                                                     raw[0x0e:0x25].split(b'\0')[0], raw[0x3a:0x46])
        if m.code in (100, 200):
            print('reply code=%d %s' % (m.code, info))


def send_report(uuid_hex, js):
    ts = int(time.time())
    att = c.encrypt_attach(json.dumps(js, separators=(',', ':')).encode(), ts)
    rb = struct.pack('<IH', 0, len(att)) + uuid_hex.encode() + b'\0' * 6 + att
    msg = protocol.build_header(protocol.TYPE_REPORT, ts, c._next_seq(), c.route,
                                contact=c.sn, body=rb, body_type=7, net_type=1, encrypted=1)
    c.send(msg)


# app's exact report JSONs (order: priv_media x2 -> priv1 x2)
_now = '2026-09-27 19:05:00'
rm = {"c_s":2,"f_cs":1,"channel_type":"priv_media","ice":2,"app_ice":2,
      "channel_status":"0x80e","msg_status":"0x27e","call_duration":7,"h0":8,"s0":8,"r0":7,
      "ice_pt":71597,"cur":71597,"VER":"2","last_ping_time":_now,"info_count":0,
      "app_update_time_utc":_now}
r1 = {"c_s":2,"m_cs":2,"channel_type":"priv1","channel_status":"0x80e","msg_status":"0x85c",
      "call_duration":7,"ice_pt":0,"cur":71597,"VER":"2","last_ping_time":_now,
      "info_count":0,"app_update_time_utc":_now}
rm2 = dict(rm); rm2["repeat"] = 1
r12 = dict(r1); r12["repeat"] = 1


def send_app_reports():
    time.sleep(7.0)
    send_report(u2, rm)
    time.sleep(0.2)
    send_report(u2, rm2)
    time.sleep(0.2)
    send_report(u1, r1)
    time.sleep(0.2)
    send_report(u1, r12)
    print('app-style reports sent (priv_media x2 -> priv1 x2)')


th_r = threading.Thread(target=send_app_reports, daemon=True)
th_r.start()

c.info(u1, {"file_candidate": f"a=candidate:1 1 UDP 2122317823 {lip} {port1} typ host", "file_candidate_num": 0})
c.info(u2, {"candidate": f"candidate:2849834890 1 udp 2122260223 {lip} {port2} typ host generation 0 ufrag {UFRAG2.decode()} network-id 1"})

hosts1 = []
hosts2 = []
media_peer = None
ok1 = None
kcp = None
acct = os.environ.get('EUFY_ACCOUNT', '')
SSRC_MEDIA = struct.unpack('>I', os.urandom(4))[0]


def tx():
    return str(int(time.time() * 1000))


env1306 = json.dumps({"account_id": acct, "cmd": 1306, "mChannel": 0, "mValue3": 0,
                      "payload": {"cmd": 10013, "table": "history_record_info", "transaction": tx()}},
                     separators=(',', ':')).encode()
env1003 = json.dumps({"cmd": 1003, "mChannel": 0, "account_id": acct, "mValue3": 1003, "mValue5": 0,
                      "payload": {"accountId": acct, "streamtype": 2, "camera_type": 0, "entrytype": 0,
                                  "stitch_mode": 7,
                                  "chn_list": [{"cameraType": 0, "chn": 0, "index": 0, "sensor": 0},
                                               {"cameraType": 0, "chn": 0, "index": 1, "sensor": 1}],
                                  "ClientOS": "ANDROID", "audio_chn": 0,
                                  "pip_cord": {"x1": 690, "y1": 690, "x2": 940, "y2": 940},
                                  "msg_id": 1, "extValue": 1000, "cameraType": 0, "station_video_type": 9},
                      "transaction": tx(), "msg_id": 1}, separators=(',', ':')).encode()

RTCP76 = bytes.fromhex('81c90007000000010dc1a8150000000000027cb40000087f140ff38b00001c1b8fce0005000000010000000052454d420117b9d90dc1a81580cf00040000000104000002ee631410ef9f7729')
RTP152 = bytes.fromhex('b0ce000a3390000f1105ea5000200f5e340101010101010101010101010101060dc1a8157c84020100000003b0ce0006339f00011105ea51192001a001060dc1a8157c8402010001b0ce000a33a000111105eb52082011350201010101010201010101010101010201060dc1a8157c8402010001b0ce000833b100081105ec530020082c0101010101010101060dc1a8157c930201000002')
# matrix schedule: [(label, kind, key)]  kind: kcp1306 / media1003
app1103 = bytes.fromhex('ff00000087030000')
matrix = [
    ('kcp1103-K1-first', 'kcp1103', K1, 0x01020302),
    ('kcp44c-K1', 'kcp44c', K1, 0x01020303),
    ('kcp1003-K2#1', 'kcp1003', K2, 0x01020310),
    ('kcp1003-K2#2', 'kcp1003', K2, 0x01020311),
    ('media1003-K2#1', 'media1003', K2, 0x01020312),
    ('media1003-K2#2', 'media1003', K2, 0x01020313),
    ('probe1306-K1', 'kcp1306', K1, 0x01020304),
    ('media1003-K2#3', 'media1003', K2, 0x01020314),
    ('kcp1003-K2#3', 'kcp1003', K2, 0x01020315),
    ('media1003-K2#4', 'media1003', K2, 0x01020316),
    ('kcp44c-K1-retry', 'kcp44c', K1, 0x01020317),
    ('kcp44c-K2', 'kcp44c', K2, 0x01020318),
]
stream = b''
media_pkts = 0
media_kinds = {}
hello = False
report_ok = 0
ack_sent = 0
t_end = time.time() + 480
nxt_hello = 0
nxt_ice1 = 0
nxt_ice2 = 0
nxt_info = 0
nxt_report = 0
nxt_mkeep = 0
nxt_rtp = 0
nxt_cmd = 0
stage = 0
ank_counter = 0
start_loop = time.time()
while time.time() < t_end:
    now = time.time()
    if kcp is not None and now >= nxt_hello:
        kcp.push(notify(b'XZYH' + struct.pack('<HH', 0x0473, 0) + b'\0' * 8, ms(), kcp.sn))
        nxt_hello = now + 0.6
    if hosts1 and now >= nxt_ice1:
        sock1.sendto(sreq(os.urandom(12), UFRAG1.decode(), PWD1), hosts1[-1])
        nxt_ice1 = now + 1.5
    if kcp is not None and (media_peer or hosts2) and now >= nxt_rtp:
        tgt = media_peer or (hosts2[0] if hosts2 else None)
        if tgt:
            sock2.sendto(RTCP76, tgt)
            sock2.sendto(RTP152, tgt)
        nxt_rtp = now + 1.0
    if (media_peer or hosts2) and now >= nxt_mkeep:
        tgt = media_peer or (hosts2[0] if hosts2 else None)
        if tgt:
            ka = ank_frame(b'', SSRC_MEDIA, ank_counter, mask=b'\x04\xaa\xaa\xaa')
            sock2.sendto(ka, tgt)
            ank_counter += 1
        nxt_mkeep = now + 0.6
    if (media_peer or hosts2) and now >= nxt_ice2:
        for h in ([media_peer] if media_peer else hosts2[-2:]):
            sock2.sendto(sreq(os.urandom(12), UFRAG2.decode(), PWD2), h)
        nxt_ice2 = now + 1.5
    if now >= nxt_info:
        c.info(u1, {"file_candidate": f"a=candidate:1 1 UDP 2122317823 {lip} {port1} typ host", "file_candidate_num": 0})
        c.info(u2, {"candidate": f"candidate:2849834890 1 udp 2122260223 {lip} {port2} typ host generation 0 ufrag {UFRAG2.decode()} network-id 1"})
        nxt_info = now + 5.0
    if kcp is not None and stage < len(matrix) and now >= nxt_cmd and now - start_loop > (13 + ORACLE_WAIT):
        label, kind, key, ctr = matrix[stage]
        if kind == 'kcp1306':
            kcp.push(notify(enc_frame(0x546, env1306, key, ctr), ms(), kcp.sn))
            print('>> %s (KCP 1306, key=%r)' % (label, key))
        elif kind == 'kcp1103':
            kcp.push(notify(enc_frame(0x44f, app1103, key, ctr), ms(), kcp.sn))
            print('>> %s (KCP 1103, key=%r)' % (label, key))
        elif kind == 'kcp44c':
            kcp.push(notify(enc_frame(0x44c, b'', key, ctr), ms(), kcp.sn))
            print('>> %s (KCP 44c, key=%r)' % (label, key))
        elif kind == 'kcp1003':
            kcp.push(notify(enc_frame(0x546, env1003, key, ctr), ms(), kcp.sn))
            print('>> %s (KCP 1003, key=%r)' % (label, key))
        else:
            tgt = media_peer or (hosts2[0] if hosts2 else None)
            if tgt:
                fr = ank_frame(enc_frame(0x546, env1003, key, ctr), SSRC_MEDIA, ank_counter)
                sock2.sendto(fr, tgt)
                ank_counter += 1
                print('>> %s (MEDIA 1003, key=%r) to %s' % (label, key, tgt))
            else:
                print('>> %s skipped (no media peer)' % label)
        stage += 1
        nxt_cmd = now + 3.0

    m = c.recv(timeout=0.002)
    if m is not None and m.type == 4:
        txt = (m.attach_plain or b'').decode(errors='replace')
        try:
            j = json.loads(txt[:txt.rfind('}') + 1])
            fc = j.get('file_candidate', '')
            cd = j.get('candidate', '')
            if fc:
                p = fc.split()
                if len(p) >= 8 and p[6] == 'typ' and p[7] == 'host' and p[4] != lip:
                    h = (p[4], int(p[5]))
                    if h not in hosts1:
                        hosts1.append(h)
                        print('cam host1', h)
            if cd:
                p = cd.replace('\r\n', '').split()
                if len(p) >= 8 and p[6] == 'typ' and p[4] != lip:
                    h = (p[4], int(p[5]))
                    if h not in hosts2:
                        hosts2.append(h)
                        print('cam cand2', h)
        except Exception:
            pass
        if m.response == 0:
            c.ack_info(m)

    for sk in (sock1,) + (sock2,) * 10:
        try:
            data, peer = sk.recvfrom(65535)
        except socket.timeout:
            continue
        if peer[0] == lip:
            continue
        if len(data) >= 20 and data[4:8] == b'\x21\x12\xa4\x42':
            kind = struct.unpack_from('>H', data, 0)[0]
            if kind == 0x0001:
                pwd = PWD1 if sk is sock1 else PWD2
                sk.sendto(sresp(data[8:20], peer, pwd), peer)
            elif kind == 0x0101 and sk is sock1 and ok1 is None:
                ok1 = peer
                kcp = KCP(sock1, ok1)
                print('ICE1', ok1)
            continue
        if sk is sock1 and kcp is not None and len(data) >= 56 and data[:4] in (b'\x01\x00\x00\x00', b'\x03\x00\x00\x00'):
            r = kcp.on_recv(data)
            if r[0] == 'push':
                stream += r[3]
                while len(stream) >= 16:
                    j2 = stream.find(b'XZYH')
                    if j2 < 0:
                        stream = stream[-8:]
                        break
                    if j2 > 0:
                        stream = stream[j2:]
                    if len(stream) < 16:
                        break
                    ln3 = struct.unpack_from('<I', stream, 6)[0]
                    if len(stream) < 16 + ln3:
                        break
                    frame = stream[:16 + ln3]
                    stream = stream[16 + ln3:]
                    cid = struct.unpack_from('<H', frame, 4)[0]
                    body = frame[16:]
                    code = struct.unpack('<i', body[:4])[0] if len(body) >= 4 else None
                    print('  CAM KCP cmd=%#x len=%d code=%s' % (cid, ln3, code))
                    try:
                        with open(OUT + '/rawkcp.bin', 'ab') as rf:
                            rf.write(struct.pack('<I', len(frame)) + frame)
                    except Exception:
                        pass
                    if cid in (0x44c, 0x44d, 0x401, 0x400) or ln3 > 1000:
                        try:
                            with open(OUT + '/keyresp_%x.bin' % cid, 'ab') as kf:
                                kf.write(struct.pack('<I', len(body)) + body)
                        except Exception:
                            pass
                        print('    DUMP cmd=%#x bodylen=%d body[:64]=%r' % (cid, len(body), body[:64]))
            continue
        if sk is sock2:
            media_pkts += 1
            if data[:1] == b'\x90' or data[:1] == b'\x80':
                pfx = data[:2].hex()
                media_kinds[pfx] = media_kinds.get(pfx, 0) + 1
                try:
                    fh2 = _vf_handles.get(pfx)
                    if fh2 is None:
                        fh2 = open(OUT + '/vf_%s.bin' % pfx, 'ab')
                        _vf_handles[pfx] = fh2
                    fh2.write(data)
                except Exception:
                    pass
            if len(data) == 20 and data[:2] == b'\x80\xac' and media_peer != peer:
                media_peer = peer
                print('media peer set', peer)
            if b'Hello,Axera' in data:
                hello = True
                print('  *** Hello,Axera! len=%d' % len(data))
            elif len(data) > 100:
                print('  MEDIA[%d] len=%d head=%s' % (media_pkts, len(data), data[:48].hex()))
            if media_pkts % 1000 == 0:
                print('  media pkts', media_pkts)

c.hangup(u1)
c.close()
import json
try:
    json.dump(media_kinds, open(OUT + '/vf_kinds.json','w'), indent=1)
except Exception:
    pass
print('DONE media packets', media_pkts, 'hello', hello)
print('KINDS', sorted(media_kinds.items(), key=lambda kv:-kv[1]))
