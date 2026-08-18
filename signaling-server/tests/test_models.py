import pytest

from app.models import (
    AuthenticateMessage,
    IceCandidateMessage,
    JoinSessionMessage,
    PairApprovedMessage,
    PairRejectedMessage,
    ReleasePeerMessage,
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


def test_parse_join_session_message_without_device_id():
    parsed = parse_inbound_message({"type": "join-session", "session_id": "abc123"})
    assert isinstance(parsed, JoinSessionMessage)
    assert parsed.device_id is None


def test_parse_join_session_message_with_device_id():
    parsed = parse_inbound_message(
        {"type": "join-session", "session_id": "abc123", "device_id": "dev-1"}
    )
    assert isinstance(parsed, JoinSessionMessage)
    assert parsed.device_id == "dev-1"


def test_parse_register_host_message():
    parsed = parse_inbound_message({"type": "register-host", "host_id": "host-1"})
    assert parsed.host_id == "host-1"


def test_parse_authenticate_message():
    parsed = parse_inbound_message(
        {"type": "authenticate", "host_id": "host-1", "device_id": "dev-1", "token": "tok-1"}
    )
    assert isinstance(parsed, AuthenticateMessage)
    assert parsed.host_id == "host-1"
    assert parsed.device_id == "dev-1"
    assert parsed.token == "tok-1"


def test_parse_pair_approved_message():
    parsed = parse_inbound_message(
        {"type": "pair-approved", "token": "tok-1", "host_id": "host-1"}
    )
    assert isinstance(parsed, PairApprovedMessage)


def test_parse_pair_rejected_message():
    parsed = parse_inbound_message({"type": "pair-rejected", "reason": "denied"})
    assert isinstance(parsed, PairRejectedMessage)


def test_parse_release_peer_message():
    parsed = parse_inbound_message({"type": "release-peer"})
    assert isinstance(parsed, ReleasePeerMessage)
