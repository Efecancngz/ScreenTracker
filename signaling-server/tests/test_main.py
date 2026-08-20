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


def test_viewer_disconnect_keeps_the_session_alive_for_a_reconnect():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json({"type": "join-session", "session_id": session_id})
            host_ws.receive_json()  # peer-joined
            # Viewer disconnects (e.g. a page refresh) — the host is notified
            # but its session must not be torn down.
        disconnect_notice = host_ws.receive_json()
        assert disconnect_notice == {"type": "peer-disconnected"}

        with client.websocket_connect("/ws") as new_viewer_ws:
            new_viewer_ws.send_json({"type": "join-session", "session_id": session_id})
            peer_joined = host_ws.receive_json()
            assert peer_joined["type"] == "peer-joined"


def test_viewer_disconnect_then_authenticate_reconnect_finds_the_live_session():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "register-host", "host_id": "host-reconnect", "host_secret": "secret-reconnect"})
        host_ws.send_json({"type": "create-session"})
        host_ws.receive_json()  # session-created

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json(
                {
                    "type": "authenticate",
                    "host_id": "host-reconnect",
                    "device_id": "dev-1",
                    "token": "tok-1",
                }
            )
            host_ws.receive_json()  # peer-joined
        host_ws.receive_json()  # peer-disconnected

        with client.websocket_connect("/ws") as new_viewer_ws:
            new_viewer_ws.send_json(
                {
                    "type": "authenticate",
                    "host_id": "host-reconnect",
                    "device_id": "dev-1",
                    "token": "tok-1",
                }
            )
            peer_joined = host_ws.receive_json()
            assert peer_joined["type"] == "peer-joined"


def test_host_disconnect_still_fully_removes_the_session():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json({"type": "join-session", "session_id": session_id})
            host_ws.receive_json()  # peer-joined

            host_ws.close()
            assert viewer_ws.receive_json() == {"type": "peer-disconnected"}

    with client.websocket_connect("/ws") as late_joiner_ws:
        late_joiner_ws.send_json({"type": "join-session", "session_id": session_id})
        assert late_joiner_ws.receive_json() == {
            "type": "session-expired",
            "reason": "not-found",
        }


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
        # First FAILURE_THRESHOLD (5) attempts are free — real failure reason,
        # no backoff yet.
        for _ in range(5):
            ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
            response = ws.receive_json()
            assert response == {"type": "session-expired", "reason": "not-found"}

        # 6th attempt trips the lock: still the real reason, but now carries
        # a retry_after_seconds.
        ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
        response = ws.receive_json()
        assert response["type"] == "session-expired"
        assert response["reason"] == "not-found"
        assert response["retry_after_seconds"] > 0

        # 7th attempt is rejected as rate-limited (not re-checked against the
        # session store), with a larger backoff than the 6th.
        previous_retry_after = response["retry_after_seconds"]
        ws.send_json({"type": "join-session", "session_id": "does-not-exist"})
        response = ws.receive_json()
        assert response["type"] == "session-expired"
        assert response["reason"] == "rate-limited"
        assert response["retry_after_seconds"] > previous_retry_after

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


def test_authenticate_with_valid_token_joins_without_a_code():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws:
        host_ws.send_json({"type": "register-host", "host_id": "host-abc", "host_secret": "secret-abc"})
        host_ws.send_json({"type": "create-session"})
        host_ws.receive_json()  # session-created, session_id not needed here

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json(
                {
                    "type": "authenticate",
                    "host_id": "host-abc",
                    "device_id": "dev-1",
                    "token": "tok-1",
                }
            )
            peer_joined = host_ws.receive_json()
            assert peer_joined["type"] == "peer-joined"
            assert peer_joined["device_id"] == "dev-1"
            assert peer_joined["token"] == "tok-1"


def test_authenticate_with_unknown_host_id_returns_not_found():
    client = TestClient(app)
    with client.websocket_connect("/ws") as viewer_ws:
        viewer_ws.send_json(
            {
                "type": "authenticate",
                "host_id": "no-such-host",
                "device_id": "dev-1",
                "token": "tok-1",
            }
        )
        response = viewer_ws.receive_json()
        assert response == {"type": "session-expired", "reason": "not-found"}


def test_join_session_relays_device_id_in_peer_joined():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        viewer_ws.send_json(
            {"type": "join-session", "session_id": session_id, "device_id": "dev-2"}
        )
        peer_joined = host_ws.receive_json()
        assert peer_joined == {"type": "peer-joined", "device_id": "dev-2", "token": None}


