# Multi-Monitor Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a viewer with 2+ physical monitors on the host see a monitor list and live-switch which one is streamed and controlled, without any WebRTC renegotiation.

**Architecture:** The host detects monitors via `mss` and broadcasts them once the existing `"input"` RTCDataChannel opens. The viewer renders a selector; tapping a monitor sends a `select-monitor` message on the same channel. The host swaps `ScreenCaptureTrack`'s active `monitor_index` and `InputInjector`'s screen geometry in place — the `RTCPeerConnection` and its video track are never touched, so no offer/answer exchange happens.

**Tech Stack:** Python (`mss`, `aiortc`, `pytest`) for the host; TypeScript/React (`vitest`, `@testing-library/react`) for the viewer.

**Spec:** `docs/superpowers/specs/2026-08-20-multi-monitor-selection-design.md`

## Global Constraints

- No WebRTC renegotiation for monitor switching — the video track and peer connection must not be recreated when the monitor changes.
- Monitor index 0 (mss's synthetic "all monitors combined" entry) is always excluded from any monitor list shown to the user, consistent with the codebase's existing default of `monitor_index=1`.
- Single-monitor hosts must see zero behavior change: `list_monitors()` returns one entry, the viewer renders no selector, and default offsets (0,0) leave `normalize_to_pixels` output identical to today's.
- An unknown/stale `select-monitor` index must be logged and ignored, never raise or crash the host process.

---

### Task 1: `capture.py` — monitor enumeration and runtime monitor switching

**Files:**
- Modify: `host-app/screentracker_host/capture.py`
- Test: `host-app/tests/test_capture.py`

**Interfaces:**
- Consumes: `mss.mss()` (existing dependency, same mocking pattern already used in this test file).
- Produces: `list_monitors() -> list[dict]` where each dict is `{"index": int, "width": int, "height": int, "left": int, "top": int}`; `ScreenCapturer.set_monitor(index: int) -> None` — consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Add to `host-app/tests/test_capture.py` (uses the same `_make_mock_sct`-style mocking already in this file; `list_monitors()` needs a multi-monitor `monitors` list, so build it inline rather than reusing `_make_mock_sct`, which only ever sets up one monitor):

```python
def test_list_monitors_excludes_the_synthetic_all_monitors_entry():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3200, "height": 1080},  # index 0: synthetic combined
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1280, "height": 1080},
        ]
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        from screentracker_host.capture import list_monitors

        monitors = list_monitors()

    assert monitors == [
        {"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0},
        {"index": 2, "width": 1280, "height": 1080, "left": 1920, "top": 0},
    ]


def test_list_monitors_returns_single_entry_for_a_single_monitor_host():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        from screentracker_host.capture import list_monitors

        monitors = list_monitors()

    assert monitors == [{"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0}]


def test_set_monitor_changes_which_monitor_the_next_capture_grabs():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        width, height = 100, 50
        mock_sct.monitors = [
            None,
            {"left": 0, "top": 0, "width": width, "height": height},
            {"left": width, "top": 0, "width": width, "height": height},
        ]
        fake_raw = MagicMock()
        fake_raw.width = width
        fake_raw.height = height
        mock_sct.grab.return_value = fake_raw
        mock_mss_cls.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((height, width, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((height, width, 3), dtype=np.uint8),
        ):
            capturer = ScreenCapturer()
            capturer.set_monitor(2)
            capturer.capture()

    mock_sct.grab.assert_called_once_with(mock_sct.monitors[2])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd host-app && python -m pytest tests/test_capture.py -k "list_monitors or set_monitor_changes" -v`
Expected: FAIL — `ImportError: cannot import name 'list_monitors'` / `AttributeError: 'ScreenCapturer' object has no attribute 'set_monitor'`

- [ ] **Step 3: Implement `list_monitors()` and `ScreenCapturer.set_monitor()`**

In `host-app/screentracker_host/capture.py`, add after `get_monitor_size`:

```python
def list_monitors() -> list[dict]:
    """All physical monitors mss can see, excluding index 0 (mss's synthetic
    "all monitors combined" entry -- never a real capture target, and never
    what `monitor_index`'s default of 1 refers to)."""
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
```

In `ScreenCapturer`, add after `__init__`:

```python
    def set_monitor(self, index: int) -> None:
        """Changes which monitor the next capture() grabs. A plain attribute
        write is safe without a lock here: the capture worker thread only
        ever reads self._monitor_index at the start of _grab(), and CPython
        attribute assignment is atomic, so a switch takes effect cleanly on
        the very next frame with no torn read possible."""
        self._monitor_index = index
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd host-app && python -m pytest tests/test_capture.py -v`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add host-app/screentracker_host/capture.py host-app/tests/test_capture.py
git commit -m "feat(host): add monitor enumeration and runtime monitor switching to ScreenCapturer"
```

---

### Task 2: `input_injector.py` — offset-aware coordinate normalization

**Files:**
- Modify: `host-app/screentracker_host/input_injector.py`
- Test: `host-app/tests/test_input_injector.py`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `normalize_to_pixels(x, y, screen_width, screen_height, offset_x=0, offset_y=0) -> tuple[int, int]`; `InputInjector.update_screen(width: int, height: int, left: int, top: int) -> None` — consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Add to `host-app/tests/test_input_injector.py`:

```python
def test_normalize_to_pixels_defaults_offset_to_zero():
    assert normalize_to_pixels(0.5, 0.25, 1920, 1080) == (960, 270)


def test_normalize_to_pixels_applies_offset():
    # A second monitor sitting to the right of a 1920-wide primary monitor.
    assert normalize_to_pixels(0.5, 0.25, 1920, 1080, offset_x=1920, offset_y=0) == (2880, 270)


def test_update_screen_changes_subsequent_pointer_mapping(injector):
    instance, mock_mouse, _, _ = injector

    instance.update_screen(width=1920, height=1080, left=1920, top=0)
    # Right button: goes straight through pynput's `self._mouse.position =
    # pixels`, so the exact mapped pixel is directly assertable (unlike the
    # left-button path, which goes through the mocked SendInput conversion).
    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "right"})

    assert mock_mouse.position == (2880, 540)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd host-app && python -m pytest tests/test_input_injector.py -k "offset or update_screen" -v`
Expected: FAIL — `TypeError: normalize_to_pixels() got an unexpected keyword argument 'offset_x'` / `AttributeError: 'InputInjector' object has no attribute 'update_screen'`

- [ ] **Step 3: Implement offset support**

In `host-app/screentracker_host/input_injector.py`, replace `normalize_to_pixels`:

```python
def normalize_to_pixels(
    x: float, y: float, screen_width: int, screen_height: int, offset_x: int = 0, offset_y: int = 0
) -> tuple[int, int]:
    px = round(clamp_unit(x) * screen_width) + offset_x
    py = round(clamp_unit(y) * screen_height) + offset_y
    return px, py
