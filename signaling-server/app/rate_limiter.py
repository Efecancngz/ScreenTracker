import time
from collections.abc import Callable

# The first few failed join attempts are free (typos happen); only sustained
# guessing gets penalized, and the penalty compounds so a determined guesser
# slows to a crawl instead of hammering the server at full speed.
FAILURE_THRESHOLD = 5
BASE_BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 120.0
KICK_THRESHOLD = 8


def backoff_seconds_for_count(
    count: int,
    failure_threshold: int = FAILURE_THRESHOLD,
    base_backoff_seconds: float = BASE_BACKOFF_SECONDS,
    max_backoff_seconds: float = MAX_BACKOFF_SECONDS,
) -> float:
    if count <= failure_threshold:
        return 0.0
    doublings = count - failure_threshold - 1
    return min(base_backoff_seconds * (2**doublings), max_backoff_seconds)


class RateLimiter:
    """Tracks failed join-session attempts per key (typically an IP address).

    In-memory only, matching the rest of the signaling server's Phase 1
    architecture (no persistent store).
    """

    def __init__(
        self,
        failure_threshold: int = FAILURE_THRESHOLD,
        base_backoff_seconds: float = BASE_BACKOFF_SECONDS,
        max_backoff_seconds: float = MAX_BACKOFF_SECONDS,
        kick_threshold: int = KICK_THRESHOLD,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._base_backoff_seconds = base_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._kick_threshold = kick_threshold
        self._clock = clock
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, float] = {}

    def seconds_until_unlocked(self, key: str) -> float:
        locked_until = self._locked_until.get(key, 0.0)
        remaining = locked_until - self._clock()
        return max(0.0, remaining)

    def record_failure(self, key: str) -> None:
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        backoff = backoff_seconds_for_count(
            count,
            self._failure_threshold,
            self._base_backoff_seconds,
            self._max_backoff_seconds,
        )
        if backoff > 0:
            self._locked_until[key] = self._clock() + backoff

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)

    def should_kick(self, key: str) -> bool:
        return self._failures.get(key, 0) >= self._kick_threshold

    def clear(self) -> None:
        self._failures.clear()
        self._locked_until.clear()
