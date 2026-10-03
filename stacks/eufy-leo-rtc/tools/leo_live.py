import hashlib, ipaddress, json, os, socket, struct, subprocess, sys, time, base64
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from leo_rtc.client import LeoRtcClient
from leo_rtc.protocol import CALL_PRIV1, CALL_PRIV_P2P
from leo_rtc.sdpinfo import build_sdp_info
from leo_rtc import protocol

# 0x401 用の ECC 公開鍵（E2E 鍵配送。復号には未使用だがカメラが期待する）
from cryptography.hazmat.primitives.asymmetric import ec as _ec
from cryptography.hazmat.primitives import serialization as _ser
_ECC_PRIV = _ec.generate_private_key(_ec.SECP256R1())
ECC_PUB_HEX = _ECC_PRIV.public_key().public_bytes(
    _ser.Encoding.X962, _ser.PublicFormat.UncompressedPoint)[1:].hex().upper().encode()


MAGIC = 0x2112A442
FP_XOR = 0x5354554E
APP_ID = 'a9d1ec8e0d2d4e46'
PERSIST_CONTACT = os.environ.get('EUFY_CONTACT', '')
OUT = os.environ.get('LEO_OUT', '/tmp')
_vf_handles = {}

UFRAG1 = b'probe'
PWD1 = b'probe-password-23-bytes'
K1 = b'QOXBQDG7UShCGUaS'
IV1 = b'J' * 12

UFRAG2 = b'pMUM2'
PWD2 = b'p2p-password-23-byte!!!'
K2 = b'Wtd312vgUx5AEEhE'
IV2 = b'K' * 12


ICE_CONTROLLED = os.environ.get('LEO_ICE_CONTROLLED') == '1'


def _sreq(tid, ufrag, pwd):
    from leo_rtc.ice import stun_request
    return stun_request(tid, ufrag, pwd, controlled=ICE_CONTROLLED)


def ms():
    return int(time.time() * 1000) & 0xffffffff



from leo_rtc.ice import stun_response as sresp
from leo_rtc.kcp import KcpChannel as KCP, notify
from leo_rtc.envelope import build_command_frame as enc_frame
from leo_rtc.media_channel import build_ank as ank_frame


ORDER = os.environ.get('ORDER', 'p2p_first')
ORACLE_WAIT = float(os.environ.get('ORACLE_WAIT', '0'))

lip = subprocess.check_output(['hostname', '-I'], text=True).split()[0]
sock1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock1.bind((lip, 0))
sock1.settimeout(0.05)
port1 = sock1.getsockname()[1]
sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    sock2.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
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
_callseq = ((CALL_PRIV_P2P, si2, 'priv_p2p'), (CALL_PRIV1, si1, 'priv1')) if ORDER == 'p2p_first' else ((CALL_PRIV1, si1, 'priv1'), (CALL_PRIV_P2P, si2, 'priv_p2p'))


def build_calls(ts):
    acct = hashlib.md5(('0' + os.environ.get('EUFY_ACCOUNT', '') + str(ts)).encode()).hexdigest()
    tok_plain = (os.environ['EUFY_DID'] + ':' + os.environ['EUFY_LICENSE']).encode().ljust(48, b'\0')
    token = base64.b64encode(c.encrypt_attach(tok_plain, ts)).decode()
    msgs = {}
    for ct, si, p2p in _callseq:
        payload = {
            'account': acct, 'ftv': 20, 'call_type': 'scall', 'eufy_p2p_type': p2p,
            'sdp_info': base64.b64encode(si).decode(), 'to': 'device',
            'eufy_from_contact': c.session.contact, 'eufy_video_format': int(os.environ.get('EUFY_VIDEO_FORMAT', '0')),
            'eufy_network_type': 1, 'eufy_app_id': APP_ID, 'token': token,
            'boot_action': int(os.environ.get('EUFY_BOOT_ACTION', '1')),
        }
        attach = c.encrypt_attach(json.dumps(payload, separators=(',', ':')).encode(), ts)
        uuid = protocol.call_uuid(ct, c.sn, c.did, c.license, ts * 1000000 + ct)
        body = protocol.CallBody(uuid=uuid, contact=c.session.contact, attach=attach, reserved=0).build()
        msg = protocol.build_header(protocol.TYPE_CALL, ts, c._next_seq(), c.route,
                                    contact=c.sn, body=body, body_type=protocol.BODY_CALL, net_type=2, encrypted=1,
                                    reserved=2)
        msgs[p2p] = (uuid, msg)
    return msgs


