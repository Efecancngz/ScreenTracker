"""Windows SendInput-based mouse injection.

Touch Injection was used previously in the (mistaken) belief that
Explorer's drag-and-drop (OLE DoDragDrop) doesn't recognize synthetic
mouse input. That belief traced back to pynput's `mouse.position`
setter, which calls SetCursorPos -- it moves the cursor but generates
no input event at all, so of course DoDragDrop never saw it. A real
mouse event stream via SendInput was confirmed, via an automated,
filesystem-verified test (drag a real file onto a real folder in
Explorer, backed by Microsoft UI Automation to find the exact on-screen
target -- no guessed coordinates), to drag files correctly: every
open-source remote-desktop project (RustDesk, Sunshine, the VNC family)
uses SendInput for exactly this reason, and none of them resort to
touch injection.

Unlike Touch Injection, SendInput has no persistent "contact" that can
go stale -- so there is no keepalive timer to manage here.
"""

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
INPUT_MOUSE = 0

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _to_absolute(x: int, y: int) -> tuple[int, int]:
    """SendInput's MOUSEEVENTF_ABSOLUTE coordinates are 0..65535 across
    the whole virtual desktop (which may span multiple monitors with a
    non-zero origin), not raw pixels on the primary monitor."""
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return (
        round((x - vx) * 65535 / (vw - 1)),
        round((y - vy) * 65535 / (vh - 1)),
    )


def _send(flags: int, dx: int = 0, dy: int = 0) -> None:
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(dx, dy, 0, flags, 0, None)
    sent = user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        err = ctypes.get_last_error()
        raise RuntimeError(f"SendInput failed, GetLastError={err}")


class MouseInjector:
    """Injects real mouse move/button events via SendInput."""

    def down(self, x: int, y: int) -> None:
        self.move(x, y)
        _send(MOUSEEVENTF_LEFTDOWN)

    def move(self, x: int, y: int) -> None:
        ax, ay = _to_absolute(x, y)
        _send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, ax, ay)

    def up(self, x: int, y: int) -> None:
        self.move(x, y)
        _send(MOUSEEVENTF_LEFTUP)
