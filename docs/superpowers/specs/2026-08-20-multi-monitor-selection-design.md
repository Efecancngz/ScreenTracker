# Multi-monitor selection — design

**Date:** 2026-08-20
**Status:** Approved (brainstorming session), ready for implementation plan

## Problem

The host only ever captures `mss` monitor index 1 (hardcoded default
everywhere `ScreenCapturer`/`ScreenCaptureTrack`/`get_monitor_size` are
constructed). A user with two or more physical monitors can only ever see
and control the first one. Previous plans (`2026-08-18-input-control.md`,
its design doc) explicitly scoped multi-monitor out — this spec brings it
in.

## Goal

From the viewer (phone), the user can see how many monitors the host has
and switch which one is being streamed/controlled, live, without dropping
the WebRTC connection.

## Chosen approach: DataChannel-driven live swap, no renegotiation

Two approaches were considered:

1. **DataChannel swap (chosen).** The existing `"input"` RTCDataChannel
   (already open host→viewer and viewer→host) carries two new message
   types. Switching monitors changes which physical monitor
   `ScreenCapturer` grabs and where `InputInjector` maps normalized
   coordinates — the video track and peer connection are untouched.
2. **Track renegotiation.** Stop the old video track, add a new one, and
   run a fresh offer/answer exchange when the user switches monitors.

Approach 1 is chosen. This project's history (`67638c5`, `8435d5f`, the
whole 2026-08-20 negotiation saga) shows that every serious video bug so
far has come from the offer/answer/renegotiation layer. Avoiding a second
renegotiation trigger entirely removes that class of risk for a feature
that doesn't need it — swapping which monitor a track reads from is a
strictly cheaper operation than renegotiating.

## Data flow

1. Host builds a `HostPeerConnection`. Alongside the existing input
   handling, it calls `capture.list_monitors()` (new function) once the
   `"input"` DataChannel is open and sends
   `{"type": "monitor-list", "monitors": [{"index": 1, "width": ..., "height": ..., "left": ..., "top": ...}, ...]}`.
2. Viewer receives this on the same channel it already holds
   (`inputChannel` from `useWebRTCViewer`). If there's more than one
   monitor, it renders a small selector (button group) over the video.
3. User taps a monitor button. Viewer sends
   `{"type": "select-monitor", "index": N}` on the same channel.
4. Host's message handler recognizes `"select-monitor"` (alongside the
   existing pointer/keyboard/wheel types it already dispatches) and:
   - Calls `ScreenCaptureTrack.set_monitor(index)`, which updates the
     underlying `ScreenCapturer`'s `monitor_index` (a plain attribute
     write, read by the capture worker thread on its next `_grab()` —
     safe without a lock, same reasoning as CPython's other single-word
     attribute writes).
   - Calls `InputInjector.update_screen(width, height, left, top)` with
     the new monitor's geometry, so subsequent pointer coordinates map
     into the correct region of the Windows virtual desktop.
5. The video track's next captured frame is simply a different
   resolution/content; no signaling exchange happens. The viewer's
   existing `object-fit: contain` + letterbox-aware coordinate mapping
   (`useInputControl.ts`, already fixed for aspect-ratio changes) handles
   the resolution change with no viewer-side change needed.

## Components touched

- **`host-app/screentracker_host/capture.py`**
  - New `list_monitors() -> list[dict]`: iterates `mss.mss().monitors[1:]`
    (index 0 is the synthetic "all monitors combined" entry, always
    skipped — consistent with the existing `monitor_index` default of 1)
    and returns `{"index": i, "width": w, "height": h, "left": l, "top": t}`
    per physical monitor.
  - `ScreenCapturer` gets a `set_monitor(index: int) -> None` method:
    `self._monitor_index = index`. No lock — same single-attribute-write
    safety argument as the existing `_monitor_index` field.

