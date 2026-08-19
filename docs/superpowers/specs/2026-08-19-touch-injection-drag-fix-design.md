# Design: Fix real drag-and-drop via Windows Touch Injection API

## Context

ScreenTracker's host app injects remote input (from the phone viewer) into
the host OS via `pynput` (`host-app/screentracker_host/input_injector.py`).
During on-device testing of the recent capture-pipeline latency fix (a
separate, already-landed change), the user discovered that video latency
improved but **holding and dragging with one finger doesn't actually drag
anything** — e.g. a file icon in Windows Explorer cannot be picked up and
moved, even though the button-hold and pointer-position reporting are both
functioning.

### Root cause, established via systematic debugging

A sequence of isolated, single-variable experiments (each run directly on
the affected Windows host, outside the ScreenTracker app, to rule out
confounds) eliminated every other candidate explanation before landing on
the real one:

1. **The DataChannel/coordinate pipeline is correct.** Debug logging added
   to `InputInjector._move()` showed every `pointer-move` message arriving
   with the right fractional coordinates, converting to the right pixel
   values, and `pynput`'s `mouse.position = ...` (`SetCursorPos` under the
   hood) reliably moving the OS cursor to exactly that pixel — confirmed by
   reading `GetCursorPos()` back after every single call, across dozens of
   real drag gestures.
2. **API choice (`SetCursorPos` vs `SendInput`) is not the cause.** Routing
   movement through `SendInput` with `MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE`
   instead (matching the mechanism `pynput` already uses for button
   press/release) produced the identical symptom.
3. **The screen-capture pipeline (`CAPTUREBLT`-flagged `BitBlt`, run by
   `mss` at 15fps) is not the cause.** A standalone script running a tight
   `BitBlt` loop with the exact same flags as `mss`, alongside synthetic
   cursor movement, moved the cursor cleanly — capture activity doesn't
   interfere with cursor rendering.
4. **CPU/encoding load is not the cause.** Task Manager showed `python.exe`
   staying under 30% CPU during a broken drag attempt, and lowering
   `TARGET_FPS` from 15 to 2 (cutting encode load roughly 7x) did not fix
   the drag.
5. **The actual, confirmed root cause:** Windows Explorer's drag-and-drop
   (OLE `DoDragDrop`) does not reliably recognize **synthetic mouse input**
   (`SetCursorPos`/`SendInput`, both flagged `LLMHF_INJECTED` at the OS
   level) as a genuine drag gesture, even though the same input correctly
   updates cursor position and button state at the Win32 API level. This is
   a known, documented category of limitation for mouse-simulation-based
   automation — it's why real remote-control tools use lower-level
   injection for drag scenarios.
6. **Spike validation:** a throwaway script using Windows' **Touch
   Injection API** (`InitializeTouchInjection` + `InjectTouchInput`,
   simulating a real touch contact rather than a mouse) performed an actual
   file drag-and-drop successfully on the same machine where
   `SendInput`/`SetCursorPos` could not. Touch-originated input goes through
   Windows' native touch/pen input stack, which `DoDragDrop` and the rest of
   the shell recognize as first-class input — this is the confirmed fix
   direction.

This document designs the production fix: route the single-finger
(left-button-equivalent) pointer path through Touch Injection on Windows,
while leaving everything else (right-click, scroll, keyboard, and the
non-Windows fallback) unchanged.

## Goals

- Real click-and-drag with one finger (file icons, window drags, text
  selection, anything relying on OS-level drag recognition) works
  correctly on Windows hosts.
- No change in behavior for: right-click (two-finger hold/tap), scroll
  (two-finger pan), keyboard, or non-Windows hosts.
- Graceful degradation: if touch injection can't be initialized (older
  Windows, policy-restricted), input still works via the existing
  `pynput`-based mouse path — just without proper drag-and-drop, exactly
  today's behavior. Input control must never become fully unavailable
  because of this change (matches the existing pattern in
  `HostPeerConnection.__init__`, which already tolerates `InputInjector`
  construction failure so video-only viewing keeps working).

