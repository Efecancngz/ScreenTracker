from __future__ import annotations

import fractions

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

from screentracker_host.capture import capture_frame

VIDEO_TIME_BASE = fractions.Fraction(1, 90000)
TARGET_FPS = 15
_PTS_STEP = int(VIDEO_TIME_BASE.denominator / TARGET_FPS)


class ScreenCaptureTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, monitor_index: int = 1) -> None:
        super().__init__()
        self._monitor_index = monitor_index
        self._pts = 0

    async def recv(self) -> VideoFrame:
        frame = capture_frame(self._monitor_index)
        rgb = frame.data[:, :, :3][:, :, ::-1]  # BGRA -> RGB
        video_frame = VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
        video_frame.pts = self._pts
        video_frame.time_base = VIDEO_TIME_BASE
        self._pts += _PTS_STEP
        return video_frame


class HostPeerConnection:
    def __init__(self) -> None:
        self._pc = RTCPeerConnection()
        self._pc.addTrack(ScreenCaptureTrack())

    async def create_offer(self) -> RTCSessionDescription:
        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)
        return self._pc.localDescription

    async def set_remote_answer(self, sdp: str) -> None:
        await self._pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    async def add_ice_candidate(self, candidate) -> None:
        await self._pc.addIceCandidate(candidate)

    async def close(self) -> None:
        await self._pc.close()
