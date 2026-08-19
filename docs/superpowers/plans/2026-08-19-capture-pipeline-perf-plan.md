# Plan: Screen capture pipeline latency optimization

## Context

ScreenTracker's host app (`host-app/screentracker_host/`) streams the host's
screen to a viewer over WebRTC. Latency has been reported as noticeably high
in real-device testing. Investigation found the root cause: `ScreenCaptureTrack.recv()`
(in `webrtc_peer.py`) runs a fully synchronous, blocking `capture_frame()` call
directly on the asyncio event loop, on every frame, at `TARGET_FPS = 15`. Because
the same event loop also handles ICE/RTP housekeeping and the `input` DataChannel's
message handler (mouse/keyboard forwarding to `InputInjector`), every capture
call stalls input responsiveness too, not just video.

Three additional inefficiencies compound this:
- `capture_frame()` (`capture.py`) opens a brand-new `mss.mss()` context on
  every single call instead of reusing one instance — unnecessary GDI/DXGI
  setup cost every frame.
- The BGRA→RGB color conversion in `webrtc_peer.py` does two numpy passes
  (`frame.data[:, :, :3][:, :, ::-1]` then `np.ascontiguousarray(...)`)
  instead of one optimized OpenCV call.
  handle blindly.
- No resolution cap: a 4K/1440p monitor gets encoded at full resolution by
  aiortc's software VP8 encoder, which is far more CPU-expensive than the
  viewer (a phone screen) can actually make use of. 720p–1080p is enough
  quality per the project owner.
- The frame-pacing loop (`_next_frame_time += 1 / TARGET_FPS`) has no drift
  guard: if capture stalls for a long time (system sleep/wake, CPU spike),
  it will try to "catch up" by sending a burst of frames back-to-back.

This plan fixes all of the above by moving capture off the event loop into a
dedicated thread, reusing the `mss` context, converting color with OpenCV in
one pass, capping resolution, and adding a drift guard. It does **not**
change the encoder (still aiortc/PyAV VP8) or move any code to a
non-Python language — that's an explicitly deferred, evidence-gated future
step, not part of this plan.

Repo: `C:\dev\ScreenTracker`. This plan executes in the git worktree at
`.worktrees/perf-capture-pipeline` on branch `perf/capture-pipeline`.
Working directory for both tasks: `host-app/`.

## Global Constraints

- TDD: for every code change, write/update the failing test first, then
  make it pass. Do not write implementation code before its test exists.
