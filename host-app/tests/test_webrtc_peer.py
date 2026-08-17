import numpy as np
import pytest

from screentracker_host.capture import Frame
from screentracker_host.webrtc_peer import ScreenCaptureTrack, TARGET_FPS


@pytest.mark.asyncio
async def test_recv_returns_video_frame_matching_capture_size(monkeypatch):
    fake_frame = Frame(width=4, height=2, data=np.zeros((2, 4, 4), dtype=np.uint8))
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.capture_frame", lambda monitor_index: fake_frame
    )

    track = ScreenCaptureTrack()
    video_frame = await track.recv()

    assert video_frame.width == 4
    assert video_frame.height == 2


@pytest.mark.asyncio
async def test_recv_paces_frames_to_target_fps(monkeypatch):
    """Verify that recv() sleeps to maintain TARGET_FPS frame pacing."""
    fake_frame = Frame(width=4, height=2, data=np.zeros((2, 4, 4), dtype=np.uint8))
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.capture_frame", lambda monitor_index: fake_frame
    )

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
