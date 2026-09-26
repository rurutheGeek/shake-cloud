"""Media negotiation constants recovered from libmega_media_sdk.so.

The device's SDP answer (``WebrtcApp_Event_NewSetRemoteSDP*``) is a fixed
template with SDES-SRTP: there is no DTLS fingerprint, and the SRTP key is
hardcoded in the firmware. The video is H.264 (payload 99) / H.265 (97) plus
flexfec (125), and the audio is opus (111).

The signalling flow (see H05):
  1. priv1 scall with sdp_info -> 100 triggers the app's file agent.
  2. The device sends ``file_candidate`` info messages (host/srflx/relay).
  3. The app answers each with an info 200 echo and runs ICE (libjuice) with
     the sdp_info ICE credentials, then KCP/DTLS over the connection.
  4. Media payloads are decrypted with the sdp_info crypto key/IV.
"""

from __future__ import annotations

SRTP_KEY = 'FvLcvU2P3ZWmQxgPAgcDu7Zl9vftYElFOjEzhWs5'
VIDEO_CODECS = {'H265': 97, 'H264': 99, 'flexfec-03': 125}
AUDIO_CODECS = {'opus': 111}


def build_offer_sdp(ufrag: str, pwd: str, *, candidates=(), ssrc: int = 1,
                    srtp_key: str = SRTP_KEY) -> str:
    """Build the client's local SDP for the device (libjingle template)."""
    lines = [
        'v=0',
        'o=- 1751872 1751872 IN IP4 127.0.0.1',
        's=Anker Webrtc Stream',
        't=0 0',
        'a=group:BUNDLE 0 1',
        'a=msid-semantic: WMS b350J',
        'm=audio 1 RTP/SAVPF 111',
        'c=IN IP4 127.0.0.1',
        'a=mid:0',
        'a=extmap:9 anker-qos-feedback:transport-sequence',
        'a=sendrecv',
        'a=rtcp-mux',
        f'a=ice-ufrag:{ufrag}',
        f'a=ice-pwd:{pwd}',
        f'a=crypto:1 AES_CM_128_HMAC_SHA1_80 inline:{srtp_key}',
        'a=setup:actpass',
        'a=rtpmap:111 opus/48000/2',
        'a=fmtp:111 maxplaybackrate=48000;stereo=1;minptime=10;maxptime=80;useinbandfec=1',
        f'a=ssrc:{ssrc} cname:uIGCl7ux',
        'm=video 1 RTP/SAVPF 97 99 125',
        'c=IN IP4 0.0.0.0',
        'a=mid:1',
        'a=extmap:2 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time',
        'a=extmap:3 http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01',
        'a=extmap:5 http://www.webrtc.org/experiments/rtp-hdrext/playout-delay',
        'a=extmap:6 http://www.webrtc.org/experiments/rtp-hdrext/abs-capture-time',
        'a=extmap:9 anker-qos-feedback:transport-sequence',
        'a=recvonly',
        'a=rtcp-mux',
        f'a=ice-ufrag:{ufrag}',
        f'a=ice-pwd:{pwd}',
        f'a=crypto:1 AES_CM_128_HMAC_SHA1_80 inline:{srtp_key}',
        'a=setup:actpass',
        'a=rtpmap:97 H265/90000',
        'a=rtcp-fb:97 nack',
        'a=rtcp-fb:97 nack pli',
        'a=rtcp-fb:97 ccm fir',
        'a=rtpmap:99 H264/90000',
        'a=rtcp-fb:99 nack',
        'a=rtcp-fb:99 nack pli',
        'a=rtcp-fb:99 ccm fir',
        'a=rtpmap:125 flexfec-03/90000',
        'a=fmtp:125 repair-window=10000000',
    ]
    lines.extend(candidates)
    return '\r\n'.join(lines) + '\r\n'
