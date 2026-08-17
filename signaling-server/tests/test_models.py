import pytest

from app.models import JoinSessionMessage, SdpMessage, parse_inbound_message


def test_parse_join_session_message():
    parsed = parse_inbound_message({"type": "join-session", "session_id": "abc123"})
    assert isinstance(parsed, JoinSessionMessage)
    assert parsed.session_id == "abc123"


def test_parse_offer_message():
    parsed = parse_inbound_message({"type": "offer", "sdp": "v=0..."})
    assert isinstance(parsed, SdpMessage)
    assert parsed.type == "offer"


def test_parse_unknown_type_raises():
    with pytest.raises(ValueError):
        parse_inbound_message({"type": "not-a-real-type"})
