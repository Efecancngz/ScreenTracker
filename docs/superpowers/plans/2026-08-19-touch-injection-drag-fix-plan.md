# Touch Injection Drag Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make real click-and-drag (file icons, window drags, text selection) work when driven remotely from the viewer, by routing the single-finger/left-button pointer path through Windows' Touch Injection API instead of `pynput` mouse simulation.

**Architecture:** A new Windows-only `TouchInjector` class (`touch_injector.py`) wraps `InitializeTouchInjection`/`InjectTouchInput` via ctypes, exposing `down(x, y)` / `move(x, y)` / `up(x, y)` in host pixel coordinates. `InputInjector` (`input_injector.py`) routes `pointer-down`/`pointer-move`/`pointer-up` messages with `button == "left"` through `TouchInjector` when available, tracking which button is currently held (`self._active_button`) so bare `pointer-move` messages — which don't carry a button field — route to the same sink the corresponding `pointer-down` used. Right-click, scroll, and keyboard are untouched; non-Windows hosts and hosts where touch injection fails to initialize keep using the existing `pynput` path unconditionally.

**Tech Stack:** Python 3.12, `ctypes` (stdlib, Win32 API access), `pynput` (existing dependency, unchanged), `pytest` + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-08-19-touch-injection-drag-fix-design.md`

## Global Constraints

- TDD: write/update the failing test first, then make it pass, for every code change in this plan.
- Test command: `python -m pytest -q` run from `host-app/`. Baseline before this plan: 67 passed, 0 failed. Every task must leave this suite fully green — no skips, no `xfail` (except the platform-guard skip described in Task 1, which is intentional and documented there).
- Scope: only `host-app/screentracker_host/touch_injector.py` (new), `host-app/screentracker_host/input_injector.py` (modified), and their test files change in this plan. Do not touch `viewer-app/`, `signaling-server/`, `launcher/`, or any capture-pipeline file from the earlier perf plan.
- No change to the DataChannel wire protocol or to any client-side (`viewer-app`) code — `pointer-down` / `pointer-move` / `pointer-up` / `wheel` / `key-down` / `key-up` message shapes are exactly as today.
- Right-click (`button == "right"`), scroll (`wheel`), and keyboard (`key-down`/`key-up`) behavior must be **byte-identical** to today — same `pynput` calls, same code paths. Only the `button == "left"` pointer path changes.
- `TouchInjector` construction failure (or running on a non-Windows platform) must **never** disable input entirely — it falls back to the pre-existing `pynput`-based left-button path (today's behavior, drag just won't work correctly, exactly as before this plan).
- Commit messages: no co-author trailer (repo convention — see `git log` in this repo).
- `TouchInjector` uses a fixed `pointerId=0` — only one contact is ever live at a time by this app's design (single-finger primary gesture), so no contact-ID management is needed.

---

## Task 1: `TouchInjector` — Windows Touch Injection API wrapper

**Files:**
- Create: `host-app/screentracker_host/touch_injector.py`
- Test: `host-app/tests/test_touch_injector.py`

**Interfaces:**
- Produces (for Task 2 to consume):
  - `class TouchInjector:`
    - `__init__(self) -> None` — raises `RuntimeError` if `InitializeTouchInjection` fails.
    - `down(self, x: int, y: int) -> None`
    - `move(self, x: int, y: int) -> None`
    - `up(self, x: int, y: int) -> None`
    - Each of `down`/`move`/`up` raises `RuntimeError` if the underlying `InjectTouchInput` call fails.
  - Module-level `user32 = ctypes.windll.user32` — Task 2's tests don't need this directly, but it's the patch target (`screentracker_host.touch_injector.user32`) any test in this module or importing it uses.

This module is Windows-only: `ctypes.windll` only exists on Windows, so importing this module on any other platform raises `AttributeError` at import time. That's intentional — Task 2 only imports it inside a `sys.platform == "win32"` guard, so it's never imported elsewhere. `test_touch_injector.py` itself must guard its own collection the same way (see Step 1) so the suite stays green on a hypothetical non-Windows run.

- [ ] **Step 1: Write the failing tests**

Create `host-app/tests/test_touch_injector.py`:

```python
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Touch Injection API is Windows-only"
)

