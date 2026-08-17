import secrets
import time
from dataclasses import dataclass, field

SESSION_TTL_SECONDS = 300.0  # 5 minutes to be claimed by a viewer

# 6 characters from a 32-symbol alphabet is ~30 bits of entropy — combined
# with the 5-minute TTL, guessing a live code is impractical. The alphabet
# drops 0/O/1/I/L so a code read aloud or hand-typed on a phone can't be
# misread (matches the viewer's segmented 6-box code input).
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6


@dataclass
class Session:
    session_id: str
    host_connection_id: str
    viewer_connection_id: str | None = None
    created_at: float = field(default_factory=time.monotonic)


class SessionNotFoundError(Exception):
    pass


class SessionExpiredError(Exception):
    pass


class SessionAlreadyClaimedError(Exception):
    pass


class SessionManager:
    def __init__(self, ttl_seconds: float = SESSION_TTL_SECONDS) -> None:
        self._sessions: dict[str, Session] = {}
        self._ttl_seconds = ttl_seconds

    def create_session(self, host_connection_id: str) -> Session:
        session_id = self._generate_unique_code()
        session = Session(session_id=session_id, host_connection_id=host_connection_id)
        self._sessions[session_id] = session
        return session

    def _generate_unique_code(self) -> str:
        while True:
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
            if code not in self._sessions:
                return code

    def join_session(self, session_id: str, viewer_connection_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        if session.viewer_connection_id is not None:
            # A claimed session is never handed to a second viewer: silently
            # overwriting would kick the first viewer off with no notice. It
            # also stops expiring — the host's disconnect cleans it up.
            if session.viewer_connection_id == viewer_connection_id:
                return session
            raise SessionAlreadyClaimedError(session_id)
        if self._is_expired(session):
            del self._sessions[session_id]
            raise SessionExpiredError(session_id)
        session.viewer_connection_id = viewer_connection_id
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def release_viewer(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.viewer_connection_id = None

    def _is_expired(self, session: Session) -> bool:
        return (time.monotonic() - session.created_at) > self._ttl_seconds
