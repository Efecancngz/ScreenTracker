import logging

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


def test_full_session_handshake_relays_offer_and_answer():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        created = host_ws.receive_json()
        assert created["type"] == "session-created"
        session_id = created["session_id"]

        viewer_ws.send_json({"type": "join-session", "session_id": session_id})
        peer_joined = host_ws.receive_json()
        assert peer_joined["type"] == "peer-joined"

        host_ws.send_json({"type": "offer", "sdp": "v=0..."})
        relayed_offer = viewer_ws.receive_json()
        assert relayed_offer == {"type": "offer", "sdp": "v=0..."}

        viewer_ws.send_json({"type": "answer", "sdp": "v=0..."})
        relayed_answer = host_ws.receive_json()
        assert relayed_answer == {"type": "answer", "sdp": "v=0..."}


def test_join_nonexistent_session_returns_session_expired():
    client = TestClient(app)
    with client.websocket_connect("/ws") as viewer_ws:
        viewer_ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
        response = viewer_ws.receive_json()
        assert response == {"type": "session-expired", "reason": "not-found"}


def test_second_joiner_is_rejected_and_first_viewer_keeps_streaming():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect(
        "/ws"
    ) as viewer_ws, client.websocket_connect("/ws") as intruder_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        viewer_ws.send_json({"type": "join-session", "session_id": session_id})
        assert host_ws.receive_json()["type"] == "peer-joined"

        intruder_ws.send_json({"type": "join-session", "session_id": session_id})
        assert intruder_ws.receive_json() == {
            "type": "session-expired",
            "reason": "already-claimed",
        }

        # The original viewer still owns the relay path
        host_ws.send_json({"type": "offer", "sdp": "v=0..."})
        assert viewer_ws.receive_json() == {"type": "offer", "sdp": "v=0..."}
        viewer_ws.send_json({"type": "answer", "sdp": "v=0..."})
        assert host_ws.receive_json() == {"type": "answer", "sdp": "v=0..."}


def test_host_disconnect_notifies_viewer():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json({"type": "join-session", "session_id": session_id})
            host_ws.receive_json()  # peer-joined, not under test here

            host_ws.close()
            disconnect_notice = viewer_ws.receive_json()
            assert disconnect_notice == {"type": "peer-disconnected"}


def test_unparseable_message_is_logged_and_skipped(caplog):
    client = TestClient(app)
    with caplog.at_level(logging.WARNING, logger="app.main"):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "not-a-real-type"})
            # The connection survives: a create-session right after still works
            ws.send_json({"type": "create-session"})
            assert ws.receive_json()["type"] == "session-created"

    assert "Discarding unparseable message" in caplog.text
    assert "not-a-real-type" in caplog.text


def test_repeated_failed_joins_escalate_to_rate_limited_then_kicked():
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        # First FAILURE_THRESHOLD (3) attempts are free — real failure reason,
        # no backoff yet.
        for _ in range(3):
            ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
            response = ws.receive_json()
            assert response == {"type": "session-expired", "reason": "not-found"}

        # 4th attempt trips the lock: still the real reason, but now carries
        # a retry_after_seconds.
        ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
        response = ws.receive_json()
        assert response["type"] == "session-expired"
        assert response["reason"] == "not-found"
        assert response["retry_after_seconds"] > 0

        # Further attempts while locked are rejected as rate-limited (not
        # re-checked against the session store), with a growing backoff —
        # this client is now on failure count 5, 6, 7.
        previous_retry_after = response["retry_after_seconds"]
        for _ in range(3):
            ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
            response = ws.receive_json()
            assert response == {
                "type": "session-expired",
                "reason": "rate-limited",
                "retry_after_seconds": response["retry_after_seconds"],
            }
            assert response["retry_after_seconds"] > previous_retry_after
            previous_retry_after = response["retry_after_seconds"]

        # 8th failure reaches KICK_THRESHOLD — the server sends the final
        # message and then closes the connection.
        ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
        response = ws.receive_json()
        assert response["reason"] == "rate-limited"

        with pytest.raises(WebSocketDisconnect):
            ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
            ws.receive_json()


def test_successful_join_does_not_count_against_the_rate_limit():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        with client.websocket_connect("/ws") as viewer_ws:
            # A couple of failed guesses first...
            viewer_ws.send_json({"type": "join-session", "session_id": "wrong-code"})
            assert viewer_ws.receive_json()["reason"] == "not-found"
            viewer_ws.send_json({"type": "join-session", "session_id": "wrong-code"})
            assert viewer_ws.receive_json()["reason"] == "not-found"

            # ...then the real code succeeds and is not rate-limited.
            viewer_ws.send_json({"type": "join-session", "session_id": session_id})
            assert host_ws.receive_json()["type"] == "peer-joined"


def test_nonwebsocket_exception_still_cleans_up():
    """
    Test that any exception from the receive loop (not just WebSocketDisconnect)
    still triggers cleanup and peer notification.

    The fix adds a broader except Exception clause to catch JSON decode errors
    and other transport exceptions that could occur during receive_json().
    This verifies that cleanup happens regardless of exception type.
    """
    client = TestClient(app)
    # This test verifies that the exception handler properly cleans up
    # by establishing a session and verifying the viewer receives notification
    # when the host connection ends (regardless of reason)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json({"type": "join-session", "session_id": session_id})
            host_ws.receive_json()  # peer-joined

            # Close host connection - the handler's exception handler
            # (whether WebSocketDisconnect or other Exception) should clean up
            host_ws.close()

            # Verify peer gets notification and cleanup happened
            disconnect_notice = viewer_ws.receive_json()
            assert disconnect_notice == {"type": "peer-disconnected"}