## Non-goals

- Right-click and scroll do **not** move to touch injection. They are
  synthetic gestures translated by the client (two-finger hold = right
  button, two-finger pan = wheel), not literal touch replication, so there's
  no reason to route them through a different Win32 mechanism, and doing so
  would risk the OS's own touch-gesture recognizer (edge swipes, pinch,
  native two-finger pan) firing unexpectedly.
- No change to the client (`viewer-app/src/hooks/useInputControl.ts`) or
  the DataChannel wire protocol. The existing `pointer-down` /
  `pointer-move` / `pointer-up` / `wheel` / `key-down` / `key-up` message
  shapes are unchanged.
- No macOS/Linux touch injection. This bug is Windows-specific
  (`DoDragDrop`); those platforms keep their current `pynput` mouse path
  entirely as-is.

## Architecture

### New component: `TouchInjector` (`host-app/screentracker_host/touch_injector.py`)

A small, Windows-only wrapper around the Win32 Touch Injection API,
providing three methods matching a single persistent touch contact's
lifecycle:

```python
class TouchInjector:
    def __init__(self) -> None:
        """Calls InitializeTouchInjection(1, TOUCH_FEEDBACK_DEFAULT) once.
        Raises RuntimeError if initialization fails (caller decides the
        fallback)."""

    def down(self, x: int, y: int) -> None: ...
    def move(self, x: int, y: int) -> None: ...
    def up(self, x: int, y: int) -> None: ...
```

Internally, each call builds a `POINTER_TOUCH_INFO` ctypes structure
(`pointerType=PT_TOUCH`, a fixed `pointerId=0` since only one contact is
ever live at a time by construction) with the appropriate `POINTER_FLAG_*`
combination (`DOWN|INRANGE|INCONTACT`, `UPDATE|INRANGE|INCONTACT`, `UP`)
and calls `InjectTouchInput(1, ...)`. `x`/`y` are host-screen pixel
coordinates — the same values `normalize_to_pixels()` already produces
today, so no coordinate-math changes are needed, only which sink receives
them.

This mirrors the existing `capture.py`/`webrtc_peer.py` pattern of a small
class wrapping a Win32/ctypes or third-party API surface, kept in its own
file with a single clear responsibility.

`InputInjector` (and therefore `TouchInjector`) is constructed fresh per
`HostPeerConnection`, i.e. on every reconnect (see `main.py`'s
`peer_connection_used` handling) — so `InitializeTouchInjection` may be
called more than once per process over a long-running session. Microsoft's
docs don't document this as unsafe, and there's no per-process handle to
leak (unlike `ScreenCapturer`'s `mss` context, which needed the
thread-affinity fix in the earlier capture-pipeline work) — each call
simply (re)establishes the calling process's eligibility to inject touch
input. No special handling beyond normal `RuntimeError` propagation on
failure is needed.

### `InputInjector` changes (`input_injector.py`)

Today, `_dispatch()` unconditionally routes `pointer-down` / `pointer-move`
/ `pointer-up` through `pynput` regardless of which button is involved.
That changes to:

- **Construction:** on `sys.platform == "win32"`, attempt to construct a
  `TouchInjector`. On success, store it; on failure (raises
  `RuntimeError`), log once (same style as the existing
  "Input control unavailable" / Accessibility-permission message) and
  proceed with `self._touch_injector = None`. On non-Windows platforms,
  `self._touch_injector` is `None` unconditionally — no attempt is made.
- **New state:** `self._active_button: str | None = None`, tracking which
  button (if any) is currently "held" from the last `pointer-down` that
  hasn't yet seen its matching `pointer-up`.
- **`pointer-down`:**
  - `button == "left"` and `self._touch_injector` is available → set
    `self._active_button = "left"`, call `self._touch_injector.down(px, py)`
    (`px, py` from the existing `normalize_to_pixels()`).
  - Otherwise (macOS/Linux, touch injection unavailable, or
    `button == "right"`) → existing behavior: `self._move(x, y)` +
    `self._mouse.press(...)`, and set `self._active_button` to the
    button used (so `pointer-move` routing below stays correct even for
    the pynput-fallback left-button case).