from unittest.mock import patch

from screentracker_host.touch_injector import (
    POINTER_FLAG_DOWN,
    POINTER_FLAG_INCONTACT,
    POINTER_FLAG_INRANGE,
    POINTER_FLAG_UP,
    POINTER_FLAG_UPDATE,
    TOUCH_FEEDBACK_DEFAULT,
    TouchInjector,
)


@pytest.fixture
def mock_user32():
    with patch("screentracker_host.touch_injector.user32") as mock:
        mock.InitializeTouchInjection.return_value = True
        mock.InjectTouchInput.return_value = True
        yield mock


def test_init_calls_initialize_touch_injection_with_one_contact(mock_user32):
    TouchInjector()

    mock_user32.InitializeTouchInjection.assert_called_once_with(1, TOUCH_FEEDBACK_DEFAULT)


def test_init_raises_runtime_error_when_initialize_fails(mock_user32):
    mock_user32.InitializeTouchInjection.return_value = False

    with pytest.raises(RuntimeError, match="InitializeTouchInjection failed"):
        TouchInjector()


def test_down_injects_down_flags_at_the_given_pixel(mock_user32):
    injector = TouchInjector()

    injector.down(100, 200)

    count, contact_ptr = mock_user32.InjectTouchInput.call_args[0]
    contact = contact_ptr.contents
    assert count == 1
    assert contact.pointerInfo.pointerFlags == (
        POINTER_FLAG_DOWN | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
    )
    assert contact.pointerInfo.ptPixelLocation.x == 100
    assert contact.pointerInfo.ptPixelLocation.y == 200


def test_move_injects_update_flags_at_the_given_pixel(mock_user32):
    injector = TouchInjector()

    injector.move(50, 60)

    contact = mock_user32.InjectTouchInput.call_args[0][1].contents
    assert contact.pointerInfo.pointerFlags == (
        POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
    )
    assert contact.pointerInfo.ptPixelLocation.x == 50
    assert contact.pointerInfo.ptPixelLocation.y == 60


def test_up_injects_up_flags_at_the_given_pixel(mock_user32):
    injector = TouchInjector()

    injector.up(10, 20)

    contact = mock_user32.InjectTouchInput.call_args[0][1].contents
    assert contact.pointerInfo.pointerFlags == POINTER_FLAG_UP
    assert contact.pointerInfo.ptPixelLocation.x == 10
    assert contact.pointerInfo.ptPixelLocation.y == 20


def test_down_uses_pointer_id_zero(mock_user32):
    injector = TouchInjector()

    injector.down(1, 1)

    contact = mock_user32.InjectTouchInput.call_args[0][1].contents
    assert contact.pointerInfo.pointerId == 0


def test_down_uses_pointer_type_touch(mock_user32):
    from screentracker_host.touch_injector import PT_TOUCH

    injector = TouchInjector()

    injector.down(1, 1)

    contact = mock_user32.InjectTouchInput.call_args[0][1].contents
    assert contact.pointerInfo.pointerType == PT_TOUCH


def test_inject_raises_runtime_error_when_inject_touch_input_fails(mock_user32):
    mock_user32.InjectTouchInput.return_value = False
    injector = TouchInjector()

    with pytest.raises(RuntimeError, match="InjectTouchInput failed"):
        injector.down(1, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `host-app/`): `python -m pytest tests/test_touch_injector.py -v`
