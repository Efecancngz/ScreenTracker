import time

import pytest

from app.session_manager import (
    SessionAlreadyClaimedError,
    SessionExpiredError,
    SessionManager,
    SessionNotFoundError,
)


def test_create_session_returns_unique_id():
    manager = SessionManager()
    session_a = manager.create_session(host_connection_id="host-1")
    session_b = manager.create_session(host_connection_id="host-2")
    assert session_a.session_id != session_b.session_id


def test_join_session_attaches_viewer():
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    joined = manager.join_session(session.session_id, viewer_connection_id="viewer-1")
    assert joined.viewer_connection_id == "viewer-1"


def test_join_unknown_session_raises():
    manager = SessionManager()
    with pytest.raises(SessionNotFoundError):
        manager.join_session("does-not-exist", viewer_connection_id="viewer-1")


def test_join_already_claimed_session_raises_and_keeps_the_first_viewer():
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1")

    with pytest.raises(SessionAlreadyClaimedError):
        manager.join_session(session.session_id, viewer_connection_id="viewer-2")

    assert manager.get_session(session.session_id).viewer_connection_id == "viewer-1"


def test_rejoin_by_the_same_connection_is_idempotent():
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1")

    rejoined = manager.join_session(session.session_id, viewer_connection_id="viewer-1")

    assert rejoined.viewer_connection_id == "viewer-1"


def test_claimed_session_does_not_expire():
    manager = SessionManager(ttl_seconds=0.01)
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1")
    time.sleep(0.02)

    # A claimed session lives until the host disconnects, not until the TTL
    assert manager.get_session(session.session_id) is not None
    with pytest.raises(SessionAlreadyClaimedError):
        manager.join_session(session.session_id, viewer_connection_id="viewer-2")


def test_join_expired_session_raises_and_removes_it():
    manager = SessionManager(ttl_seconds=0.01)
    session = manager.create_session(host_connection_id="host-1")
    time.sleep(0.02)
    with pytest.raises(SessionExpiredError):
        manager.join_session(session.session_id, viewer_connection_id="viewer-1")
    assert manager.get_session(session.session_id) is None


def test_release_viewer_clears_the_claim_so_a_new_join_succeeds():
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1")

    manager.release_viewer(session.session_id)

    rejoined = manager.join_session(session.session_id, viewer_connection_id="viewer-2")
    assert rejoined.viewer_connection_id == "viewer-2"


def test_release_viewer_on_unknown_session_is_a_no_op():
    manager = SessionManager()
    manager.release_viewer("does-not-exist")  # must not raise


def test_join_by_the_same_device_id_reclaims_a_session_held_by_a_dead_connection():
    # A mobile tab closed (not reloaded) often never sends a clean WS close
    # frame, so the server's disconnect handler never runs and the old
    # connection_id stays the claimant forever. The same device reconnecting
    # gets a new connection_id but the same persisted device_id -- it must
    # be able to take over instead of being told the session is claimed by
    # someone else.
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1", device_id="device-A")

    reclaimed = manager.join_session(
        session.session_id, viewer_connection_id="viewer-2", device_id="device-A"
    )

    assert reclaimed.viewer_connection_id == "viewer-2"


def test_join_by_a_different_device_id_still_raises_already_claimed():
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1", device_id="device-A")

    with pytest.raises(SessionAlreadyClaimedError):
        manager.join_session(session.session_id, viewer_connection_id="viewer-2", device_id="device-B")

    assert manager.get_session(session.session_id).viewer_connection_id == "viewer-1"


def test_join_with_no_device_id_still_raises_already_claimed():
    # No device_id to verify identity with -- must not be treated as a match.
    manager = SessionManager()
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1", device_id="device-A")

    with pytest.raises(SessionAlreadyClaimedError):
        manager.join_session(session.session_id, viewer_connection_id="viewer-2")

    assert manager.get_session(session.session_id).viewer_connection_id == "viewer-1"


def test_released_session_does_not_expire_even_after_the_ttl():
    # A page refresh releases the viewer slot; the reconnect might happen
    # after the original TTL window but must still succeed since the
    # session was already claimed once (the host is still live).
    manager = SessionManager(ttl_seconds=0.01)
    session = manager.create_session(host_connection_id="host-1")
    manager.join_session(session.session_id, viewer_connection_id="viewer-1")
    manager.release_viewer(session.session_id)
    time.sleep(0.02)

    rejoined = manager.join_session(session.session_id, viewer_connection_id="viewer-2")
    assert rejoined.viewer_connection_id == "viewer-2"
