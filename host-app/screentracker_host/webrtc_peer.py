from __future__ import annotations

import asyncio
import fractions
import json
import os
import time

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from aiortc import (
    RTCConfiguration,
    RTCIceCandidate,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from aiortc.sdp import candidate_from_sdp
from av import VideoFrame

from screentracker_host.capture import ScreenCapturer, get_monitor_size, list_monitors
from screentracker_host.input_injector import InputInjector

# A public STUN server is enough for most NATs; TURN is the relay fallback for
# the symmetric-NAT cases where no direct path can be found.
STUN_SERVER_URL = "stun:stun.l.google.com:19302"

VIDEO_TIME_BASE = fractions.Fraction(1, 90000)
TARGET_FPS = 15
_PTS_STEP = int(VIDEO_TIME_BASE.denominator / TARGET_FPS)

# Any stall longer than this is treated as "we fell behind for a reason
# outside normal frame-to-frame variance" (system sleep/wake, a long GC
# pause, a CPU spike) rather than something to catch up on frame-by-frame.
MAX_PACING_DRIFT_SECONDS = 1.0


class ScreenCaptureTrack(VideoStreamTrack):
    kind = "video"

    def __init__(self, monitor_index: int = 1) -> None:
        super().__init__()
        self._capturer = ScreenCapturer(monitor_index)
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._pts = 0
        self._next_frame_time = time.monotonic()

    def set_monitor(self, index: int) -> None:
        self._capturer.set_monitor(index)

    async def recv(self) -> VideoFrame:
        now = time.monotonic()
        # Drift guard: a long stall (sleep/wake, CPU spike) leaves
        # _next_frame_time far behind wall-clock time; reset instead of
        # sending a burst of frames trying to catch up.
        if now - self._next_frame_time > MAX_PACING_DRIFT_SECONDS:
            self._next_frame_time = now

        time_to_sleep = self._next_frame_time - now
        if time_to_sleep > 0:
            await asyncio.sleep(time_to_sleep)

        loop = asyncio.get_event_loop()
        frame = await loop.run_in_executor(self._executor, self._capturer.capture)

        video_frame = VideoFrame.from_ndarray(frame.data, format="rgb24")
        video_frame.pts = self._pts
        video_frame.time_base = VIDEO_TIME_BASE
        self._pts += _PTS_STEP

        # Schedule next frame to maintain TARGET_FPS
        self._next_frame_time += 1 / TARGET_FPS

        return video_frame

    def stop(self) -> None:
        """Called by aiortc (RTCPeerConnection.close() stops sender tracks)
        to release capture resources. self._capturer.close() has the same
        thread-affinity constraint as capture() -- mss's GDI handles live in
        threading.local() on whichever thread lazily created them -- so it
        must run on the executor's worker thread, not here on the event
        loop thread. Dispatching close() through the executor is correct
        (and cheap) even if capture() was never called, since close() is a
        safe no-op when self._sct is still None.
        """
        super().stop()
        self._executor.submit(self._capturer.close).result()
        self._executor.shutdown(wait=True)


def build_ice_servers() -> list[RTCIceServer]:
    """STUN baseline plus the optional self-hosted TURN relay from the env."""
    ice_servers = [RTCIceServer(urls=STUN_SERVER_URL)]

    turn_url = os.environ.get("TURN_SERVER_URL")
    turn_username = os.environ.get("TURN_USERNAME")
    turn_password = os.environ.get("TURN_PASSWORD")
    if turn_url and turn_username and turn_password:
        ice_servers.append(
            RTCIceServer(urls=turn_url, username=turn_username, credential=turn_password)
        )

    return ice_servers


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
    def __init__(self, screen_size: tuple[int, int] | None = None) -> None:
        self._pc = RTCPeerConnection(RTCConfiguration(iceServers=build_ice_servers()))
        self._track = ScreenCaptureTrack()
        self._pc.addTrack(self._track)

        try:
            self._input_injector: InputInjector | None = InputInjector(
                screen_size or get_monitor_size()
            )
        except Exception as exc:
            # On a host without a usable display/permission bindings for
            # pynput (e.g. Xlib.error.DisplayNameError on a headless Linux
            # box), input control simply isn't available on this host —
            # that must not prevent video-only Phase 1 viewing from working.
            print(f"Input control unavailable: {exc}. Screen viewing will still work.")
            self._input_injector = None

        self._input_channel = self._pc.createDataChannel("input")

        @self._input_channel.on("open")
        def _on_input_channel_open() -> None:
            self._input_channel.send(
                json.dumps({"type": "monitor-list", "monitors": list_monitors()})
            )

        @self._input_channel.on("message")
        def _on_input_message(message: str) -> None:
            try:
                payload = json.loads(message)
            except (ValueError, TypeError):
                return
            if payload.get("type") == "select-monitor":
                self._handle_select_monitor(payload)
                return
            if self._input_injector is None:
                return
            self._input_injector.handle_message(payload)

    def _handle_select_monitor(self, payload: dict[str, Any]) -> None:
        index = payload.get("index")
        monitor = next((m for m in list_monitors() if m["index"] == index), None)
        if monitor is None:
            print(f"select-monitor: unknown monitor index {index!r}, ignoring")
            return
        self._track.set_monitor(index)
        if self._input_injector is not None:
            self._input_injector.update_screen(
                monitor["width"], monitor["height"], monitor["left"], monitor["top"]
            )

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
        if self._input_injector is not None:
            self._input_injector.close()
        await self._pc.close()
