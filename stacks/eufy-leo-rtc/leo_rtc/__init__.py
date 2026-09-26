"""Reverse-engineered native leo_rtc client (eufy standalone battery cameras).

See README.md and docs/development/H05-eufy-leo-rtc.md.
"""

from .client import LeoRtcClient, LeoRtcError, Message, Session
from .media import SRTP_KEY, build_offer_sdp
from .protocol import (
    CALL_PRIV1,
    CALL_PRIV_P2P,
    TYPE_CALL,
    TYPE_DISCOVER,
    TYPE_HANGUP,
    TYPE_INFO,
    TYPE_LOGIN,
    TYPE_NAMES,
)
from .sdpinfo import build_sdp_info

__all__ = [
    'LeoRtcClient',
    'LeoRtcError',
    'Message',
    'Session',
    'SRTP_KEY',
    'build_offer_sdp',
    'build_sdp_info',
    'CALL_PRIV1',
    'CALL_PRIV_P2P',
    'TYPE_CALL',
    'TYPE_DISCOVER',
    'TYPE_HANGUP',
    'TYPE_INFO',
    'TYPE_LOGIN',
    'TYPE_NAMES',
]
