from dataclasses import dataclass

import cv2
import mss
import numpy as np

MAX_CAPTURE_DIM = 1280


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    data: np.ndarray  # RGB, shape (height, width, 3)


class ScreenCapturer:
    """Reusable screen capturer. Keeps a single mss context open across
    repeated captures (mss re-opens GDI/DXGI resources on every fresh
    `mss.mss()` call, which is wasteful at video frame rates), converts
    BGRA->RGB in one pass, and downscales anything above `max_dim` on its
    longest side so a 4K/1440p host doesn't force full-resolution software
    video encoding a phone-sized viewer can't use anyway."""

    def __init__(self, monitor_index: int = 1, max_dim: int = MAX_CAPTURE_DIM) -> None:
        self._sct = mss.mss()
        self._monitor_index = monitor_index
        self._max_dim = max_dim

    def capture(self) -> Frame:
        monitor = self._sct.monitors[self._monitor_index]
        raw = self._sct.grab(monitor)
        bgra = np.array(raw)
        rgb = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGB)
        rgb = _downscale_if_needed(rgb, self._max_dim)
        height, width = rgb.shape[:2]
        return Frame(width=width, height=height, data=np.ascontiguousarray(rgb))

    def close(self) -> None:
        self._sct.close()


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
