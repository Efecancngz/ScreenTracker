import pytest

from app.rate_limiter import RateLimiter, backoff_seconds_for_count


def test_backoff_is_zero_at_and_below_threshold():
    kwargs = dict(failure_threshold=3, base_backoff_seconds=2.0, max_backoff_seconds=60.0)
    assert backoff_seconds_for_count(1, **kwargs) == 0.0
    assert backoff_seconds_for_count(3, **kwargs) == 0.0


def test_backoff_doubles_past_threshold():
    kwargs = dict(failure_threshold=3, base_backoff_seconds=2.0, max_backoff_seconds=60.0)
    assert backoff_seconds_for_count(4, **kwargs) == 2.0
    assert backoff_seconds_for_count(5, **kwargs) == 4.0
    assert backoff_seconds_for_count(6, **kwargs) == 8.0


def test_backoff_caps_at_max():
    kwargs = dict(failure_threshold=3, base_backoff_seconds=2.0, max_backoff_seconds=60.0)
    assert backoff_seconds_for_count(20, **kwargs) == 60.0


def test_first_failures_up_to_threshold_do_not_lock():
    limiter = RateLimiter(failure_threshold=3)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert limiter.seconds_until_unlocked("1.2.3.4") == 0.0


def test_failure_past_threshold_locks_and_unlocks_after_backoff():
    current_time = [100.0]
    limiter = RateLimiter(failure_threshold=1, base_backoff_seconds=2.0, clock=lambda: current_time[0])
    limiter.record_failure("1.2.3.4")  # count=1, at threshold, no lock
    limiter.record_failure("1.2.3.4")  # count=2, past threshold, locks for 2s
    assert limiter.seconds_until_unlocked("1.2.3.4") == pytest.approx(2.0)
    current_time[0] += 2.0
    assert limiter.seconds_until_unlocked("1.2.3.4") == 0.0


def test_different_keys_are_tracked_independently():
    limiter = RateLimiter(failure_threshold=1, base_backoff_seconds=2.0)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert limiter.seconds_until_unlocked("1.2.3.4") > 0.0
    assert limiter.seconds_until_unlocked("5.6.7.8") == 0.0


def test_record_success_resets_failures_and_lock():
    limiter = RateLimiter(failure_threshold=1, base_backoff_seconds=2.0)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert limiter.seconds_until_unlocked("1.2.3.4") > 0.0

    limiter.record_success("1.2.3.4")

    assert limiter.seconds_until_unlocked("1.2.3.4") == 0.0
    assert not limiter.should_kick("1.2.3.4")


def test_should_kick_once_kick_threshold_reached():
    limiter = RateLimiter(failure_threshold=100, kick_threshold=3)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert not limiter.should_kick("1.2.3.4")

    limiter.record_failure("1.2.3.4")

    assert limiter.should_kick("1.2.3.4")


def test_stale_entries_are_evicted_after_the_retention_window():
    """_failures/_locked_until never shrank on their own -- a key that
    failed a few times (below the lock threshold) and was never seen
    again stayed in memory for the lifetime of the process. Over a
    long-running server this is unbounded growth. A key idle past the
    retention window, and not currently locked, should be forgotten."""
    current_time = [0.0]
    limiter = RateLimiter(
        failure_threshold=1,
        base_backoff_seconds=2.0,
        clock=lambda: current_time[0],
        retention_seconds=100.0,
    )
    limiter.record_failure("1.2.3.4")
    assert limiter.tracked_key_count() == 1

    current_time[0] += 200.0
    limiter.record_failure("5.6.7.8")  # sweep runs as a side effect

    assert limiter.tracked_key_count() == 1  # only "5.6.7.8" remains


def test_a_currently_locked_key_is_not_evicted_even_past_the_retention_window():
    current_time = [0.0]
    limiter = RateLimiter(
        failure_threshold=1,
        base_backoff_seconds=1000.0,  # long enough to still be locked below
        max_backoff_seconds=1000.0,
        clock=lambda: current_time[0],
        retention_seconds=100.0,
    )
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")  # now locked for 1000s

    current_time[0] += 200.0  # past retention_seconds, but still locked
    limiter.record_failure("5.6.7.8")

    assert limiter.tracked_key_count() == 2
    assert limiter.seconds_until_unlocked("1.2.3.4") > 0.0
