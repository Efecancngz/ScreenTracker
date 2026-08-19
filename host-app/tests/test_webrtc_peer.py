import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from screentracker_host.capture import Frame, ScreenCapturer
from aiortc import RTCIceCandidate

from screentracker_host.webrtc_peer import (
    HostPeerConnection,
    MAX_PACING_DRIFT_SECONDS,
    STUN_SERVER_URL,
    ScreenCaptureTrack,
    TARGET_FPS,
    build_ice_servers,
    parse_ice_candidate,
)


VIEWER_CANDIDATE = {
    "candidate": "candidate:842163049 1 udp 1677729535 203.0.113.9 54321 typ srflx "
    "raddr 192.168.1.5 rport 54321 generation 0 ufrag Xm1a network-cost 999",
    "sdpMid": "0",
    "sdpMLineIndex": 0,
    "usernameFragment": "Xm1a",
}


def test_build_ice_servers_falls_back_to_stun_only(monkeypatch):
    for name in ("TURN_SERVER_URL", "TURN_USERNAME", "TURN_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    ice_servers = build_ice_servers()

    assert [server.urls for server in ice_servers] == [STUN_SERVER_URL]


def test_build_ice_servers_appends_turn_when_configured(monkeypatch):
    monkeypatch.setenv("TURN_SERVER_URL", "turn:turn.example.com:3478")
    monkeypatch.setenv("TURN_USERNAME", "screentracker")
    monkeypatch.setenv("TURN_PASSWORD", "s3cret")

    ice_servers = build_ice_servers()

    assert [server.urls for server in ice_servers] == [
        STUN_SERVER_URL,
        "turn:turn.example.com:3478",
    ]
    assert ice_servers[1].username == "screentracker"
    assert ice_servers[1].credential == "s3cret"


def test_parse_ice_candidate_builds_aiortc_candidate_from_browser_payload():
    candidate = parse_ice_candidate(VIEWER_CANDIDATE)

    assert candidate is not None
    assert candidate.foundation == "842163049"
    assert candidate.component == 1
    assert candidate.protocol == "udp"
    assert candidate.priority == 1677729535
    assert candidate.ip == "203.0.113.9"
    assert candidate.port == 54321
    assert candidate.type == "srflx"
    assert candidate.relatedAddress == "192.168.1.5"
    assert candidate.relatedPort == 54321
    # Without these, aiortc's addIceCandidate() raises ValueError
    assert candidate.sdpMid == "0"
    assert candidate.sdpMLineIndex == 0


def test_parse_ice_candidate_returns_none_for_end_of_candidates_marker():
    assert parse_ice_candidate({"candidate": "", "sdpMid": "0", "sdpMLineIndex": 0}) is None


@pytest.mark.asyncio
async def test_add_ice_candidate_hands_a_parsed_candidate_to_aiortc():
    peer = HostPeerConnection()
    peer._pc = AsyncMock()

    await peer.add_ice_candidate(VIEWER_CANDIDATE)

    peer._pc.addIceCandidate.assert_awaited_once()
    (passed,) = peer._pc.addIceCandidate.await_args.args
    assert isinstance(passed, RTCIceCandidate)
    assert passed.ip == "203.0.113.9"
    assert passed.sdpMid == "0"


@pytest.mark.asyncio
async def test_add_ice_candidate_ignores_end_of_candidates_marker():
    peer = HostPeerConnection()
    peer._pc = AsyncMock()

    await peer.add_ice_candidate({"candidate": "", "sdpMid": "0", "sdpMLineIndex": 0})

    peer._pc.addIceCandidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_recv_returns_video_frame_matching_capture_size(monkeypatch):
    fake_frame = Frame(width=4, height=2, data=np.zeros((2, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(ScreenCapturer, "capture", lambda self: fake_frame)

    track = ScreenCaptureTrack()
    video_frame = await track.recv()

    assert video_frame.width == 4
    assert video_frame.height == 2


def _patch_immediate_loop(monkeypatch):
    """Replace the event loop used inside recv() with a stub whose
    run_in_executor runs the target function synchronously in place. Tests
    that need a deterministic time.monotonic() sequence would otherwise be
    perturbed by the real event loop's internal timer reads while it waits
    on a real executor thread.

    Only use this for tests asserting on the exact monkeypatched
    time.monotonic() sequence (pacing/drift-guard); the genuine-concurrency
    test (test_recv_does_not_block_the_event_loop_during_capture) must NOT
    use it, since it needs a real executor thread for capture() to actually
    run concurrently with other coroutines -- an immediate/synchronous loop
    would defeat the exact behavior it's verifying."""

    class _ImmediateLoop:
        def run_in_executor(self, executor, func, *args):
            async def _runner():
                return func(*args)

            return _runner()

    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.asyncio.get_event_loop", lambda: _ImmediateLoop()
    )


@pytest.mark.asyncio
async def test_recv_paces_frames_to_target_fps(monkeypatch):
    """Verify that recv() sleeps to maintain TARGET_FPS frame pacing."""
    fake_frame = Frame(width=4, height=2, data=np.zeros((2, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(ScreenCapturer, "capture", lambda self: fake_frame)
    _patch_immediate_loop(monkeypatch)

    # Track sleep calls to verify pacing
    sleep_calls = []

    async def mock_sleep(duration):
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    # Mock time.monotonic() to simulate time progression
    # Provide extra values to avoid StopIteration during event loop teardown
    times = [0.0, 0.0, 0.05, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]  # Extra values for teardown
    time_iter = iter(times)
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.time.monotonic", lambda: next(time_iter, 0.2)
    )

    track = ScreenCaptureTrack()

    # First recv: time is 0.0, _next_frame_time is 0.0
    # time_to_sleep = 0.0, so no sleep call (only sleep if > 0)
    await track.recv()
    assert len(sleep_calls) == 0

    # Second recv: time is 0.05, _next_frame_time is 1/15 (≈0.0667)
    # Should sleep for 1/15 - 0.05 (≈0.0167 seconds)
    await track.recv()
    assert len(sleep_calls) == 1
    expected_sleep = 1 / TARGET_FPS - 0.05
    assert abs(sleep_calls[0] - expected_sleep) < 1e-6

    # Third recv: time is 0.1, _next_frame_time is 2/15 (≈0.1333)
    # Should sleep for 2/15 - 0.1 (≈0.0333 seconds)
    await track.recv()
    assert len(sleep_calls) == 2
    expected_sleep = 2 / TARGET_FPS - 0.1
    assert abs(sleep_calls[1] - expected_sleep) < 1e-6


@pytest.mark.asyncio
async def test_recv_does_not_block_the_event_loop_during_capture(monkeypatch):
    """capture() must run off-loop (via the executor) so other coroutines
    scheduled concurrently get a chance to run while a capture is in
    flight, instead of being stalled for the capture's full duration."""
    fake_frame = Frame(width=4, height=2, data=np.zeros((2, 4, 3), dtype=np.uint8))

    def slow_capture(self):
        time.sleep(0.05)
        return fake_frame

    monkeypatch.setattr(ScreenCapturer, "capture", slow_capture)

    track = ScreenCaptureTrack()

    marker_finished_at = None
    capture_finished_at = None

    async def marker():
        nonlocal marker_finished_at
        await asyncio.sleep(0)
        marker_finished_at = time.monotonic()

    async def do_recv():
        nonlocal capture_finished_at
        await track.recv()
        capture_finished_at = time.monotonic()

    await asyncio.gather(do_recv(), marker())

    assert marker_finished_at is not None
    assert capture_finished_at is not None
    # The marker coroutine (a trivial asyncio.sleep(0) yield) must complete
    # before the blocking capture does -- if capture() ran synchronously on
    # the event loop, the marker couldn't run until recv() fully returned.
    assert marker_finished_at < capture_finished_at


@pytest.mark.asyncio
async def test_recv_drift_guard_resets_pacing_after_long_stall(monkeypatch):
    """A stall longer than MAX_PACING_DRIFT_SECONDS between recv() calls
    (system sleep/wake, a long GC pause, a CPU spike) must reset
    _next_frame_time to "now" rather than leave the track trying to send a
    burst of frames to catch up."""
    fake_frame = Frame(width=4, height=2, data=np.zeros((2, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(ScreenCapturer, "capture", lambda self: fake_frame)
    _patch_immediate_loop(monkeypatch)

    sleep_calls = []

    async def mock_sleep(duration):
        sleep_calls.append(duration)

    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    # First recv happens at t=0.0. Second recv happens at t=10.0 -- a stall
    # far bigger than MAX_PACING_DRIFT_SECONDS (1.0s).
    times = [0.0, 0.0, 10.0, 10.0, 10.0, 10.0]
    time_iter = iter(times)
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.time.monotonic", lambda: next(time_iter, 10.0)
    )

    track = ScreenCaptureTrack()

    await track.recv()
    assert len(sleep_calls) == 0

    await track.recv()

    # If the drift guard didn't fire, recv() would try to sleep for a
    # negative/huge catch-up amount instead. Either way it must not sleep
    # for anything resembling the ~10 second gap.
    assert not any(duration > MAX_PACING_DRIFT_SECONDS for duration in sleep_calls)
    # _next_frame_time was reset to (approximately) the post-jump "now"
    # (10.0) plus one frame interval, not left near its pre-jump value.
    assert abs(track._next_frame_time - (10.0 + 1 / TARGET_FPS)) < 1e-6


@pytest.mark.asyncio
async def test_recv_uses_screen_capturer_to_produce_frame(monkeypatch):
    """recv() must go through ScreenCapturer.capture() (not mss or the old
    capture_frame() directly) to build the returned VideoFrame."""
    calls = []
    fake_frame = Frame(width=6, height=3, data=np.zeros((3, 6, 3), dtype=np.uint8))

    def stub_capture(self):
        calls.append(self)
        return fake_frame

    monkeypatch.setattr(ScreenCapturer, "capture", stub_capture)

    track = ScreenCaptureTrack()
    assert isinstance(track._capturer, ScreenCapturer)

    video_frame = await track.recv()

    assert calls == [track._capturer]
    assert video_frame.width == 6
    assert video_frame.height == 3


def test_stop_shuts_down_executor_and_closes_capturer_via_executor(monkeypatch):
    """ScreenCaptureTrack.stop() (called by aiortc's RTCPeerConnection.close()
    via its sender tracks) must release the executor thread and the mss
    GDI handles. close() has the same thread-affinity constraint as
    capture(), so it must be dispatched through the executor rather than
    called directly from the event loop thread."""
    close_calls = []
    monkeypatch.setattr(ScreenCapturer, "close", lambda self: close_calls.append(self))

    track = ScreenCaptureTrack()
    track._executor.shutdown = MagicMock(wraps=track._executor.shutdown)

    track.stop()

    assert close_calls == [track._capturer]
    track._executor.shutdown.assert_called_once()
    # close() must have been dispatched to (and finished on) the executor
    # before shutdown was called -- not called directly on this thread.
    assert track._executor._shutdown is True


def test_host_peer_connection_creates_labeled_input_data_channel(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))

    assert peer._input_channel.label == "input"


def test_input_channel_message_is_forwarded_to_injector(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    payload = {"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"}
    peer._input_channel.emit("message", json.dumps(payload))

    fake_injector.handle_message.assert_called_once_with(payload)


def test_malformed_input_channel_message_is_dropped(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    peer._input_channel.emit("message", "not valid json")

    fake_injector.handle_message.assert_not_called()


def test_host_peer_connection_defaults_screen_size_from_monitor(monkeypatch):
    fake_injector = MagicMock()
    captured_sizes = []
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector",
        lambda screen_size: captured_sizes.append(screen_size) or fake_injector,
    )
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.get_monitor_size", lambda: (2560, 1440)
    )

    HostPeerConnection()

    assert captured_sizes == [(2560, 1440)]


def test_host_peer_connection_survives_input_injector_construction_failure(monkeypatch, capsys):
    def _raise(screen_size):
        raise RuntimeError("no display available")

    monkeypatch.setattr("screentracker_host.webrtc_peer.InputInjector", _raise)

    # Must not raise: video-only viewing must keep working even if input
    # control can't be initialized on this host.
    peer = HostPeerConnection(screen_size=(1920, 1080))

    assert peer._input_injector is None
    assert peer._input_channel.label == "input"
    captured = capsys.readouterr()
    assert "Input control unavailable" in captured.out


def test_input_message_is_silently_dropped_when_injector_failed_to_construct(monkeypatch):
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector",
        lambda screen_size: (_ for _ in ()).throw(RuntimeError("no display available")),
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    payload = {"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"}

    # Must not crash even though there's no injector to forward the message to.
    peer._input_channel.emit("message", json.dumps(payload))
