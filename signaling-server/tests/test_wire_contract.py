"""
Contract tests pinning the exact payload shapes the viewer app puts on the wire.

The viewer builds these payloads in `viewer-app/src/App.tsx`; anything the
server refuses to parse is dropped silently by the endpoint's `except
ValueError: continue`, so a shape mismatch is invisible without these tests.
"""

from fastapi.testclient import TestClient

from app.main import app

# Exactly what `RTCIceCandidate.toJSON()` produces in a browser
VIEWER_ICE_CANDIDATE = {
    "type": "ice-candidate",
    "candidate": {
        "candidate": "candidate:842163049 1 udp 1677729535 203.0.113.9 54321 typ srflx "
        "raddr 192.168.1.5 rport 54321 generation 0 ufrag Xm1a network-cost 999",
        "sdpMid": "0",
        "sdpMLineIndex": 0,
        "usernameFragment": "Xm1a",
    },
}

VIEWER_ANSWER = {
    "type": "answer",
    "sdp": "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\n",
}


def test_viewer_ice_candidate_payload_is_relayed_verbatim():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]
        # join-session as the viewer sends it: a plain session_id string
        viewer_ws.send_json({"type": "join-session", "session_id": session_id})
        assert host_ws.receive_json() == {"type": "peer-joined", "device_id": None, "token": None}

        viewer_ws.send_json(VIEWER_ICE_CANDIDATE)

        assert host_ws.receive_json() == VIEWER_ICE_CANDIDATE


def test_viewer_answer_payload_is_relayed_verbatim():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]
        viewer_ws.send_json({"type": "join-session", "session_id": session_id})
        assert host_ws.receive_json() == {"type": "peer-joined", "device_id": None, "token": None}

        viewer_ws.send_json(VIEWER_ANSWER)

        assert host_ws.receive_json() == VIEWER_ANSWER


def test_viewer_join_session_payload_is_accepted():
    """A session_id string straight out of the six-box code form."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        created = host_ws.receive_json()
        assert isinstance(created["session_id"], str)

        viewer_ws.send_json({"type": "join-session", "session_id": created["session_id"]})

        assert host_ws.receive_json() == {"type": "peer-joined", "device_id": None, "token": None}