```

In `InputInjector.__init__`, after `self._screen_width, self._screen_height = screen_size`:

```python
        self._offset_x = 0
        self._offset_y = 0
```

Add a new method:

```python
    def update_screen(self, width: int, height: int, left: int, top: int) -> None:
        """Called when the viewer switches which monitor is active -- see
        webrtc_peer.py's select-monitor handling. left/top are the
        monitor's position in the Windows virtual desktop (mss's
        "left"/"top"), needed so pointer coordinates land on the right
        monitor's actual global position, not (0,0)-relative to whichever
        monitor happens to be primary."""
        self._screen_width = width
        self._screen_height = height
        self._offset_x = left
        self._offset_y = top
```

In `_dispatch`, update all three `normalize_to_pixels(...)` call sites (pointer-down, pointer-move, pointer-up) to pass the stored offsets:

```python
            pixels = normalize_to_pixels(
                message["x"], message["y"], self._screen_width, self._screen_height,
                self._offset_x, self._offset_y,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd host-app && python -m pytest tests/test_input_injector.py -v`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add host-app/screentracker_host/input_injector.py host-app/tests/test_input_injector.py
git commit -m "feat(host): make pointer coordinate normalization monitor-offset-aware"
```

---

### Task 3: `webrtc_peer.py` — live monitor switching over the input channel

**Files:**
- Modify: `host-app/screentracker_host/webrtc_peer.py`
- Test: `host-app/tests/test_webrtc_peer.py`

**Interfaces:**
- Consumes: `ScreenCapturer.set_monitor(index)` and `list_monitors()` from Task 1 (`from screentracker_host.capture import ScreenCapturer, get_monitor_size, list_monitors`); `InputInjector.update_screen(width, height, left, top)` from Task 2.
- Produces: `ScreenCaptureTrack.set_monitor(index: int) -> None`; `HostPeerConnection` broadcasts `{"type": "monitor-list", "monitors": [...]}` on its `"input"` channel's `"open"` event, and handles incoming `{"type": "select-monitor", "index": N}` messages — consumed by Task 4/5 (the viewer) via the wire protocol, not by any other Python code.

- [ ] **Step 1: Write the failing tests**

Add to `host-app/tests/test_webrtc_peer.py`:

```python
def test_set_monitor_delegates_to_the_capturer():
    track = ScreenCaptureTrack()
    track._capturer.set_monitor = MagicMock()

    track.set_monitor(2)

    track._capturer.set_monitor.assert_called_once_with(2)


def test_data_channel_open_broadcasts_the_monitor_list(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.list_monitors",
        lambda: [
            {"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0},
            {"index": 2, "width": 1280, "height": 720, "left": 1920, "top": 0},
        ],
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    peer._input_channel.send = MagicMock()

    peer._input_channel.emit("open")

    peer._input_channel.send.assert_called_once()
    sent = json.loads(peer._input_channel.send.call_args[0][0])
    assert sent == {
        "type": "monitor-list",
        "monitors": [
            {"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0},
            {"index": 2, "width": 1280, "height": 720, "left": 1920, "top": 0},
        ],
    }


def test_select_monitor_message_switches_track_and_updates_injector(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.list_monitors",
        lambda: [
            {"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0},
            {"index": 2, "width": 1280, "height": 720, "left": 1920, "top": 0},
        ],
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    peer._track.set_monitor = MagicMock()

    peer._input_channel.emit("message", json.dumps({"type": "select-monitor", "index": 2}))

    peer._track.set_monitor.assert_called_once_with(2)
    fake_injector.update_screen.assert_called_once_with(1280, 720, 1920, 0)


def test_select_monitor_with_unknown_index_is_ignored(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.list_monitors",
        lambda: [{"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0}],
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    peer._track.set_monitor = MagicMock()

    peer._input_channel.emit("message", json.dumps({"type": "select-monitor", "index": 99}))

    peer._track.set_monitor.assert_not_called()
    fake_injector.update_screen.assert_not_called()


def test_select_monitor_switches_video_even_when_input_injector_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector",
        lambda screen_size: (_ for _ in ()).throw(RuntimeError("no display available")),
    )
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.list_monitors",
        lambda: [
            {"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0},
            {"index": 2, "width": 1280, "height": 720, "left": 1920, "top": 0},
        ],
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    assert peer._input_injector is None
    peer._track.set_monitor = MagicMock()

    # Must not raise even with no injector to update.
    peer._input_channel.emit("message", json.dumps({"type": "select-monitor", "index": 2}))

    peer._track.set_monitor.assert_called_once_with(2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd host-app && python -m pytest tests/test_webrtc_peer.py -k "set_monitor or monitor_list or select_monitor" -v`
Expected: FAIL — `AttributeError: 'ScreenCaptureTrack' object has no attribute 'set_monitor'` (and the rest failing similarly once that's fixed, since `list_monitors` isn't imported into `webrtc_peer` yet and `peer._track` doesn't exist)

- [ ] **Step 3: Implement**

In `host-app/screentracker_host/webrtc_peer.py`, update the import line:

```python
from screentracker_host.capture import ScreenCapturer, get_monitor_size, list_monitors
```

Add to `ScreenCaptureTrack`, after `__init__`:

```python
    def set_monitor(self, index: int) -> None:
        self._capturer.set_monitor(index)
```

In `HostPeerConnection.__init__`, replace `self._pc.addTrack(ScreenCaptureTrack())` with:

```python
        self._track = ScreenCaptureTrack()
        self._pc.addTrack(self._track)
```

Replace the existing `_on_input_message` handler and add an `"open"` handler right after it (still inside `__init__`, after `self._input_channel = self._pc.createDataChannel("input")`):

```python
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
```

Add a new method to `HostPeerConnection` (e.g. right after `__init__`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd host-app && python -m pytest tests/test_webrtc_peer.py -v`
Expected: PASS (all tests, including the pre-existing ones — in particular re-check `test_input_channel_message_is_forwarded_to_injector` and `test_malformed_input_channel_message_is_dropped`, which exercise the same handler and must be unaffected)

- [ ] **Step 5: Run the full host-app suite**

Run: `cd host-app && python -m pytest -v`
Expected: PASS, no regressions in `test_capture.py` or `test_input_injector.py` either

- [ ] **Step 6: Commit**

```bash
git add host-app/screentracker_host/webrtc_peer.py host-app/tests/test_webrtc_peer.py
git commit -m "feat(host): broadcast monitor list and handle live monitor switching over the input channel"
```

---

### Task 4: `useMonitorSelection` viewer hook

**Files:**
- Create: `viewer-app/src/hooks/useMonitorSelection.ts`
- Test: `viewer-app/tests/useMonitorSelection.test.ts`

**Interfaces:**
- Consumes: `RTCDataChannel | null` (the same `inputChannel` object `useWebRTCViewer` already returns and `useInputControl` already sends on).
- Produces: `useMonitorSelection(channel: RTCDataChannel | null) -> { monitors: MonitorInfo[]; activeIndex: number | null; selectMonitor: (index: number) => void }` where `MonitorInfo = { index: number; width: number; height: number; left: number; top: number }` — consumed by Task 5.

- [ ] **Step 1: Write the failing test**

Create `viewer-app/tests/useMonitorSelection.test.ts`:

```typescript
import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMonitorSelection } from "../src/hooks/useMonitorSelection";

class FakeDataChannel extends EventTarget {
  readyState: RTCDataChannelState;
  send = vi.fn();

  constructor(readyState: RTCDataChannelState = "open") {
    super();
    this.readyState = readyState;
  }

  receive(payload: unknown) {
    this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(payload) }));
  }
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useMonitorSelection", () => {
  it("starts with no monitors and no active index", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    expect(result.current.monitors).toEqual([]);
    expect(result.current.activeIndex).toBeNull();
  });

  it("stores the monitor list and defaults the active index to the first monitor", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.receive({
        type: "monitor-list",
        monitors: [
          { index: 1, width: 1920, height: 1080, left: 0, top: 0 },
          { index: 2, width: 1280, height: 720, left: 1920, top: 0 },
        ],
      });
    });

    expect(result.current.monitors).toHaveLength(2);
    expect(result.current.activeIndex).toBe(1);
  });

  it("ignores messages of other types", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.receive({ type: "pointer-down", x: 0.5, y: 0.5, button: "left" });
    });

    expect(result.current.monitors).toEqual([]);
  });

  it("ignores unparseable message data", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.dispatchEvent(new MessageEvent("message", { data: "not valid json" }));
    });

    expect(result.current.monitors).toEqual([]);
  });

  it("selectMonitor sends a select-monitor message and updates activeIndex optimistically", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.receive({
        type: "monitor-list",
        monitors: [
          { index: 1, width: 1920, height: 1080, left: 0, top: 0 },
          { index: 2, width: 1280, height: 720, left: 1920, top: 0 },
        ],
      });
    });

    act(() => {
      result.current.selectMonitor(2);
    });

    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "select-monitor", index: 2 }));
    expect(result.current.activeIndex).toBe(2);
  });

  it("selectMonitor does nothing when the channel isn't open", () => {
    const channel = new FakeDataChannel("connecting");
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      result.current.selectMonitor(2);
    });

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("resets to no monitors when the channel becomes null", () => {
    const channel = new FakeDataChannel();
    const { result, rerender } = renderHook(
      ({ ch }: { ch: RTCDataChannel | null }) => useMonitorSelection(ch),
      { initialProps: { ch: channel as unknown as RTCDataChannel } }
    );

    act(() => {
      channel.receive({
        type: "monitor-list",
        monitors: [{ index: 1, width: 1920, height: 1080, left: 0, top: 0 }],
      });
    });
    expect(result.current.monitors).toHaveLength(1);

    rerender({ ch: null });

    expect(result.current.monitors).toEqual([]);
    expect(result.current.activeIndex).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd viewer-app && npx vitest run tests/useMonitorSelection.test.ts`
Expected: FAIL — cannot find module `../src/hooks/useMonitorSelection`

- [ ] **Step 3: Implement the hook**

Create `viewer-app/src/hooks/useMonitorSelection.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";

export interface MonitorInfo {
  index: number;
  width: number;
  height: number;
  left: number;
  top: number;
}

interface UseMonitorSelectionResult {
  monitors: MonitorInfo[];
  activeIndex: number | null;
  selectMonitor: (index: number) => void;
}

// Listens on the same "input" RTCDataChannel useInputControl already sends
// on -- the host broadcasts monitor-list once on channel open, this hook
// just needs a message listener, not a separate channel.
export function useMonitorSelection(channel: RTCDataChannel | null): UseMonitorSelectionResult {
  const [monitors, setMonitors] = useState<MonitorInfo[]>([]);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  useEffect(() => {
    setMonitors([]);
    setActiveIndex(null);
    if (!channel) return;

    function handleMessage(event: Event) {
      const data = (event as MessageEvent).data;
      let payload: { type?: string; monitors?: MonitorInfo[] };
      try {
        payload = JSON.parse(data);
      } catch {
        return;
      }
      if (payload.type !== "monitor-list" || !Array.isArray(payload.monitors)) return;
      setMonitors(payload.monitors);
      setActiveIndex(payload.monitors[0]?.index ?? null);
    }

    channel.addEventListener("message", handleMessage);
    return () => channel.removeEventListener("message", handleMessage);
  }, [channel]);

  const selectMonitor = useCallback(
    (index: number) => {
      if (!channel || channel.readyState !== "open") return;
      channel.send(JSON.stringify({ type: "select-monitor", index }));
      setActiveIndex(index);
    },
    [channel]
  );

  return { monitors, activeIndex, selectMonitor };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd viewer-app && npx vitest run tests/useMonitorSelection.test.ts`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add viewer-app/src/hooks/useMonitorSelection.ts viewer-app/tests/useMonitorSelection.test.ts
git commit -m "feat(viewer): add useMonitorSelection hook for the monitor-list/select-monitor protocol"
```

---

### Task 5: `VideoPlayer` monitor selector UI

**Files:**
- Modify: `viewer-app/src/components/VideoPlayer.tsx`
- Modify: `viewer-app/src/components/VideoPlayer.module.css`
- Test: `viewer-app/tests/VideoPlayer.test.tsx`

**Interfaces:**
- Consumes: `useMonitorSelection(channel)` from Task 4, using the same `inputChannel` prop `VideoPlayer` already receives.
- Produces: nothing further downstream — this is the UI leaf.

- [ ] **Step 1: Write the failing tests**

Add to `viewer-app/tests/VideoPlayer.test.tsx` (the file already defines `FakeDataChannel`; give it a `send` mock and a `receive` helper so these tests and the pre-existing ones can share it):

```typescript
// Add to the existing FakeDataChannel class in this file:
//   send = vi.fn();
//   receive(payload: unknown) {
//     this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(payload) }));
//   }

describe("monitor selector", () => {
  it("shows no selector when there is only one monitor", () => {
    const fakeStream = {} as MediaStream;
    const channel = new FakeDataChannel("open");
    render(<VideoPlayer stream={fakeStream} inputChannel={channel as unknown as RTCDataChannel} />);

    channel.receive({
      type: "monitor-list",
      monitors: [{ index: 1, width: 1920, height: 1080, left: 0, top: 0 }],
    });

    expect(screen.queryByRole("button", { name: /monitor 1/i })).not.toBeInTheDocument();
  });

  it("shows one button per monitor when there are two or more", async () => {
    const fakeStream = {} as MediaStream;
    const channel = new FakeDataChannel("open");
    render(<VideoPlayer stream={fakeStream} inputChannel={channel as unknown as RTCDataChannel} />);

    channel.receive({
      type: "monitor-list",
      monitors: [
        { index: 1, width: 1920, height: 1080, left: 0, top: 0 },
        { index: 2, width: 1280, height: 720, left: 1920, top: 0 },
      ],
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /monitor 1/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /monitor 2/i })).toBeInTheDocument();
    });
  });

  it("sends select-monitor and marks the tapped button active", async () => {
    const user = userEvent.setup();
    const fakeStream = {} as MediaStream;
    const channel = new FakeDataChannel("open");
    render(<VideoPlayer stream={fakeStream} inputChannel={channel as unknown as RTCDataChannel} />);

    channel.receive({
      type: "monitor-list",
      monitors: [
        { index: 1, width: 1920, height: 1080, left: 0, top: 0 },
        { index: 2, width: 1280, height: 720, left: 1920, top: 0 },
      ],
    });

    const monitor2Button = await screen.findByRole("button", { name: /monitor 2/i });
    await user.click(monitor2Button);

    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "select-monitor", index: 2 }));
    expect(monitor2Button).toHaveAttribute("aria-pressed", "true");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd viewer-app && npx vitest run tests/VideoPlayer.test.tsx`
Expected: FAIL — no "Monitor 1"/"Monitor 2" buttons found (selector doesn't exist yet)

- [ ] **Step 3: Implement the selector UI**

In `viewer-app/src/components/VideoPlayer.tsx`, add the import and hook call, and render the selector inside `toolbarRight`:

```typescript
import { useMonitorSelection } from "../hooks/useMonitorSelection";
```

Inside `VideoPlayer`, after the existing `useInputControl` call:

```typescript
  const { monitors, activeIndex, selectMonitor } = useMonitorSelection(inputChannel);
```

In the JSX, inside `<div className={styles.toolbarRight}>`, before the fullscreen button:

```tsx
        {monitors.length > 1 && (
          <div className={styles.monitorSelector}>
            {monitors.map((monitor) => (
              <button
                key={monitor.index}
                type="button"
                className={
                  monitor.index === activeIndex
                    ? `${styles.monitorButton} ${styles.monitorButtonActive}`
                    : styles.monitorButton
                }
                aria-pressed={monitor.index === activeIndex}
                onClick={() => selectMonitor(monitor.index)}
              >
                Monitor {monitor.index}
              </button>
            ))}
          </div>
        )}
```

In `viewer-app/src/components/VideoPlayer.module.css`, add:

```css
.monitorSelector {
  display: flex;
  gap: var(--space-1);
}

.monitorButton {
  padding: var(--space-1) var(--space-2);
  border: none;
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text-secondary);
  font-family: var(--font-display);
  font-size: 12px;
  cursor: pointer;
}

.monitorButton:hover {
  color: var(--accent);
}

.monitorButtonActive {
  color: var(--accent);
  background: var(--surface);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd viewer-app && npx vitest run tests/VideoPlayer.test.tsx`
Expected: PASS (all tests, including the pre-existing ones)

- [ ] **Step 5: Run the full viewer-app suite**

Run: `cd viewer-app && npx vitest run`
Expected: PASS, no regressions elsewhere

- [ ] **Step 6: Rebuild the viewer dist**

This project's standing rule: any `viewer-app` source change must be rebuilt before a real device can see it (`start.bat` serves the prebuilt `dist/`, not live source).

Run: `cd viewer-app && npm run build`
Expected: builds cleanly, `dist/` updated

- [ ] **Step 7: Commit**

```bash
git add viewer-app/src/components/VideoPlayer.tsx viewer-app/src/components/VideoPlayer.module.css viewer-app/tests/VideoPlayer.test.tsx viewer-app/dist
git commit -m "feat(viewer): add monitor selector UI to VideoPlayer"
```

---

## Manual verification (after all tasks land)

Not automatable — requires a real multi-monitor Windows host:

1. Start the host on a machine with 2+ monitors (`start.bat` or `start-dev.bat`).
2. Connect from the phone viewer; confirm "Monitor 1" is the only or default-active button if 2+ monitors are present.
3. Tap "Monitor 2": video should switch to the second monitor's content within roughly one frame interval, with no reconnect/black-screen flash.
4. With Monitor 2 active, tap/click near a known on-screen element on that monitor (e.g. an icon near its edge) and confirm the click lands at the correct on-screen position, not offset by the primary monitor's width.
5. Switch back to Monitor 1 and confirm both video and clicks are correct again.
