import numpy as np
import pytest

from screentracker_host.capture import Frame
from screentracker_host.webrtc_peer import ScreenCaptureTrack


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