- Test command: `python -m pytest -q` run from `host-app/`. Baseline
  (before this plan's changes): 56 passed, 0 failed. Every task must leave
  this suite fully green — no skips, no `xfail`.
- New dependency: `opencv-python-headless` must be added to
  `host-app/requirements.txt` (Task 1). Use `opencv-python-headless`, not
  `opencv-python` — this is a headless server/background process with no
  GUI needs, and the `-headless` build avoids pulling in Qt/GUI shared
  libraries this project will never use.
- Do not touch `viewer-app/`, `signaling-server/`, or `launcher/` in this
  plan — scope is host-app capture pipeline only.
- Do not change `TARGET_FPS`, the WebRTC signaling protocol, or the
  `input` DataChannel message format — out of scope.
- Preserve the existing public entry points other modules rely on:
  `screentracker_host.capture.get_monitor_size()` keeps its current
  signature and behavior (still used by `webrtc_peer.HostPeerConnection`
  to size `InputInjector`) — do not merge it into the new capturer class.
- `Frame` (the dataclass) keeps its current field names (`width`, `height`,
  `data`) but its `data` contract changes: it now holds **RGB** data
  (shape `(height, width, 3)`), not BGRA (shape `(height, width, 4)`) —
  because color conversion moves into the capturer (Task 1) instead of
  happening in `webrtc_peer.py` (Task 2). This is intentional; update every
  test that asserts on `Frame.data`'s shape or dtype accordingly.
- Commit at the end of each task with a message describing what changed
  and why (no co-author trailer — this repo's convention, see recent log).

---

## Task 1: `ScreenCapturer` — reusable, downscaling, single-pass color conversion

**Files:** `host-app/screentracker_host/capture.py`,
`host-app/tests/test_capture.py`, `host-app/requirements.txt`

**Goal:** Replace the free function `capture_frame()` with a stateful
`ScreenCapturer` class that (a) opens exactly one `mss.mss()` context and
reuses it across calls instead of one per call, (b) converts BGRA→RGB with a
single `cv2.cvtColor` call, and (c) downscales the result if its longest
side exceeds a cap, using `cv2.resize` with `INTER_AREA` (the right choice
for shrinking — avoids aliasing that `INTER_LINEAR` would introduce).

Add `opencv-python-headless` to `host-app/requirements.txt` (alongside the
existing pinned deps — check what version resolves cleanly with the already
pinned `numpy==2.1.2` and pin it the same way, e.g. `opencv-python-headless==4.10.0.84`
or whatever the latest compatible 4.10.x/4.11.x release is; run `pip install
opencv-python-headless` in the dev environment to confirm the version and
that `import cv2` plus `import numpy` together don't conflict).

Delete the old free function `capture_frame()` entirely — it has no other
callers after Task 2 rewires `webrtc_peer.py` (Task 2 is a separate task,
but nothing else in the codebase besides `webrtc_peer.py` and
`test_capture.py` imports `capture_frame`, confirmed by repo-wide grep).
Keep `get_monitor_size()` exactly as it is today (own `with mss.mss()`
block — it's a one-shot call, not part of the hot per-frame path, so its
own short-lived context is fine and it must keep working identically for
`HostPeerConnection`'s existing use).

### Implementation (this is the target shape — write the tests first, per
### Global Constraints, then implement to make them pass)

```python
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
```

### Tests to write (replace `test_capture.py`'s existing
`test_capture_frame_returns_frame_with_expected_shape`, keep
`test_get_monitor_size_returns_width_and_height_without_grabbing` as-is
since `get_monitor_size` is unchanged):

1. `ScreenCapturer.__init__` opens exactly one `mss.mss()` — assert the
   mock `mss.mss` constructor was called once at construction time, not
   again inside `capture()`.
2. `ScreenCapturer().capture()` calls `sct.grab()` again on a **second**
   `capture()` call **without** re-constructing `mss.mss()` — i.e. two
   `capture()` calls on the same instance produce two `grab()` calls but
   only one `mss.mss()` construction. This is the regression test for the
   "new context per frame" bug.
3. `capture()` returns a `Frame` whose `data.shape == (height, width, 3)`
   (RGB, not RGBA/BGRA) when the source frame is below `max_dim` — no
   resize applied, shape matches source dimensions exactly.
4. `capture()` downscales when the source's longest side exceeds
   `max_dim`: construct with e.g. `max_dim=100`, mock a captured frame of
   e.g. 200x100 (BGRA, via `mss.grab`/`np.array` mocking — mock `cv2.cvtColor`
   to return a plain RGB array of the source's shape so the test isolates
   resize logic from real color math), and assert the returned `Frame`'s
   longest side is exactly `max_dim` and the aspect ratio is preserved
   (within rounding).
5. `capture()` does **not** downscale when the source is at or below
   `max_dim` on both dimensions (boundary case: longest side == max_dim
   exactly → no resize call).
6. `close()` calls the underlying `mss` context's `close()`.

Use the same mocking approach the existing tests use (`patch(
"screentracker_host.capture.mss.mss")`, `MagicMock` for the `sct` object)
— keep the pattern consistent with `test_get_monitor_size...` in the same
file. Mock `cv2.cvtColor`/`cv2.resize` where the test is about capture
orchestration or resize math, not about verifying OpenCV's own color/resize
correctness (that's OpenCV's job to get right, not this project's).

**Report file:** implementer writes status/commits/test summary to the
report path given in the dispatch. Full narrative goes in the report file,
not back to the controller inline.

---

## Task 2: Move capture off the event loop, add drift guard

**Files:** `host-app/screentracker_host/webrtc_peer.py`,
`host-app/tests/test_webrtc_peer.py`

**Depends on Task 1:** uses `ScreenCapturer` from
`screentracker_host.capture` (Task 1's new class) instead of the old
`capture_frame()` free function, which Task 1 deletes.

**Goal:** `ScreenCaptureTrack.recv()` currently calls a blocking
`capture_frame()` synchronously on the asyncio event loop — this stalls
every other coroutine on that loop (ICE/RTP housekeeping, and critically
the `input` DataChannel's message handler that forwards mouse/keyboard
events to `InputInjector`) for the full duration of every capture. Move the
actual capture+convert+resize work to a dedicated single-worker thread via
`concurrent.futures.ThreadPoolExecutor` + `loop.run_in_executor()`, so the
event loop stays free while a frame is being captured. Also add a drift
guard to the frame-pacing logic so a long stall (system sleep/wake, a CPU
spike) doesn't cause the track to fire off a burst of frames trying to
"catch up."

Since `Frame.data` is now RGB (Task 1's contract change), delete the old
two-pass BGRA→RGB conversion in `recv()`
(`frame.data[:, :, :3][:, :, ::-1]` + `np.ascontiguousarray(...)`) — the
data arriving from `ScreenCapturer.capture()` is already RGB and
contiguous; hand it to `VideoFrame.from_ndarray(..., format="rgb24")`
directly.

### Implementation shape (write failing tests first, then implement)

```python
from concurrent.futures import ThreadPoolExecutor

from screentracker_host.capture import ScreenCapturer, get_monitor_size

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

        self._next_frame_time += 1 / TARGET_FPS

        return video_frame
```

`HostPeerConnection.__init__` still calls `get_monitor_size()` for
`InputInjector` sizing exactly as it does today (Task 1 preserves that
function unchanged) — no change needed there beyond the import already
being updated for `ScreenCapturer`.

### Tests to write/update in `test_webrtc_peer.py`:

The two existing tests that monkeypatch
`"screentracker_host.webrtc_peer.capture_frame"`
(`test_recv_returns_video_frame_matching_capture_size` and
`test_recv_paces_frames_to_target_fps`) must be rewritten because
`capture_frame` no longer exists in this module — replace by monkeypatching
`ScreenCapturer.capture` (e.g. `monkeypatch.setattr(ScreenCapturer,
"capture", lambda self: fake_frame)`) or by patching the `ScreenCapturer`
class used inside `ScreenCaptureTrack.__init__` so the track's
`self._capturer.capture` resolves to a stub. Frame fixtures change from
BGRA `(2, 4, 4)` to RGB `(2, 4, 3)` shape, matching Task 1's new `Frame`
contract. Keep the pacing-math assertions in
`test_recv_paces_frames_to_target_fps` identical (same expected sleep
durations) — pacing logic itself doesn't change, only where the capture
call happens.

New tests to add:

1. **`recv()` does not block the event loop during capture.** Use a stub
   capture function that blocks for a short, deterministic duration (e.g.
   `time.sleep(0.05)` inside the stub run via the real executor — do not
   mock `run_in_executor` itself, since that's exactly the mechanism under
   test) and assert that another coroutine scheduled concurrently (e.g. via
   `asyncio.gather` with a `asyncio.sleep(0)`-based marker coroutine, or by
   asserting the marker coroutine's completion timestamp is *not*
   serialized after the blocking capture) actually gets to run during that
   window. A concrete approach: track wall-clock entry/exit of both the
   marker coroutine and the stub capture using `time.monotonic()`, run them
   concurrently with `asyncio.gather`, and assert the marker coroutine
   finished before the blocking capture did — proving they overlapped
   rather than ran strictly sequentially on one loop.
2. **Drift guard resets pacing after a long stall.** Simulate
   `time.monotonic()` jumping forward by more than `MAX_PACING_DRIFT_SECONDS`
   between two `recv()` calls (monkeypatch `time.monotonic` the same way
   `test_recv_paces_frames_to_target_fps` already does, with a controlled
   sequence of return values) and assert `recv()` does **not** call
   `asyncio.sleep` with a large catch-up duration — i.e. after the jump,
   `_next_frame_time` was reset to (approximately) the post-jump `now`,
   not left at its pre-jump scheduled value.
3. **`recv()` uses `ScreenCapturer` (not `mss` or the old `capture_frame`
   directly)** — a straightforward assertion that the stub capture function
   was actually invoked to produce the returned `VideoFrame`'s dimensions,
   proving the wiring is correct end-to-end.

Run the **full** `host-app` suite (`python -m pytest -q` from `host-app/`)
before reporting done — Task 1's `test_capture.py` changes and this task's
`test_webrtc_peer.py` changes must both be green together, along with every
other untouched test file (56 baseline + whatever net-new tests this plan
adds, 0 failures).

**Report file:** implementer writes status/commits/test summary to the
report path given in the dispatch. Full narrative goes in the report file,
not back to the controller inline.