CALL_TS = int(time.time())
call_msgs = build_calls(CALL_TS)
print('SESSION CONTACT =', repr(c.session.contact))
u2, msg2 = call_msgs['priv_p2p']
u1, msg1 = call_msgs['priv1']
print('calls: p2p', u2[:20], 'priv1', u1[:20])
# app-like retry batches: (p2p,priv1) at t0; priv1 at +0.7; (p2p,priv1) at +4.0; (p2p,priv1) at +6.0
batch = [(0.0, (msg2, msg1)), (0.7, (msg1,)), (4.0, (msg2, msg1)), (6.0, (msg2, msg1))]
start = time.time()
import threading
host = (c.session.candidates or [c.host])[0]
TURN_INFO = None


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
        if j and isinstance(j.get('turn'), dict):
            TURN_INFO = j['turn']
        if j and j.get('sdp_info'):
            raw = base64.b64decode(j['sdp_info'])
            key = raw[0x26:0x36].split(b'\0')[0]
            iv = raw[0x3a:0x46].split(b'\0')[0]
            ufrag = raw[0x06:0x1e].split(b'\0')[0]
            info = 'ufrag=%r key=%r pwd=%r iv=%r' % (ufrag, key,
                                                     raw[0x0e:0x25].split(b'\0')[0], iv)
            # 映像ストリーム（90 61）は priv_p2p チャネルの鍵で暗号化される。
            # priv1 の鍵で上書きしないよう、p2p の応答だけを書く。
            if ufrag == UFRAG2 and key and iv:
                try:
                    with open(OUT + '/session_keys.json.tmp', 'w') as kf:
                        json.dump({'key': key.decode(), 'iv': iv.decode(),
                                   'session_ts': int(time.time())}, kf)
                    os.replace(OUT + '/session_keys.json.tmp', OUT + '/session_keys.json')
                    print('session keys -> %s/session_keys.json' % OUT)
                except Exception as e:
                    print('session keys write err', e)
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

# 公式アプリはメディアを TURN 中継で受けている（直経路は約 11 秒で止まる）。
# LEO_TURN=1 なら映像ソケットを TURN 中継に差し替え、relay 候補だけを出す。
CAND2 = f"candidate:2849834890 1 udp 2122260223 {lip} {port2} typ host generation 0 ufrag {UFRAG2.decode()} network-id 1"
turn_sock = None
CAND2_RELAY = None
if os.environ.get('LEO_TURN', '0') == '1' and TURN_INFO:
    from leo_rtc.turn import TurnSocket
    try:
        turn_sock = TurnSocket((TURN_INFO['turn_addr'], int(TURN_INFO['turn_port'])),
                               TURN_INFO['turn_user'], TURN_INFO['turn_password'], lip)
        raddr, rport = turn_sock.allocate()
        print('TURN relayed', (raddr, rport), 'mapped', turn_sock.mapped)
        mip, mport = turn_sock.mapped or (lip, port2)
        CAND2_RELAY = (f"candidate:3226357370 1 udp 41885695 {raddr} {rport} typ relay raddr {mip} rport {mport}"
                       f" generation 0 ufrag {UFRAG2.decode()} network-id 1")
        # LEO_TURN=only なら中継だけ、1 なら直経路と中継の両方を出して両方で受ける。
        if os.environ.get('LEO_TURN_MODE', 'dual') == 'only':
            sock2 = turn_sock
            CAND2 = CAND2_RELAY
        else:
            from leo_rtc.turn import DualSocket
            sock2 = DualSocket(sock2, turn_sock)
    except Exception as error:
        print('TURN allocate failed, using host path:', error)
        turn_sock = None