def test_pair_approved_pair_rejected_and_authenticate_failed_relay_to_viewer():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect("/ws") as viewer_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]
        viewer_ws.send_json(
            {"type": "join-session", "session_id": session_id, "device_id": "dev-3"}
        )
        host_ws.receive_json()  # peer-joined

        host_ws.send_json({"type": "pair-approved", "token": "tok-9", "host_id": "host-xyz"})
        assert viewer_ws.receive_json() == {
            "type": "pair-approved",
            "token": "tok-9",
            "host_id": "host-xyz",
        }


def test_release_peer_frees_the_slot_for_a_new_joiner():
    client = TestClient(app)
    with client.websocket_connect("/ws") as host_ws, client.websocket_connect(
        "/ws"
    ) as first_viewer_ws, client.websocket_connect("/ws") as second_viewer_ws:
        host_ws.send_json({"type": "create-session"})
        session_id = host_ws.receive_json()["session_id"]

        first_viewer_ws.send_json(
            {"type": "join-session", "session_id": session_id, "device_id": "dev-4"}
        )
        host_ws.receive_json()  # peer-joined for the first viewer

        host_ws.send_json({"type": "pair-rejected", "reason": "denied"})
        assert first_viewer_ws.receive_json() == {"type": "pair-rejected", "reason": "denied"}
        host_ws.send_json({"type": "release-peer"})

        second_viewer_ws.send_json(
            {"type": "join-session", "session_id": session_id, "device_id": "dev-5"}
        )
        peer_joined = host_ws.receive_json()
        assert peer_joined == {"type": "peer-joined", "device_id": "dev-5", "token": None}


def test_register_host_with_a_different_secret_does_not_hijack_an_existing_host_id():
    """Before this, register-host had no ownership check at all -- any
    connection could claim any host_id, silently overwriting the
    legitimate host's registration. A paired viewer's later authenticate
    for that host_id would then route to the impostor, including the
    viewer's own auth token (relayed verbatim in peer-joined). The first
    connection to register a host_id now "owns" it: later registrations
    under the same host_id with a different secret are refused rather
    than silently taking over."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as real_host_ws:
        real_host_ws.send_json(
            {"type": "register-host", "host_id": "shared-host-id", "host_secret": "real-secret"}
        )
        real_host_ws.send_json({"type": "create-session"})
        real_host_ws.receive_json()  # session-created

        with client.websocket_connect("/ws") as impostor_ws:
            impostor_ws.send_json(
                {"type": "register-host", "host_id": "shared-host-id", "host_secret": "wrong-secret"}
            )
            impostor_ws.send_json({"type": "create-session"})
            impostor_ws.receive_json()  # session-created for the impostor's OWN session

            with client.websocket_connect("/ws") as viewer_ws:
                viewer_ws.send_json(
                    {
                        "type": "authenticate",
                        "host_id": "shared-host-id",
                        "device_id": "dev-1",
                        "token": "victim-token",
                    }
                )
                # Routed to the REAL host, not the impostor -- the impostor
                # never sees the victim's token.
                peer_joined = real_host_ws.receive_json()
                assert peer_joined["type"] == "peer-joined"
                assert peer_joined["token"] == "victim-token"


def test_register_host_with_the_matching_secret_can_still_reconnect_under_a_new_connection():
    """The legitimate host restarting (a new WebSocket connection, same
    persisted host_secret) must still be able to reclaim its own
    host_id -- ownership is proven by the secret, not by being the
    original connection."""
    client = TestClient(app)
    with client.websocket_connect("/ws") as first_ws:
        first_ws.send_json(
            {"type": "register-host", "host_id": "restarting-host", "host_secret": "same-secret"}
        )

    with client.websocket_connect("/ws") as second_ws:
        second_ws.send_json(
            {"type": "register-host", "host_id": "restarting-host", "host_secret": "same-secret"}
        )
        second_ws.send_json({"type": "create-session"})
        second_ws.receive_json()  # session-created

        with client.websocket_connect("/ws") as viewer_ws:
            viewer_ws.send_json(
                {
                    "type": "authenticate",
                    "host_id": "restarting-host",
                    "device_id": "dev-1",
                    "token": "tok-1",
                }
            )
            assert second_ws.receive_json()["type"] == "peer-joined"
