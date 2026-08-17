from __future__ import annotations

import asyncio
import fractions
import time

from typing import Any

import numpy as np
from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.sdp import candidate_from_sdp
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
        self._next_frame_time = time.monotonic()

    async def recv(self) -> VideoFrame:
        # Pace frames to TARGET_FPS by sleeping until the next frame time
        now = time.monotonic()
        time_to_sleep = self._next_frame_time - now
        if time_to_sleep > 0:
            await asyncio.sleep(time_to_sleep)

        frame = capture_frame(self._monitor_index)
        rgb = frame.data[:, :, :3][:, :, ::-1]  # BGRA -> RGB
        video_frame = VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")
        video_frame.pts = self._pts
        video_frame.time_base = VIDEO_TIME_BASE
        self._pts += _PTS_STEP

        # Schedule next frame to maintain TARGET_FPS
        self._next_frame_time += 1 / TARGET_FPS

        return video_frame


def parse_ice_candidate(candidate_init: dict[str, Any]) -> RTCIceCandidate | None:
    """
    Turn a browser `RTCIceCandidateInit` dict into an aiortc `RTCIceCandidate`.

    aiortc's `addIceCandidate()` wants a candidate object carrying `sdpMid` /
    `sdpMLineIndex`, while the viewer relays `RTCIceCandidate.toJSON()`:
    `{candidate, sdpMid, sdpMLineIndex, usernameFragment}`. Returns None for an
    empty candidate string, which browsers use as an end-of-candidates marker.
    """
    sdp = (candidate_init.get("candidate") or "").strip()
    if not sdp:
        return None
    if sdp.startswith("candidate:"):
        sdp = sdp[len("candidate:") :]

    candidate = candidate_from_sdp(sdp)
    candidate.sdpMid = candidate_init.get("sdpMid")
    candidate.sdpMLineIndex = candidate_init.get("sdpMLineIndex")
    return candidate


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

    async def add_ice_candidate(self, candidate_init: dict[str, Any]) -> None:
        candidate = parse_ice_candidate(candidate_init)
        if candidate is None:
            return
        await self._pc.addIceCandidate(candidate)

    async def close(self) -> None:
        await self._pc.close()