c.info(u1, {"file_candidate": f"a=candidate:1 1 UDP 2122317823 {lip} {port1} typ host", "file_candidate_num": 0})
c.info(u2, {"candidate": CAND2})
if turn_sock is not None and CAND2 != CAND2_RELAY:
    c.info(u2, {"candidate": CAND2_RELAY})

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

env1004 = json.dumps({"cmd": 1004, "mChannel": 0, "account_id": acct, "mValue3": 1004, "mValue5": 0,
                      "transaction": tx(), "msg_id": 1}, separators=(',', ':')).encode()

RTCP76 = bytes.fromhex('81c90007000000010dc1a8150000000000027cb40000087f140ff38b00001c1b8fce0005000000010000000052454d420117b9d90dc1a81580cf00040000000104000002ee631410ef9f7729')
RTP152 = bytes.fromhex('b0ce000a3390000f1105ea5000200f5e340101010101010101010101010101060dc1a8157c84020100000003b0ce0006339f00011105ea51192001a001060dc1a8157c8402010001b0ce000a33a000111105eb52082011350201010101010201010101010101010201060dc1a8157c8402010001b0ce000833b100081105ec530020082c0101010101010101060dc1a8157c930201000002')
# matrix schedule: [(label, kind, key)]  kind: kcp1306 / media1003
app1103 = bytes.fromhex('ff00000087030000')
def build401(sn, account, pub_hex, sflag=1):
    f = bytearray(405)
    f[0:4] = b'XZYH'; f[4:6] = struct.pack('<H', 0x0401)
    f[6:10] = struct.pack('<I', 0x0185)
    f[0x0c] = 0xff; f[0x0e] = sflag
    f[0x15:0x15 + len(sn)] = sn.encode()
    f[0x95:0x95 + len(account)] = account.encode()
    f[0x115:0x115 + 128] = pub_hex[:128]
    return bytes(f)


