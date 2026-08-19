"""Windows Touch Injection API wrapper.

Windows Explorer's drag-and-drop (OLE DoDragDrop) does not reliably
recognize synthetic MOUSE input (SetCursorPos/SendInput) as a genuine
drag gesture, even though the same calls correctly update cursor
position and button state at the Win32 API level -- confirmed via
isolated testing on a real Windows host. See
docs/superpowers/specs/2026-08-19-touch-injection-drag-fix-design.md
for the full investigation.

Touch-originated input goes through Windows' native touch/pen input
stack, which DoDragDrop and the rest of the shell recognize as
first-class input. This module simulates a single persistent touch
contact (pointerId 0) via InitializeTouchInjection + InjectTouchInput.
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

PT_TOUCH = 2

POINTER_FLAG_DOWN = 0x00010000
POINTER_FLAG_UPDATE = 0x00020000
POINTER_FLAG_UP = 0x00040000
POINTER_FLAG_INRANGE = 0x00000002
POINTER_FLAG_INCONTACT = 0x00000004

TOUCH_MASK_CONTACTAREA = 0x00000001

TOUCH_FEEDBACK_DEFAULT = 0x1

# Some Windows versions reject a zero-size contact area, so every
# injected contact carries a small rect centered on the point.
_CONTACT_HALF_WIDTH = 5


class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", ctypes.c_uint32),
        ("pointerId", ctypes.c_uint32),
        ("frameId", ctypes.c_uint32),
        ("pointerFlags", ctypes.c_uint32),
        ("sourceDevice", wintypes.HANDLE),
        ("hwndTarget", wintypes.HWND),
        ("ptPixelLocation", wintypes.POINT),
        ("ptHimetricLocation", wintypes.POINT),
        ("ptPixelLocationRaw", wintypes.POINT),
        ("ptHimetricLocationRaw", wintypes.POINT),
        ("dwTime", wintypes.DWORD),
        ("historyCount", ctypes.c_uint32),
        ("InputData", ctypes.c_int32),
        ("dwKeyStates", wintypes.DWORD),
        ("PerformanceCount", ctypes.c_uint64),
        ("ButtonChangeType", ctypes.c_int),
    ]


class POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("touchFlags", ctypes.c_uint32),
        ("touchMask", ctypes.c_uint32),
        ("rcContact", wintypes.RECT),
        ("rcContactRaw", wintypes.RECT),
        ("orientation", ctypes.c_uint32),
        ("pressure", ctypes.c_uint32),
    ]


def _make_contact(x: int, y: int, flags: int) -> POINTER_TOUCH_INFO:
    info = POINTER_TOUCH_INFO()
    ctypes.memset(ctypes.byref(info), 0, ctypes.sizeof(info))
    info.pointerInfo.pointerType = PT_TOUCH
    info.pointerInfo.pointerId = 0
    info.pointerInfo.pointerFlags = flags
    info.pointerInfo.ptPixelLocation.x = x
    info.pointerInfo.ptPixelLocation.y = y
    info.touchMask = TOUCH_MASK_CONTACTAREA
    info.rcContact.left = x - _CONTACT_HALF_WIDTH
    info.rcContact.right = x + _CONTACT_HALF_WIDTH
    info.rcContact.top = y - _CONTACT_HALF_WIDTH
    info.rcContact.bottom = y + _CONTACT_HALF_WIDTH
    return info


class TouchInjector:
    """Injects a single persistent touch contact (pointerId 0)."""

    def __init__(self) -> None:
        if not user32.InitializeTouchInjection(1, TOUCH_FEEDBACK_DEFAULT):
            err = ctypes.get_last_error()
            raise RuntimeError(f"InitializeTouchInjection failed, GetLastError={err}")

    def down(self, x: int, y: int) -> None:
        self._inject(x, y, POINTER_FLAG_DOWN | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT)

    def move(self, x: int, y: int) -> None:
        self._inject(x, y, POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT)

    def up(self, x: int, y: int) -> None:
        self._inject(x, y, POINTER_FLAG_UP)

    def _inject(self, x: int, y: int, flags: int) -> None:
        contact = _make_contact(x, y, flags)
        if not user32.InjectTouchInput(1, ctypes.pointer(contact)):
            err = ctypes.get_last_error()
            raise RuntimeError(f"InjectTouchInput failed, GetLastError={err}")