Expected: collection error / `ModuleNotFoundError: No module named 'screentracker_host.touch_injector'` (the module doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Create `host-app/screentracker_host/touch_injector.py`:

```python
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
```

Note: `_inject` passes `ctypes.pointer(contact)` (not `ctypes.byref(contact)`) — functionally equivalent for the real Win32 call, but `ctypes.pointer()` produces a full pointer object whose `.contents` can be read back, which is exactly what the tests above use to inspect what was sent. `byref()` produces a lighter-weight object that can't be introspected this way.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `host-app/`): `python -m pytest tests/test_touch_injector.py -v`
Expected: 8 passed (all tests from Step 1).

- [ ] **Step 5: Commit**

```bash
git add host-app/screentracker_host/touch_injector.py host-app/tests/test_touch_injector.py
git commit -m "$(cat <<'EOF'
Add Windows Touch Injection API wrapper

Windows Explorer's drag-and-drop (DoDragDrop) does not reliably
recognize synthetic mouse input (SetCursorPos/SendInput) as a genuine
drag, even though cursor position and button state both update
correctly -- confirmed via isolated testing. Touch-originated input
goes through Windows' native touch/pen stack instead, which
DoDragDrop does recognize.
EOF
)"
```

---

## Task 2: Route the left-button pointer path through `TouchInjector`

**Files:**
- Modify: `host-app/screentracker_host/input_injector.py`
- Test: `host-app/tests/test_input_injector.py`

**Depends on Task 1:** imports `TouchInjector` from `screentracker_host.touch_injector` (Windows-only, imported lazily inside a `sys.platform == "win32"` guard so this file stays importable on every platform).

**Interfaces:**
- Consumes: `TouchInjector` (Task 1) — `__init__() -> None` (raises `RuntimeError` on failure), `down(x: int, y: int) -> None`, `move(x: int, y: int) -> None`, `up(x: int, y: int) -> None`.
- Produces: `InputInjector`'s existing public surface (`__init__(screen_size)`, `handle_message(message: dict) -> None`) is unchanged — this task only changes internal behavior, not the class's interface. No other module in the codebase constructs `TouchInjector` directly; `InputInjector` owns that entirely.

**Goal recap:** today, `_dispatch()` sends every `pointer-down`/`pointer-move`/`pointer-up` through `pynput` unconditionally. After this task: `button == "left"` pointer events go through `TouchInjector` when one was successfully constructed (Windows, touch injection available); everything else — `button == "right"`, non-Windows, or touch injection unavailable — keeps using exactly the `pynput` calls it uses today. `pointer-move` messages carry no `button` field, so `InputInjector` tracks which button is currently held (`self._active_button`, set on `pointer-down`, cleared on `pointer-up`) to route them to the same sink the gesture's `pointer-down` used.

- [ ] **Step 1: Write the failing tests**

Replace `host-app/tests/test_input_injector.py`'s existing `injector` fixture and the tests that exercise `pointer-down`/`pointer-move`/`pointer-up` (the pure-function tests at the top of the file — `test_clamp_unit_*`, `test_normalize_to_pixels_*`, `test_wheel_delta_to_scroll_units_*`, `test_resolve_key_*` — are untouched, keep them exactly as they are). Replace everything from the `@pytest.fixture` def `injector` onward with:

```python
from unittest.mock import MagicMock, patch

import pytest

from screentracker_host.input_injector import InputInjector


@pytest.fixture
def injector():
    """Default fixture: TouchInjector constructs successfully, so
    left-button pointer events route through it. Use the
    `injector_no_touch` fixture below for the pynput-fallback cases."""
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller") as mock_keyboard_cls, \
         patch("screentracker_host.input_injector.sys.platform", "win32"), \
         patch("screentracker_host.touch_injector.user32") as mock_user32:
        mock_user32.InitializeTouchInjection.return_value = True
        mock_user32.InjectTouchInput.return_value = True
        mock_mouse = MagicMock()
        mock_keyboard = MagicMock()
        mock_mouse_cls.return_value = mock_mouse
        mock_keyboard_cls.return_value = mock_keyboard
        instance = InputInjector(screen_size=(1920, 1080))
        yield instance, mock_mouse, mock_keyboard, mock_user32


@pytest.fixture
def injector_no_touch():
    """Fixture for the pynput-fallback path: sys.platform isn't win32,
    so InputInjector never attempts to construct a TouchInjector at
    all, and every pointer path (left AND right) uses pynput -- this
    is also representative of "TouchInjector construction failed"."""
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller") as mock_keyboard_cls, \
         patch("screentracker_host.input_injector.sys.platform", "linux"):
        mock_mouse = MagicMock()
        mock_keyboard = MagicMock()
        mock_mouse_cls.return_value = mock_mouse
        mock_keyboard_cls.return_value = mock_keyboard
        instance = InputInjector(screen_size=(1920, 1080))
        yield instance, mock_mouse, mock_keyboard


def _touch_contact(mock_user32):
    """Reads back the POINTER_TOUCH_INFO most recently passed to the
    mocked InjectTouchInput -- same technique test_touch_injector.py
    uses."""
    return mock_user32.InjectTouchInput.call_args[0][1].contents


def test_left_pointer_down_goes_through_touch_injector(injector):
    from screentracker_host.touch_injector import (
        POINTER_FLAG_DOWN,
        POINTER_FLAG_INCONTACT,
        POINTER_FLAG_INRANGE,
    )

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    contact = _touch_contact(mock_user32)
    assert contact.pointerInfo.pointerFlags == (
        POINTER_FLAG_DOWN | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
    )
    assert contact.pointerInfo.ptPixelLocation.x == 960
    assert contact.pointerInfo.ptPixelLocation.y == 540
    mock_mouse.press.assert_not_called()


def test_left_pointer_move_goes_through_touch_injector_after_left_down(injector):
    from screentracker_host.touch_injector import (
        POINTER_FLAG_INCONTACT,
        POINTER_FLAG_INRANGE,
        POINTER_FLAG_UPDATE,
    )

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    instance.handle_message({"type": "pointer-move", "x": 0.1, "y": 0.9})

    contact = _touch_contact(mock_user32)
    assert contact.pointerInfo.pointerFlags == (
        POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
    )
    assert contact.pointerInfo.ptPixelLocation.x == 192
    assert contact.pointerInfo.ptPixelLocation.y == 972
    mock_mouse.press.assert_not_called()


def test_left_pointer_up_goes_through_touch_injector_and_clears_active_button(injector):
    from screentracker_host.touch_injector import POINTER_FLAG_UP

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    instance.handle_message({"type": "pointer-up", "x": 0.25, "y": 0.75, "button": "left"})

    contact = _touch_contact(mock_user32)
    assert contact.pointerInfo.pointerFlags == POINTER_FLAG_UP
    assert contact.pointerInfo.ptPixelLocation.x == 480
    assert contact.pointerInfo.ptPixelLocation.y == 810
    mock_mouse.release.assert_not_called()

    # A pointer-move after pointer-up (no active gesture) falls back to
    # the pynput path, proving _active_button was actually cleared.
    call_count_before = mock_user32.InjectTouchInput.call_count
    instance.handle_message({"type": "pointer-move", "x": 0.1, "y": 0.1})
    assert mock_user32.InjectTouchInput.call_count == call_count_before
    assert mock_mouse.position == (192, 108)


def test_right_pointer_down_still_uses_pynput_even_with_touch_injector_available(injector):
    from pynput.mouse import Button

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.0, "y": 0.0, "button": "right"})

    mock_mouse.press.assert_called_once_with(Button.right)
    assert mock_mouse.position == (0, 0)
    mock_user32.InjectTouchInput.assert_not_called()


def test_right_pointer_move_still_uses_pynput_after_right_down(injector):
    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.0, "y": 0.0, "button": "right"})
    instance.handle_message({"type": "pointer-move", "x": 0.5, "y": 0.5})

    assert mock_mouse.position == (960, 540)
    mock_user32.InjectTouchInput.assert_not_called()


def test_right_pointer_up_still_uses_pynput(injector):
    from pynput.mouse import Button

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.0, "y": 0.0, "button": "right"})
    instance.handle_message({"type": "pointer-up", "x": 0.25, "y": 0.75, "button": "right"})

    mock_mouse.release.assert_called_once_with(Button.right)
    assert mock_mouse.position == (480, 810)
    mock_user32.InjectTouchInput.assert_not_called()


def test_wheel_still_scrolls_via_pynput(injector):
    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "wheel", "deltaX": 0, "deltaY": 200})

    mock_mouse.scroll.assert_called_once_with(0, -2)
    mock_user32.InjectTouchInput.assert_not_called()


def test_key_down_still_presses_via_pynput(injector):
    from pynput.keyboard import Key

    instance, _, mock_keyboard, mock_user32 = injector

    instance.handle_message({"type": "key-down", "key": "Enter"})

    mock_keyboard.press.assert_called_once_with(Key.enter)
    mock_user32.InjectTouchInput.assert_not_called()


def test_key_up_still_releases_via_pynput(injector):
    instance, _, mock_keyboard, mock_user32 = injector

    instance.handle_message({"type": "key-up", "key": "a"})

    mock_keyboard.release.assert_called_once_with("a")
    mock_user32.InjectTouchInput.assert_not_called()


def test_unknown_message_type_is_ignored(injector):
    instance, mock_mouse, mock_keyboard, mock_user32 = injector

    instance.handle_message({"type": "not-a-real-type"})

    mock_mouse.press.assert_not_called()
    mock_keyboard.press.assert_not_called()
    mock_user32.InjectTouchInput.assert_not_called()


def test_exception_during_dispatch_is_caught_and_warned_once(injector, capsys):
    instance, mock_mouse, _, _ = injector
    mock_mouse.press.side_effect = RuntimeError("boom")

    # Use the right button so this exercises the pynput press() path
    # (left goes through TouchInjector, which doesn't call mock_mouse.press).
    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "right"})
    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "right"})

    captured = capsys.readouterr()
    assert captured.out.count("Accessibility") == 1


def test_left_pointer_down_falls_back_to_pynput_when_touch_injector_construction_fails():
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller"), \
         patch("screentracker_host.input_injector.sys.platform", "win32"), \
         patch("screentracker_host.touch_injector.user32") as mock_user32:
        mock_user32.InitializeTouchInjection.return_value = False  # construction fails
        mock_mouse = MagicMock()
        mock_mouse_cls.return_value = mock_mouse

        instance = InputInjector(screen_size=(1920, 1080))
        instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

        assert mock_mouse.position == (960, 540)
        mock_mouse.press.assert_called_once()
        mock_user32.InjectTouchInput.assert_not_called()


def test_left_pointer_down_uses_pynput_on_non_windows(injector_no_touch):
    instance, mock_mouse, _ = injector_no_touch

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    assert mock_mouse.position == (960, 540)
    mock_mouse.press.assert_called_once()


def test_host_peer_connection_survives_touch_injector_construction_failure_message():
    """The fallback message is printed (not silently swallowed) so a
    developer reading host app logs can see why drag-and-drop won't
    work correctly on this host."""
    with patch("screentracker_host.input_injector.mouse.Controller"), \
         patch("screentracker_host.input_injector.keyboard.Controller"), \
         patch("screentracker_host.input_injector.sys.platform", "win32"), \
         patch("screentracker_host.touch_injector.user32") as mock_user32, \
         patch("builtins.print") as mock_print:
        mock_user32.InitializeTouchInjection.return_value = False

        InputInjector(screen_size=(1920, 1080))

        assert any(
            "Touch injection unavailable" in str(call.args[0])
            for call in mock_print.call_args_list
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `host-app/`): `python -m pytest tests/test_input_injector.py -v`
Expected: FAIL — most new tests fail with `AttributeError`/`ImportError` (no `touch_injector` import wiring in `InputInjector` yet) or assertion failures, since `_dispatch()` doesn't route anything through `TouchInjector` yet.

- [ ] **Step 3: Write the implementation**

Replace `host-app/screentracker_host/input_injector.py` in full with:

```python
import sys

from pynput.keyboard import Key
from pynput import keyboard, mouse
from pynput.mouse import Button

WHEEL_SCROLL_DIVISOR = 100.0

# Browser KeyboardEvent.key values for named keys -> pynput's Key enum.
# Anything not in this map is treated as a literal single character
# (pynput accepts plain chars directly, so "a"/"A"/"1" pass through as-is).
KEY_MAP: dict[str, Key] = {
    "Enter": Key.enter,
    "Backspace": Key.backspace,
    "Tab": Key.tab,
    "Escape": Key.esc,
    "Shift": Key.shift,
    "Control": Key.ctrl,
    "Alt": Key.alt,
    "Meta": Key.cmd,
    "ArrowUp": Key.up,
    "ArrowDown": Key.down,
    "ArrowLeft": Key.left,
    "ArrowRight": Key.right,
    "Delete": Key.delete,
    "CapsLock": Key.caps_lock,
    "Home": Key.home,
    "End": Key.end,
    "PageUp": Key.page_up,
    "PageDown": Key.page_down,
    " ": Key.space,
}


def clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_to_pixels(x: float, y: float, screen_width: int, screen_height: int) -> tuple[int, int]:
    px = round(clamp_unit(x) * screen_width)
    py = round(clamp_unit(y) * screen_height)
    return px, py


def wheel_delta_to_scroll_units(delta_x: float, delta_y: float) -> tuple[int, int]:
    """Browser wheel deltas are ~100 per notch; pynput's scroll() takes small
    step counts. Y is inverted: pynput's positive dy scrolls the view up,
    while a positive browser deltaY means the user scrolled down."""
    dx = round(delta_x / WHEEL_SCROLL_DIVISOR)
    dy = round(-delta_y / WHEEL_SCROLL_DIVISOR)
    return dx, dy


def resolve_key(key: str) -> Key | str:
    return KEY_MAP.get(key, key)


_BUTTON_MAP: dict[str, Button] = {"left": Button.left, "right": Button.right}


class InputInjector:
    """Translates DataChannel input messages into OS-level events.

    Left-button pointer events (drag-and-drop, clicks) go through
    Windows' Touch Injection API when available -- pynput's
    SetCursorPos/SendInput-based mouse simulation moves the cursor
    correctly but isn't recognized by Windows Explorer's drag-and-drop
    (DoDragDrop), confirmed via isolated testing (see
    docs/superpowers/specs/2026-08-19-touch-injection-drag-fix-design.md).
    Right-click, scroll, and keyboard stay on pynput -- they're
    synthetic gestures the client already translates into distinct
    actions, not literal touch replication.

    Never raises: a bad message or a permissions error (e.g. missing
    macOS Accessibility access) is caught and logged once, not left to
    crash the host app's main loop.
    """

    def __init__(self, screen_size: tuple[int, int]) -> None:
        self._screen_width, self._screen_height = screen_size
        self._mouse = mouse.Controller()
        self._keyboard = keyboard.Controller()
        self._warned = False
        # Which button (if any) is currently "held" from the last
        # pointer-down that hasn't yet seen its matching pointer-up.
        # pointer-move messages carry no button field, so this is how
        # they're routed to the same sink pointer-down used.
        self._active_button: str | None = None
        self._touch_injector = self._build_touch_injector()

    def _build_touch_injector(self):
        if sys.platform != "win32":
            return None
        from screentracker_host.touch_injector import TouchInjector

        try:
            return TouchInjector()
        except RuntimeError as exc:
            print(
                f"Touch injection unavailable ({exc}); drag-and-drop may not "
                "work correctly, but clicks and other input will still work."
            )
            return None

    def handle_message(self, message: dict) -> None:
        try:
            self._dispatch(message)
        except Exception:
            if not self._warned:
                print(
                    "Input control failed to inject an event. On macOS this usually "
                    "means permission hasn't been granted — see "
                    "System Settings > Privacy & Security > Accessibility."
                )
                self._warned = True

    def _dispatch(self, message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == "pointer-down":
            button = message.get("button", "left")
            pixels = normalize_to_pixels(
                message["x"], message["y"], self._screen_width, self._screen_height
            )
            self._active_button = button
            if button == "left" and self._touch_injector is not None:
                self._touch_injector.down(*pixels)
            else:
                self._mouse.position = pixels
                self._mouse.press(_BUTTON_MAP[button])
        elif msg_type == "pointer-move":
            pixels = normalize_to_pixels(
                message["x"], message["y"], self._screen_width, self._screen_height
            )
            if self._active_button == "left" and self._touch_injector is not None:
                self._touch_injector.move(*pixels)
            else:
                self._mouse.position = pixels
        elif msg_type == "pointer-up":
            button = message.get("button", "left")
            pixels = normalize_to_pixels(
                message["x"], message["y"], self._screen_width, self._screen_height
            )
            if button == "left" and self._touch_injector is not None:
                self._touch_injector.up(*pixels)
            else:
                self._mouse.position = pixels
                self._mouse.release(_BUTTON_MAP[button])
            self._active_button = None
        elif msg_type == "wheel":
            dx, dy = wheel_delta_to_scroll_units(message.get("deltaX", 0), message.get("deltaY", 0))
            self._mouse.scroll(dx, dy)
        elif msg_type == "key-down":
            self._keyboard.press(resolve_key(message["key"]))
        elif msg_type == "key-up":
            self._keyboard.release(resolve_key(message["key"]))
```

Note what changed from before: the `_move()` helper (`self._mouse.position = normalize_to_pixels(x, y, ...)`) is gone — `pixels` is now computed once per branch and used directly, since the touch-injector branch needs the same pixel tuple `TouchInjector` expects (`int, int`), not the fractional `(x, y)` `_move()` took. No test referenced `_move()` directly (all tests go through `handle_message()`), so removing it doesn't break anything.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `host-app/`): `python -m pytest tests/test_input_injector.py -v`
Expected: all tests pass (the file's untouched pure-function tests plus every test from Step 1).

Then run the full suite: `python -m pytest -q`
Expected: all tests pass, 0 failed (67 baseline + Task 1's 8 new + Task 2's net-new/updated tests).

- [ ] **Step 5: Commit**

```bash
git add host-app/screentracker_host/input_injector.py host-app/tests/test_input_injector.py
git commit -m "$(cat <<'EOF'
Route left-button pointer path through Touch Injection

pointer-down/move/up with button=left now go through TouchInjector
when available (Windows), fixing real drag-and-drop -- pynput's mouse
simulation moved the cursor correctly but Explorer's DoDragDrop never
recognized it as a genuine drag. Right-click, scroll, and keyboard are
unchanged; non-Windows hosts and hosts where touch injection fails to
initialize keep using the pre-existing pynput path.
EOF
)"
```

---

## Manual verification (after both tasks, before finishing)

This bug was only ever caught by real on-device testing — the automated
suite mocks the Win32 boundary entirely, so it can't prove Explorer
actually accepts the injected touch as a drag. Once both tasks are
complete and the full suite is green, re-run the exact real-world
reproduction that originally surfaced this bug: from the phone viewer,
press-and-hold a real file icon on the host's physical screen and drag it
to a new location. It must actually pick up and move/drop, not just move
the cursor. Also spot-check that right-click (two-finger hold) and
two-finger scroll still work exactly as before — this plan's Global
Constraints require those paths to be byte-identical to pre-change
behavior.

Routing left-button pointer events through touch injection means the host
OS now interprets that input as genuine touch, which brings Windows' own
touch-gesture recognition into play in ways mouse simulation never
triggered. The final whole-branch review flagged this as a real behavioral
risk the automated suite cannot see — check all of these on-device too:

- **Press-and-hold without moving** (start a drag, hold still ~1s before
  moving): does Windows' native press-and-hold-for-context-menu gesture
  fire a right-click menu instead of starting the drag? The single-finger
  contract (hold = button stays down, no separate "hold" gesture) may not
  survive going through real touch semantics.
- **Hold perfectly still for 2+ seconds mid-drag** (down, move a little,
  then stop sending moves entirely for 2s, then resume): the client only
  emits `pointer-move` on actual finger movement, so a stationary hold
  sends no messages at all. If Windows drops an injected touch contact
  after a period of inactivity, the drag could die silently. If this
  fails, the fix is a periodic keep-alive `move()` call at the last known
  position while the button is held with no incoming messages.
- **Drag to the extreme edge of the screen** (all the way to x=0 or the
  right/bottom edge) and release there, then try a fresh left-click
  afterward: confirm the initial drag/drop still works at the edge and
  that left-click keeps working afterward (not stuck from an edge-clamped
  coordinate the touch stack rejected).
- **Text selection** in a document or browser (drag across text): confirm
  it selects text rather than panning the view — panning-instead-of-selecting
  is a plausible side effect of real touch semantics replacing mouse
  semantics, and text selection is one of this plan's stated goals.
- **Visible touch-feedback circles**: check whether Windows' touch
  indicator rings appear on the host's physical screen during a drag, and
  whether they show up in the video the viewer sees (`TouchInjector` uses
  `TOUCH_FEEDBACK_DEFAULT`; if the rings are visually distracting in the
  stream, switching to `TOUCH_FEEDBACK_NONE` is a one-constant fix, not
  in scope for this plan unless the on-device check shows it's a real
  problem).