- **`host-app/screentracker_host/webrtc_peer.py`**
  - `ScreenCaptureTrack` gets `set_monitor(index: int) -> None`, which
    delegates to `self._capturer.set_monitor(index)`.
  - `HostPeerConnection.__init__` keeps a reference to the constructed
    track (`self._track = ScreenCaptureTrack()`, then
    `self._pc.addTrack(self._track)`) so it can be reached from the
    message handler.
  - `HostPeerConnection.__init__` keeps a reference to the initial
    monitor's geometry (from `list_monitors()`, replacing the current
    `get_monitor_size()` call used only to size `InputInjector` — kept
    as the same tuple-returning helper for the primary monitor so
    existing tests that mock `get_monitor_size` don't need to change;
    `list_monitors()` is additive, not a replacement).
  - The existing `_on_input_message` handler gains a branch: if
    `payload.get("type") == "select-monitor"`, look up the matching
    entry from `list_monitors()` by index (ignore silently, with a log
    line, if the index doesn't exist — e.g. viewer had stale state) and
    call `self._track.set_monitor(index)` +
    `self._input_injector.update_screen(width, height, left, top)`. This
    branch runs before the existing pointer/keyboard dispatch, and does
    not touch `self._input_injector` if the injector is `None` (headless
    host, video-only) — the monitor still switches for the video-only
    case, video keeps working, only the input-mapping call is skipped.
  - On DataChannel `"open"`, send the `monitor-list` message (JSON) once.

- **`host-app/screentracker_host/input_injector.py`**
  - `normalize_to_pixels(x, y, screen_width, screen_height, offset_x=0, offset_y=0)`:
    adds the monitor's `left`/`top` (default 0 preserves current
    single-monitor behavior exactly) so a click on the second monitor
    lands at its real position in Windows' virtual desktop, not
    (0,0)-relative to the primary monitor.
  - `InputInjector.__init__` keeps `self._offset_x = self._offset_y = 0`
    alongside the existing `screen_size` unpack.
  - New `InputInjector.update_screen(width, height, left, top) -> None`
    updates all four stored fields; all four call sites of
    `normalize_to_pixels` in `_dispatch` pass the stored offsets.

- **`viewer-app/src/hooks/useMonitorSelection.ts`** (new hook, mirrors
  the shape of `useInputControl`): listens on the same `inputChannel`'s
  `"message"` event for `{"type": "monitor-list", ...}`, keeps
  `{monitors, activeIndex}` in state, and exposes a `selectMonitor(index)`
  callback that sends `{"type": "select-monitor", "index": N}` and
  optimistically updates `activeIndex`.
  - `useInputControl` currently has no message listener on the channel
    at all (it only sends); adding a `"message"` listener is new but
    additive, and doesn't touch `useInputControl`'s existing send-only
    logic.
- **`viewer-app/src/App.tsx`**: wires `useMonitorSelection`, renders a
  small button group (only when `monitors.length > 1`) positioned over
  `VideoPlayer`.

- **Docs**: the "çoklu monitör kapsam dışı" notes in
  `docs/superpowers/plans/2026-08-18-input-control.md` and
  `docs/superpowers/specs/2026-08-18-input-control-design.md` become
  historical (left as-is — they document what was true when written,
  same policy this project already follows for the touch-injection
  docs).

## Error handling

- **Unknown `select-monitor` index** (stale viewer state, race with a
  monitor being unplugged): host looks it up against a fresh
  `list_monitors()` call, logs and ignores if not found, keeps
  streaming/controlling the current monitor. No crash.
- **Monitor list channel not yet open when the user would want to
  switch**: not reachable — the selector UI only renders once
  `monitor-list` has been received, so there's nothing to click before
  the list exists.
- **A monitor physically disappears after being selected** (unplugged,
  sleep/resume topology change): out of scope for this feature, exactly
  as the existing single-monitor code already doesn't handle a vanishing
  primary monitor beyond the one-shot retry `ScreenCapturer.capture()`
  already does. No new behavior needed or claimed here.
- **Single-monitor hosts**: `monitor-list` has one entry, viewer renders
  no selector, behavior is identical to today.

## Testing

TDD, following the project's existing per-package pytest / vitest split:

- `host-app/tests/test_capture.py`: `list_monitors()` against a mocked
  `mss.mss().monitors` list (multi-entry and single-entry cases);
  `ScreenCapturer.set_monitor()` changes what the next `capture()` grabs.
- `host-app/tests/test_webrtc_peer.py`: `select-monitor` message causes
  `ScreenCaptureTrack.set_monitor` and `InputInjector.update_screen` to
  be called with the right values; unknown index is a no-op; DataChannel
  open sends `monitor-list`.
- `host-app/tests/test_input_injector.py` (existing file, extended):
  `normalize_to_pixels` with non-zero offsets; `update_screen` changes
  subsequent dispatch output.
- `viewer-app/src/hooks/useMonitorSelection.test.ts` (new): receiving a
  `monitor-list` message updates state; `selectMonitor` sends the right
  message and updates `activeIndex` optimistically.
- `viewer-app` component test for the selector's conditional rendering
  (hidden for 1 monitor, buttons for 2+, tapping calls `selectMonitor`).

## Out of scope

- Detecting a monitor that disappears/changes resolution mid-session.
- Remembering the user's monitor choice across reconnects/sessions.
- Showing monitor thumbnails/previews before switching (index-only
  labels, e.g. "Monitor 1" / "Monitor 2", are enough).