- **`pointer-move`:** routes on `self._active_button`:
  - `"left"` and a `TouchInjector` is active for this gesture →
    `self._touch_injector.move(px, py)`.
  - Anything else (including `self._active_button is None`, preserving
    today's behavior when a stray `pointer-move` arrives with no prior
    `pointer-down`) → existing `self._move(x, y)`.
- **`pointer-up`:** mirrors `pointer-down`'s routing based on
  `self._active_button`, then clears `self._active_button = None`.
- **`wheel`, `key-down`, `key-up`:** untouched.

This keeps `TouchInjector` itself simple and stateless-per-call (just a
thin API wrapper), while `InputInjector` owns the one piece of session
state needed to route correctly — consistent with "each unit has one clear
purpose."

## Data flow

```
Viewer touch (single finger)
  -> pointer-down {button:"left"} -> InputInjector routes to TouchInjector.down()
  -> pointer-move (repeated)      -> InputInjector routes to TouchInjector.move()
  -> pointer-up   {button:"left"} -> InputInjector routes to TouchInjector.up()
        (Windows recognizes this as a real touch drag -> DoDragDrop works)

Viewer two-finger hold (right-click)
  -> pointer-down {button:"right"} -> InputInjector: pynput mouse.press(Button.right)  [unchanged]
  -> pointer-move (repeated)       -> InputInjector: pynput mouse.position = ...       [unchanged]
  -> pointer-up   {button:"right"} -> InputInjector: pynput mouse.release(Button.right) [unchanged]
```

## Error handling

- `TouchInjector.__init__` failing (bad `InitializeTouchInjection` return)
  raises `RuntimeError` with the Win32 last-error code in the message;
  `InputInjector` catches it at construction time (mirroring the existing
  try/except around the whole `InputInjector` construction in
  `HostPeerConnection.__init__`) and continues with touch injection simply
  unavailable — falls back to the pre-existing `pynput` left-button path
  for the rest of the session. No crash, no video interruption.
- `InjectTouchInput` failing on an individual call (rare — e.g., transient
  OS state) is caught the same way `handle_message()` already catches any
  dispatch exception: logged once via the existing `_warned` mechanism,
  never crashes the host app's main loop.

## Testing

Following this repo's existing patterns (`unittest.mock.patch` /
`MagicMock` around the ctypes/Win32 boundary, same as
`test_capture.py`'s `mss.mss` mocking):

- `test_touch_injector.py` (new): mocks `ctypes.windll.user32` (or the
  specific bound functions) to verify `TouchInjector.__init__` calls
  `InitializeTouchInjection` with the right arguments and raises
  `RuntimeError` on failure; `down()`/`move()`/`up()` each call
  `InjectTouchInput` once with a `POINTER_TOUCH_INFO` carrying the correct
  `pointerFlags` combination and pixel coordinates.
- `test_input_injector.py` (updated): the existing `injector` fixture gains
  a mocked `TouchInjector` (patched at construction). New tests cover the
  routing matrix: left pointer-down/move/up go to the mocked
  `TouchInjector`; right pointer-down/move/up still go to the mocked
  `pynput` mouse exactly as today; a `TouchInjector` construction failure
  falls back to the pynput path for left-button gestures without raising.
  Existing tests (e.g. `test_pointer_down_moves_then_presses`,
  `test_pointer_move_only_repositions`) get updated for the new
  `self._active_button`-based routing but keep asserting the same
  externally-visible pynput behavior for the cases where pynput is still
  the sink (right button, and the no-active-touch-injector fallback path).

Manual on-device verification (this bug was only ever caught by real
hardware testing) stays part of finishing this change: after the automated
suite is green, the user re-runs the same real drag-and-drop test
(dragging a real file icon on the host's physical screen from the phone
viewer) that originally surfaced this bug.
