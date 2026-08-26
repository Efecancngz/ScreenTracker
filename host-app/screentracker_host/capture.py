import sys
from dataclasses import dataclass

import cv2
import mss
import numpy as np

try:
    import dxcam
except ImportError:
    # dxcam wraps DXGI Desktop Duplication, a Windows-only API -- it isn't
    # installable on macOS/Linux. Import failure there is expected; those
    # platforms fall back to _MssBackend, which never references this name.
    dxcam = None

MAX_CAPTURE_DIM = 1280


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    data: np.ndarray  # RGB, shape (height, width, 3)


class _MssBackend:
    """GDI/BitBlt capture via mss. Works on Windows, macOS, and Linux."""

    def __init__(self) -> None:
        self._sct = mss.mss()

    def grab(self, monitor_index: int) -> np.ndarray:
        monitor = self._sct.monitors[monitor_index]
        raw = self._sct.grab(monitor)
        bgra = np.array(raw)
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGB)

    def close(self) -> None:
        self._sct.close()


class _DxcamBackend:
    """DXGI Desktop Duplication capture via dxcam. Windows-only.

    Unlike GDI's BitBlt, Desktop Duplication reads DWM's composited
    output directly on the GPU instead of taking a lock on the shared
    desktop device context -- so it doesn't hang when another window
    (observed with the WinUI3 Task Manager) is mid-composite on that
    same DC. That contention was the root cause of ScreenTracker
    freezing whenever Task Manager was open.

    dxcam has no public API for a monitor's absolute desktop position
    (left/top), so this backend only ever produces pixel data --
    `list_monitors()`/`get_monitor_size()` stay on mss, which does
    expose that geometry and is called far too rarely for BitBlt
    contention to matter there.
    """

    def __init__(self) -> None:
        self._camera = None
        self._output_idx: int | None = None

    def grab(self, monitor_index: int) -> np.ndarray:
        # monitor_index is mss-style 1-based; dxcam's output_idx is 0-based.
        output_idx = monitor_index - 1
        if self._camera is None or output_idx != self._output_idx:
            if self._camera is not None:
                self._camera.release()
            # device_idx=0: the primary GPU. Multi-GPU rigs where the
            # target monitor is driven by a second adapter aren't
            # supported -- out of scope for now.
            self._camera = dxcam.create(device_idx=0, output_idx=output_idx, output_color="RGB")
            self._output_idx = output_idx
        return self._camera.grab(new_frame_only=False)

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()


class ScreenCapturer:
    """Reusable screen capturer. Keeps a single capture backend open across
    repeated captures (recreating the underlying GDI/DXGI resources on every
    call is wasteful at video frame rates), converts to RGB in one pass, and
    downscales anything above `max_dim` on its longest side so a 4K/1440p
    host doesn't force full-resolution software video encoding a
    phone-sized viewer can't use anyway."""

    def __init__(
        self,
        monitor_index: int = 1,
        max_dim: int = MAX_CAPTURE_DIM,
        backend_cls: type | None = None,
    ) -> None:
        # The backend keeps its capture handles in threading.local()-like
        # state, populated only on the thread that creates it. ScreenCapturer
        # is constructed on the event loop thread but capture() runs on a
        # separate executor worker thread, so the backend must not be built
        # eagerly here -- only lazily, on whatever thread first calls
        # capture().
        self._backend = None
        self._backend_cls = backend_cls or (_DxcamBackend if sys.platform == "win32" else _MssBackend)
        self._monitor_index = monitor_index
        self._max_dim = max_dim

    def set_monitor(self, index: int) -> None:
        """Changes which monitor the next capture() grabs. A plain attribute
        write is safe without a lock here: the capture worker thread only
        ever reads self._monitor_index at the start of _grab(), and CPython
        attribute assignment is atomic, so a switch takes effect cleanly on
        the very next frame with no torn read possible."""
        self._monitor_index = index

    def capture(self) -> Frame:
        try:
            return self._grab()
        except Exception:
            # A capture backend's GDI/DXGI context can be invalidated by a
            # display sleep/wake, resolution change, or screen lock/unlock
            # while a capture loop is running -- every grab() then raises
            # against the now-stale context. Rebuild it once; a transient
            # invalidation heals itself, a persistent failure still raises
            # (to the caller) after this single retry.
            if self._backend is not None:
                self._backend.close()
            self._backend = None
            return self._grab()

    def _grab(self) -> Frame:
        if self._backend is None:
            self._backend = self._backend_cls()
        rgb = self._backend.grab(self._monitor_index)
        rgb = _downscale_if_needed(rgb, self._max_dim)
        height, width = rgb.shape[:2]
        return Frame(width=width, height=height, data=np.ascontiguousarray(rgb))

    def close(self) -> None:
        # Safe no-op if capture() was never called. Must run on the same
        # thread that lazily created self._backend -- see the thread-affinity
        # note in __init__.
        if self._backend is not None:
            self._backend.close()


def _downscale_if_needed(rgb: np.ndarray, max_dim: int) -> np.ndarray:
    height, width = rgb.shape[:2]
    longest = max(height, width)
    if longest <= max_dim:
        return rgb
    scale = max_dim / longest
    new_size = (round(width * scale), round(height * scale))  # cv2.resize wants (width, height)
    return cv2.resize(rgb, new_size, interpolation=cv2.INTER_AREA)


def get_monitor_size(monitor_index: int = 1) -> tuple[int, int]:
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        return monitor["width"], monitor["height"]


def list_monitors() -> list[dict]:
    """All physical monitors mss can see, excluding index 0 (mss's synthetic
    "all monitors combined" entry -- never a real capture target, and never
    what `monitor_index`'s default of 1 refers to).

    Always backed by mss, even on Windows where capture() itself uses
    dxcam: dxcam has no public API for a monitor's absolute desktop
    position (left/top), which callers need to map input coordinates to
    the right monitor. mss provides it, and this call is infrequent
    enough (once per connection, not per frame) that it never hits the
    BitBlt/DWM contention capture() was moved off of."""
    with mss.mss() as sct:
        return [
            {
                "index": i,
                "width": monitor["width"],
                "height": monitor["height"],
                "left": monitor["left"],
                "top": monitor["top"],
            }
            for i, monitor in enumerate(sct.monitors)
            if i != 0
        ]