frame401 = build401(os.environ.get('EUFY_SN', ''), acct, ECC_PUB_HEX)
matrix = [
    ('kcp1103-K1-first', 'kcp1103', K1, 0x01020302),
    ('kcp401-K1', 'kcp401', K1, 0x01020303),
    ('kcp44c-K1', 'kcp44c', K1, 0x01020304),
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
last_media_t = 0.0
# 映像（9061/90e1）が最後に届いた時刻。カメラは約 11 秒分の映像で止めるため、
# 映像が止まったら早めに切って張り直す（LEO_VIDEO_IDLE 秒）。
last_video_t = 0.0
VIDEO_IDLE = float(os.environ.get('LEO_VIDEO_IDLE', '20'))
ack_seqs = []
# アプリの平文レポート（90ce）を模して送る実験（LEO_APP_REPORT=1 のときだけ）。
# 仕様は docs/development/H05-ha-live-request.md §9.4 参照。
_rep_tpl = []
_rep_i = 0
_rep_counter = 0
last_video_seq = 0
last_audio_seq = 0
last_902f_seq = 0
nxt_report = 0.0
nxt_hb80 = 0.0
nxt_1003_retry = 0.0
nxt_1003_keep = 0.0
# 映像中に「開始時とバイト同一の calls」を定期再送（SDK の再送方式）。
nxt_call_replay = 0.0
# 映像が止まった後も同一プロセス（KCP/socket 温存）で新しい calls を送り直し、
# 同じセッションで映像が戻るか粘る。0 で従来どおり VIDEO_IDLE で切断。
REARM_LIMIT = float(os.environ.get('LEO_REARM_LIMIT', '0'))
REARM_WAIT = float(os.environ.get('LEO_REARM_WAIT', '15'))
rearm_until = 0.0
_enc_i = 0
_enc_counter = 0
nxt_enc = 0.0
if os.environ.get('LEO_APP_REPORT'):
    try:
        _rep_tpl = [bytes.fromhex(h) for h in json.load(open(os.environ.get('LEO_REPORT_FILE', '')))]
        if _rep_tpl:
            _rep_counter = int.from_bytes(_rep_tpl[0][8:12], 'big')
        print('app reports loaded:', len(_rep_tpl))
    except Exception as e:
        print('app reports err', e)


def build_app_report(tpl, ts, ack_seq):
    body = bytearray(tpl)
    if len(body) >= 12:
        body[8:12] = struct.pack('>I', ts & 0xFFFFFFFF)
    # 06 <SSRC 4b> <seq> のレコードを、そのストリームの自前最新 seq に揃える。
    if os.environ.get('LEO_REPORT_SEQ_902F') and last_902f_seq:
        ack_seq = last_902f_seq
    for ssrc, seq in ((b'\x0d\xc1\xa8\x15', ack_seq & 0xFFFF),
                      (b'\x22\x84\x48\xe9', last_audio_seq & 0xFFFF)):
        i = 0
        while True:
            j = body.find(b'\x06' + ssrc, i)
            if j < 0 or j + 7 > len(body):
                break
            body[j+5:j+7] = struct.pack('>H', seq)
            i = j + 5
    return bytes(body)


_ce_frames = []
_ce_i = 0
nxt_ce = 0.0
_ce_path = os.environ.get('LEO_CE_FILE', '')
if _ce_path:
    try:
        _d = open(_ce_path, 'rb').read()
        _o = 0
        while _o + 2 <= len(_d):
            _ln = int.from_bytes(_d[_o:_o+2], 'little')
            _o += 2
            if _ln <= 0 or _o + _ln > len(_d):
                break
            _ce_frames.append(_d[_o:_o+_ln])
            _o += _ln
        print('ce reports loaded:', len(_ce_frames))
    except Exception as _e:
        print('ce load err', _e)
nxt_ack = 0.0
nxt_1003 = 0.0
ctr_1003 = 0x01020400
nxt_wake = 0.0
_ce = []
try:
    _d = open('/tmp/disabled_ce.bin', 'rb').read()
    _o = 0
    while _o + 2 <= len(_d):
        _ln = int.from_bytes(_d[_o:_o+2], 'little'); _o += 2
        _ce.append(_d[_o:_o+_ln]); _o += _ln
except Exception as _e:
    print('ce load err', _e)
print('ce reports loaded:', len(_ce))
_ce_i = 0
nxt_ce = 0.0
media_kinds = {}
hello = False
report_ok = 0
ack_sent = 0
t_end = time.time() + 480
nxt_hello = 0
hb_seq = 1
nxt_ice1 = 0
nxt_ice2 = 0
nxt_info = 0
nxt_report = 0
nxt_mkeep = 0
nxt_rtp = 0
nxt_arr = 0.0
nxt_static_ce = 0.0
from leo_rtc.rtcp import ReceiverReports
rtcp_reports = ReceiverReports()
# 過去の捕捉の f1ce（b0ce）をそのまま送るか。中身が古いので既定は送らない。
STATIC_CE = os.environ.get('LEO_STATIC_CE', '0') == '1'
nxt_cmd = 0
stage = 0
ank_counter = 0
start_loop = time.time()
while time.time() < t_end:
    now = time.time()
    if turn_sock is not None:
        turn_sock.maintain()
    if kcp is not None and now >= nxt_hello:
        # 1139 心拍（裸フレーム）。プリュード付きの完全形は実測で逆に短くなった
        # （08:0x の A/B: 232〜491 パケット。裸は同日 3400〜5600）。
        kcp.push(notify(b'XZYH' + struct.pack('<HH', 0x0473, 0) + b'\0' * 8, ms(), kcp.sn))
        nxt_hello = now + 0.62
    if hosts1 and now >= nxt_ice1:
        sock1.sendto(_sreq(os.urandom(12), UFRAG1.decode(), PWD1), hosts1[-1])
        nxt_ice1 = now + 1.5
    if kcp is not None and (media_peer or hosts2) and now >= nxt_rtp:
        tgt = media_peer or (hosts2[0] if hosts2 else None)
        if tgt:
            # 受信状況から組み立てた RR＋REMB＋XR（アプリと同じ約 4 回/秒）。
            # 受信前は過去の捕捉の固定 RTCP で代用する。
            _rr = rtcp_reports.video_report()
            sock2.sendto(_rr or RTCP76, tgt)
            if now >= nxt_arr:
                _arr = rtcp_reports.audio_report()
                if _arr:
                    sock2.sendto(_arr, tgt)
                nxt_arr = now + 1.0
            if STATIC_CE and now >= nxt_static_ce:
                sock2.sendto(RTP152, tgt)
                nxt_static_ce = now + 1.0
        nxt_rtp = now + 0.25
    # 実験: アプリ捕獲の 0xce レポート（長さプレフィクス LE16）をメディア経路へ
    # アプリと同じ ~24/s で流す（LEO_CE_FILE 指定時のみ）。以前の実測でセッションが
    # 15→28 秒に延びたため、新環境で再検証する。
    if _ce_frames and media_peer and now >= nxt_ce:
        nxt_ce = now + 1.0 / 24.0
        try:
            fr = ank_frame(_ce_frames[_ce_i % len(_ce_frames)], SSRC_MEDIA, ank_counter)
            sock2.sendto(fr, media_peer)
            ank_counter += 1
            _ce_i += 1
        except Exception:
            pass
    # 暗号形（b0ce）レポート: アプリと同じ約 24/s
    if (_rep_tpl and os.environ.get('LEO_REPORT_ENCRYPT') and media_peer
            and now >= nxt_enc):
        nxt_enc = now + 1.0 / float(os.environ.get('LEO_ENCRYPT_HZ', '24'))
        tpl = _rep_tpl[_enc_i % len(_rep_tpl)]
        _enc_i += 1
        _enc_counter = (_enc_counter + 0x101) & 0xFFFFFFFF
        try:
            report = build_app_report(tpl, _enc_counter, last_video_seq)
            plain = b'\xf1\xce' + report[2:]
            from leo_rtc import cs2 as _cs2
            sock2.sendto(_cs2.encrypt(plain), media_peer)
        except Exception:
            pass
    if media_peer and now >= nxt_hb80:
        nxt_hb80 = now + 1.0
        try:
            sock2.sendto(b'\x80\xc9\x00\x01\x00\x00\x00\x01', media_peer)
        except Exception:
            pass
    if _rep_tpl and media_peer and now >= nxt_report:
        nxt_report = now + 1.0 / float(os.environ.get('LEO_REPORT_HZ', '4'))
        tpl = _rep_tpl[_rep_i % len(_rep_tpl)]
        _rep_i += 1
        _rep_counter = (_rep_counter + 0x101) & 0xFFFFFFFF
        try:
            report = build_app_report(tpl, _rep_counter, last_video_seq)
            # 平文（90ce）はアプリ実測 4/s、暗号形（b0ce）は 24/s。別々に送る。
            if os.environ.get('LEO_REPORT_PLAIN', '1') != '0':
                sock2.sendto(report, media_peer)
            # アプリは平文（90ce）と暗号形（b0ce = f1ce の CS2）を併送している。

        except Exception:
            pass
    # アプリはセッションを切らずに映像停止時「開始コマンド(1003)」を再送して
    # 同じセッションで流し直す（seq リセットは正常）。LEO_1003_RETRY=1 で有効化。
    in_rearm = (REARM_LIMIT > 0 and last_video_t
                and (now - last_video_t) > VIDEO_IDLE)
    if in_rearm and rearm_until == 0.0:
        rearm_until = last_video_t + VIDEO_IDLE + REARM_LIMIT
        print('REARM start (limit=%.0fs wait=%.0fs)' % (REARM_LIMIT, REARM_WAIT))
    # 映像中に開始時とバイト同一の calls を再送（LEO_CALL_REPLAY 秒間隔）。
    _replay = float(os.environ.get('LEO_CALL_REPLAY', '0'))
    if (_replay > 0 and last_video_t and (now - last_video_t) < 3.0 and now >= nxt_call_replay):
        nxt_call_replay = now + _replay
        try:
            for _p2p in ('priv1', 'priv_p2p'):
                _u, _m = call_msgs[_p2p]
                c.send(_m, host)
            print('>> call replay (identical bytes)')
        except Exception as _e:
            print('call replay err', _e)
    # 映像が流れている最中も 1003 を定期再送して延長を試す（LEO_1003_KEEP 秒間隔）。
    _keep = float(os.environ.get('LEO_1003_KEEP', '0'))
    if (_keep > 0 and media_peer and last_video_t
            and (now - last_video_t) < 3.0 and now >= nxt_1003_keep):
        nxt_1003_keep = now + _keep
        ctr_1003 += 1
        if os.environ.get('LEO_CALL_KEEP'):
            try:
                _msgs = build_calls(int(time.time()))
                for _p2p in ('priv1', 'priv_p2p'):
                    _u, _m = _msgs[_p2p]
                    c.send(_m, host)
                print('>> call keep (fresh calls)')
            except Exception as _e:
                print('call keep err', _e)
        try:
            _fr = ank_frame(enc_frame(0x546, env1003, K2, ctr_1003), SSRC_MEDIA, ank_counter)
            sock2.sendto(_fr, media_peer)
            ank_counter += 1
            print('>> 1003 keep media (ctr=%#x)' % ctr_1003)
        except Exception:
            pass
        if kcp is not None:
            try:
                kcp.push(notify(enc_frame(0x546, env1003, K2, ctr_1003), ms(), kcp.sn))
                print('>> 1003 keep kcp')
            except Exception:
                pass
    if (os.environ.get('LEO_1003_RETRY') and not in_rearm
            and media_peer and last_media_t and (now - last_media_t) > 2.0
            and now >= nxt_1003_retry):
        nxt_1003_retry = now + 3.0
        ctr_1003 += 1
        try:
            _fr = ank_frame(enc_frame(0x546, env1003, K2, ctr_1003), SSRC_MEDIA, ank_counter)
            sock2.sendto(_fr, media_peer)
            ank_counter += 1
            print('>> 1003 retry media (video idle %.1fs, ctr=%#x)' % (now - last_media_t, ctr_1003))
        except Exception as _e:
            print('1003 retry media err', _e)
        if kcp is not None:
            try:
                kcp.push(notify(enc_frame(0x546, env1003, K2, ctr_1003), ms(), kcp.sn))
                print('>> 1003 retry kcp (ctr=%#x)' % ctr_1003)
            except Exception as _e:
                print('1003 retry kcp err', _e)
    if (os.environ.get('LEO_DRWACK', '1') != '0') and media_peer and now >= nxt_ack and ack_seqs:
        nxt_ack = now + 0.1
        try:
            from leo_rtc.report import enc_drw_ack
            sock2.sendto(enc_drw_ack(ack_seqs[-64:]), media_peer)
        except Exception:
            pass
    if (media_peer or hosts2) and now >= nxt_mkeep:
        tgt = media_peer or (hosts2[0] if hosts2 else None)
        if tgt:
            ka = ank_frame(b'', SSRC_MEDIA, ank_counter, mask=b'\x04\xaa\xaa\xaa')
            sock2.sendto(ka, tgt)
            ank_counter += 1
        nxt_mkeep = now + 0.6
    if (media_peer or hosts2) and now >= nxt_ice2:
        for h in ([media_peer] if media_peer else hosts2[-4:]):
            sock2.sendto(_sreq(os.urandom(12), UFRAG2.decode(), PWD2), h)
        nxt_ice2 = now + 1.5
    if now >= nxt_info:
        c.info(u1, {"file_candidate": f"a=candidate:1 1 UDP 2122317823 {lip} {port1} typ host", "file_candidate_num": 0})
        c.info(u2, {"candidate": CAND2})
        if turn_sock is not None and CAND2 != CAND2_RELAY:
            c.info(u2, {"candidate": CAND2_RELAY})
        nxt_info = now + 5.0
    if kcp is not None and stage < len(matrix) and now >= nxt_cmd and now - start_loop > (13 + ORACLE_WAIT):
        label, kind, key, ctr = matrix[stage]
        if kind == 'kcp1306':
            kcp.push(notify(enc_frame(0x546, env1306, key, ctr), ms(), kcp.sn))
            print('>> %s (KCP 1306, key=%r)' % (label, key))
        elif kind == 'kcp1103':
            kcp.push(notify(enc_frame(0x44f, app1103, key, ctr), ms(), kcp.sn))
            print('>> %s (KCP 1103, key=%r)' % (label, key))
        elif kind == 'kcp401':
            kcp.push(notify(enc_frame(0x401, frame401, key, ctr), ms(), kcp.sn))
            print('>> %s (KCP 401, pub=%s...)' % (label, ECC_PUB_HEX[:16].decode()))
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

    if _ce and media_peer and now >= nxt_ce:
        nxt_ce = now + 0.01
        try:
            sock2.sendto(_ce[_ce_i % len(_ce)], media_peer)
            _ce_i += 1
        except Exception:
            pass
    if False and stage >= len(matrix) and (media_peer or hosts2) and now >= nxt_1003:
        nxt_1003 = now + 12.0
        tgt = media_peer or (hosts2[0] if hosts2 else None)
        ctr_1003 += 1
        try:
            fr = ank_frame(enc_frame(0x546, env1003, K2, ctr_1003), SSRC_MEDIA, ank_counter)
            sock2.sendto(fr, tgt)
            ank_counter += 1
            print('>> media1003-keep (MEDIA 1003, ctr=%#x) to %s' % (ctr_1003, tgt))
        except Exception as e:
            print('keep1003 err', e)
        try:
            kcp.push(notify(enc_frame(0x546, env1003, K2, ctr_1003), ms(), kcp.sn))
            print('>> kcp1003-keep (KCP 1003)')
        except Exception:
            pass
    if last_media_t == 0 and now - start_loop > float(os.environ.get('LEO_NO_MEDIA_LIMIT', '90')):
        # 映像が一度も来ないまま長く粘ってもカメラは起きない（連打は逆効果）。
        # 一度切って間隔を空け直す。
        print('NO MEDIA %.0fs -> reconnect' % (now - start_loop))
        break
    if in_rearm and now >= rearm_until:
        print('REARM limit -> reconnect')
        break
    if in_rearm and now >= nxt_wake:
        nxt_wake = now + REARM_WAIT
        try:
            _msgs = build_calls(int(time.time()))
            for _p2p in ('priv1', 'priv_p2p'):
                _u, _m = _msgs[_p2p]
                c.send(_m, host)
            print('>> rearm calls sent')
        except Exception as _e:
            print('rearm calls err', _e)
        ctr_1003 += 1
        try:
            tgt = media_peer or (hosts2[0] if hosts2 else None)
            if tgt:
                fr = ank_frame(enc_frame(0x546, env1003, K2, ctr_1003), SSRC_MEDIA, ank_counter)
                sock2.sendto(fr, tgt)
                ank_counter += 1
                print('>> rearm media1003 (ctr=%#x)' % ctr_1003)
        except Exception:
            pass
        if kcp is not None:
            try:
                kcp.push(notify(enc_frame(0x546, env1003, K2, ctr_1003), ms(), kcp.sn))
                print('>> rearm kcp1003')
            except Exception:
                pass
    WAKE_WAIT = float(os.environ.get('LEO_WAKE_WAIT', '25'))
    if last_media_t == 0 and now >= nxt_wake and now - start_loop > WAKE_WAIT:
        nxt_wake = now + WAKE_WAIT
        try:
            _msgs = build_calls(int(time.time()))
            for _p2p in ('priv1', 'priv_p2p'):
                _u, _m = _msgs[_p2p]
                c.send(_m, host)
            print('>> wake retry (fresh calls) media_pkts=%d' % media_pkts)
        except Exception as _e:
            print('wake retry err', _e)
        try:
            tgt = media_peer or (hosts2[0] if hosts2 else None)
            if tgt:
                fr = ank_frame(enc_frame(0x546, env1003, K2, ctr_1003), SSRC_MEDIA, ank_counter)
                sock2.sendto(fr, tgt)
                ank_counter += 1
                print('>> wake retry media1003 sent')
        except Exception:
            pass
    if last_video_t and now - last_video_t > VIDEO_IDLE and not in_rearm:
        # カメラに closeLive(1004) を送って正常終了させる（次の付与が早くなるか）。
        if os.environ.get('LEO_CLOSE_1004', '1') != '0':
            ctr_1003 += 1
            try:
                tgt = media_peer or (hosts2[0] if hosts2 else None)
                if tgt:
                    fr = ank_frame(enc_frame(0x546, env1004, K2, ctr_1003), SSRC_MEDIA, ank_counter)
                    sock2.sendto(fr, tgt)
                    ank_counter += 1
                    print('>> closeLive 1004 media (ctr=%#x)' % ctr_1003)
            except Exception:
                pass
            if kcp is not None:
                try:
                    kcp.push(notify(enc_frame(0x546, env1004, K2, ctr_1003), ms(), kcp.sn))
                    print('>> closeLive 1004 kcp')
                except Exception:
                    pass
            try:
                with open(OUT + '/close_ts', 'w') as _cf:
                    _cf.write(str(int(now)))
            except Exception:
                pass
        print('VIDEO IDLE %.0fs -> reconnect' % VIDEO_IDLE)
        break
    if last_media_t and now - last_media_t > 20.0 and not in_rearm:
        print('MEDIA IDLE 20s -> reconnect')
        break
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
                    lan_only = sock2 is turn_sock and turn_sock is not None and ipaddress.ip_address(h[0]).is_private
                    if h not in hosts2 and not lan_only:
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
                # TURN 経由では、カメラの接続確認の送信元（グローバル側）が映像の相手になる。
                # LAN の候補は中継から届かない。
                if turn_sock is not None and sk is sock2 and media_peer is None \
                        and not ipaddress.ip_address(peer[0]).is_private:
                    media_peer = peer
                    print('media peer set (turn)', peer)
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
            rtcp_reports.observe(data)
            if data[:1] == b'\x90' and data[1:2] in (b'\x61', b'\xe1', b'\x2f', b'\xef'):
                last_media_t = now
                if data[1:2] in (b'\x61', b'\xe1'):
                    last_video_t = now
            if data[:1] == b'\x90' or data[:1] == b'\x80':
                if len(data) >= 4:
                    _seq = int.from_bytes(data[2:4], 'big')
                    ack_seqs.append(_seq)
                    if data[1] in (0x61, 0xE1):
                        last_video_seq = _seq
                    elif data[1] == 0x2F:
                        last_902f_seq = _seq
                    elif data[1] == 0xEF:
                        last_audio_seq = _seq
                    if len(ack_seqs) > 4096:
                        del ack_seqs[:2048]
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
print('DONE media packets', media_pkts, 'hello', hello, 'paths', getattr(sock2, 'counts', None))
print('KINDS', sorted(media_kinds.items(), key=lambda kv:-kv[1]))
