import time

import pytest

from app.session_manager import SessionExpiredError, SessionManager, SessionNotFoundError


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


def test_join_expired_session_raises_and_removes_it():
    manager = SessionManager(ttl_seconds=0.01)
    session = manager.create_session(host_connection_id="host-1")
    time.sleep(0.02)
    with pytest.raises(SessionExpiredError):
        manager.join_session(session.session_id, viewer_connection_id="viewer-1")
    assert manager.get_session(session.session_id) is None
