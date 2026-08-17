from dataclasses import dataclass

import mss
import numpy as np


@dataclass(frozen=True)
class Frame:
    width: int
    height: int
    data: np.ndarray  # BGRA, shape (height, width, 4)


def capture_frame(monitor_index: int = 1) -> Frame:
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        raw = sct.grab(monitor)
        data = np.array(raw)
        return Frame(width=raw.width, height=raw.height, data=data)
