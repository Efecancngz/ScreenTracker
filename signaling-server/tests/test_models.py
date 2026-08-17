import pytest

from app.models import (
    IceCandidateMessage,
    JoinSessionMessage,
    SdpMessage,
    parse_inbound_message,
)


def test_parse_join_session_message():
    parsed = parse_inbound_message({"type": "join-session", "session_id": "abc123"})
    assert isinstance(parsed, JoinSessionMessage)
    assert parsed.session_id == "abc123"


def test_parse_offer_message():
    parsed = parse_inbound_message({"type": "offer", "sdp": "v=0..."})
    assert isinstance(parsed, SdpMessage)
    assert parsed.type == "offer"


def test_parse_ice_candidate_message_accepts_browser_candidate_init():
    """The viewer sends RTCIceCandidate.toJSON() — a nested object, not a string."""
    parsed = parse_inbound_message(
        {
            "type": "ice-candidate",
            "candidate": {
                "candidate": "candidate:1 1 UDP 2130706431 192.168.1.5 54321 typ host",
                "sdpMid": "0",
                "sdpMLineIndex": 0,
                "usernameFragment": "abcd",
            },
        }
    )
    assert isinstance(parsed, IceCandidateMessage)
    assert parsed.candidate["sdpMid"] == "0"
    assert parsed.candidate["sdpMLineIndex"] == 0


def test_parse_unknown_type_raises():
    with pytest.raises(ValueError):
        parse_inbound_message({"type": "not-a-real-type"})
