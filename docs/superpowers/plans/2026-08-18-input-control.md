# Faz 2: Uzaktan Input Kontrolü Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Viewer'daki dokunma/mouse/klavye/scroll girdisini, mevcut WebRTC bağlantısına eklenen bir `RTCDataChannel` üzerinden host'a iletip `pynput` ile OS-seviyesi input'a çevirmek.

**Architecture:** Host (offer'ı oluşturan taraf) `createDataChannel("input")` çağırır; bu, mevcut offer/answer SDP değişimi içinde otomatik müzakere edilir — signaling server'a hiç dokunulmaz. Viewer, video elementi üzerindeki pointer/wheel/keyboard event'lerini normalize koordinatlı JSON mesajlara çevirip kanaldan gönderir. Host, mesajı alınca normalize koordinatı gerçek ekran pikseline çevirip `pynput.mouse.Controller` / `pynput.keyboard.Controller` çağırır.

**Tech Stack:** Python `pynput==1.8.2` (host), tarayıcı native `RTCDataChannel` + Pointer Events API (viewer) — yeni harici bağımlılık yalnızca host tarafında.

**Spec:** `docs/superpowers/specs/2026-08-18-input-control-design.md`

## Global Constraints

- Sinyalizasyon protokolüne (WebSocket mesaj tipleri) hiçbir değişiklik yok — tüm yeni mesajlar DataChannel üzerinde, `docs/api-spec.md`'nin WebSocket tablosundan tamamen ayrı bir bölümde belgelenir
- Mevcut device pairing onayı yeterli sayılır — input için ayrı bir onay adımı/toggle **eklenmeyecek**
- Host, tek birincil monitörü hedefler (`mss` `monitor_index=1`, Faz 1 ile tutarlı) — çoklu monitör kapsam dışı
- Host tarafında hiçbir istisna ana döngüyü (`run()`'daki `async for`) çökertmemeli — Task 10'da (device pairing) öğrenilen ders burada da geçerli
- DataChannel kapalıyken (`readyState !== "open"`) viewer input event'lerini sessizce yok sayar, hata göstermez

---

## Task 1: Host ekran boyutunu okuma

**Files:**
- Modify: `host-app/screentracker_host/capture.py`
- Test: `host-app/tests/test_capture.py`

**Interfaces:**
- Consumes: `mss.mss()` (mevcut bağımlılık)
- Produces: `get_monitor_size(monitor_index: int = 1) -> tuple[int, int]` — `(width, height)`

- [ ] **Step 1: Write the failing test**

`host-app/tests/test_capture.py` dosyasının sonuna ekle:

```python
from screentracker_host.capture import capture_frame, get_monitor_size


def test_get_monitor_size_returns_width_and_height_without_grabbing():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [None, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        size = get_monitor_size()

    assert size == (1920, 1080)
    mock_sct.grab.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd host-app && venv\Scripts\python.exe -m pytest tests/test_capture.py::test_get_monitor_size_returns_width_and_height_without_grabbing -v`
Expected: FAIL — `ImportError: cannot import name 'get_monitor_size'`

- [ ] **Step 3: Write minimal implementation**

`host-app/screentracker_host/capture.py`'ye ekle (dosyanın sonuna):

```python
def get_monitor_size(monitor_index: int = 1) -> tuple[int, int]:
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        return monitor["width"], monitor["height"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd host-app && venv\Scripts\python.exe -m pytest tests/test_capture.py -v`
Expected: tüm testler PASS (mevcutlar + yeni)

- [ ] **Step 5: Commit**

```bash
git add host-app/screentracker_host/capture.py host-app/tests/test_capture.py
git commit -m "feat: add get_monitor_size for input coordinate mapping"
```

---

## Task 2: Koordinat/wheel/tuş dönüşümü — saf fonksiyonlar

**Files:**
- Create: `host-app/screentracker_host/input_injector.py`
- Test: `host-app/tests/test_input_injector.py`

**Interfaces:**
- Consumes: —
- Produces:
  - `clamp_unit(value: float) -> float`
  - `normalize_to_pixels(x: float, y: float, screen_width: int, screen_height: int) -> tuple[int, int]`
  - `wheel_delta_to_scroll_units(delta_x: float, delta_y: float) -> tuple[int, int]`
  - `resolve_key(key: str) -> pynput.keyboard.Key | str`
  - `KEY_MAP: dict[str, pynput.keyboard.Key]`

- [ ] **Step 1: Write the failing tests**

`host-app/tests/test_input_injector.py` (yeni dosya):

```python
from pynput.keyboard import Key

from screentracker_host.input_injector import (
    clamp_unit,
    normalize_to_pixels,
    resolve_key,
    wheel_delta_to_scroll_units,
)


def test_clamp_unit_passes_through_in_range_values():
    assert clamp_unit(0.5) == 0.5


def test_clamp_unit_clamps_below_zero():
    assert clamp_unit(-0.3) == 0.0


def test_clamp_unit_clamps_above_one():
    assert clamp_unit(1.7) == 1.0


def test_normalize_to_pixels_scales_by_screen_size():
    assert normalize_to_pixels(0.5, 0.25, 1920, 1080) == (960, 270)


def test_normalize_to_pixels_clamps_out_of_range_input():
    assert normalize_to_pixels(-1.0, 2.0, 1920, 1080) == (0, 1080)


def test_wheel_delta_to_scroll_units_scales_and_inverts_y():
    assert wheel_delta_to_scroll_units(200, 100) == (2, -1)


def test_wheel_delta_to_scroll_units_handles_negative_deltas():
    assert wheel_delta_to_scroll_units(-100, -100) == (-1, 1)


def test_resolve_key_maps_named_keys():
    assert resolve_key("Enter") == Key.enter
    assert resolve_key("ArrowUp") == Key.up
    assert resolve_key(" ") == Key.space


def test_resolve_key_passes_through_plain_characters():
    assert resolve_key("a") == "a"
    assert resolve_key("A") == "A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd host-app && venv\Scripts\python.exe -m pytest tests/test_input_injector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'screentracker_host.input_injector'`

- [ ] **Step 3: Write minimal implementation**

`host-app/screentracker_host/input_injector.py` (yeni dosya):

```python
from pynput.keyboard import Key

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd host-app && venv\Scripts\python.exe -m pytest tests/test_input_injector.py -v`
Expected: tüm testler PASS

- [ ] **Step 5: Commit**

```bash
git add host-app/screentracker_host/input_injector.py host-app/tests/test_input_injector.py
git commit -m "feat: add coordinate, wheel, and key translation helpers for input control"
```

---

## Task 3: `InputInjector` — pynput sarmalayıcısı

**Files:**
- Modify: `host-app/screentracker_host/input_injector.py`
- Modify: `host-app/requirements.txt`
- Test: `host-app/tests/test_input_injector.py`

**Interfaces:**
- Consumes: `clamp_unit`, `normalize_to_pixels`, `wheel_delta_to_scroll_units`, `resolve_key` (Task 2, same file)
- Produces: `InputInjector` class — `__init__(self, screen_size: tuple[int, int]) -> None`, `handle_message(self, message: dict) -> None`

- [ ] **Step 1: Add `pynput` to requirements**

`host-app/requirements.txt`'ye ekle:

```
pynput==1.8.2
```

Zaten kurulu değilse: `cd host-app && venv\Scripts\python.exe -m pip install -r requirements.txt`

- [ ] **Step 2: Write the failing tests**

`host-app/tests/test_input_injector.py`'nin sonuna ekle (üstteki importlara `MagicMock`, `patch`, `pytest` ekle):

```python
from unittest.mock import MagicMock, patch

import pytest

from screentracker_host.input_injector import InputInjector


@pytest.fixture
def injector():
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller") as mock_keyboard_cls:
        mock_mouse = MagicMock()
        mock_keyboard = MagicMock()
        mock_mouse_cls.return_value = mock_mouse
        mock_keyboard_cls.return_value = mock_keyboard
        instance = InputInjector(screen_size=(1920, 1080))
        yield instance, mock_mouse, mock_keyboard


def test_pointer_down_moves_then_presses(injector):
    instance, mock_mouse, _ = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    assert mock_mouse.position == (960, 540)
    mock_mouse.press.assert_called_once()


def test_pointer_down_right_button_presses_right(injector):
    from pynput.mouse import Button

    instance, mock_mouse, _ = injector

    instance.handle_message({"type": "pointer-down", "x": 0.0, "y": 0.0, "button": "right"})

    mock_mouse.press.assert_called_once_with(Button.right)


def test_pointer_up_releases(injector):
    from pynput.mouse import Button

    instance, mock_mouse, _ = injector

    instance.handle_message({"type": "pointer-up", "x": 0.25, "y": 0.75, "button": "left"})

    mock_mouse.release.assert_called_once_with(Button.left)
    assert mock_mouse.position == (480, 810)


def test_pointer_move_only_repositions(injector):
    instance, mock_mouse, _ = injector

    instance.handle_message({"type": "pointer-move", "x": 0.1, "y": 0.9})

    assert mock_mouse.position == (192, 972)
    mock_mouse.press.assert_not_called()
    mock_mouse.release.assert_not_called()


def test_wheel_scrolls(injector):
    instance, mock_mouse, _ = injector

    instance.handle_message({"type": "wheel", "deltaX": 0, "deltaY": 200})

    mock_mouse.scroll.assert_called_once_with(0, -2)


def test_key_down_presses_resolved_key(injector):
    from pynput.keyboard import Key

    instance, _, mock_keyboard = injector

    instance.handle_message({"type": "key-down", "key": "Enter"})

    mock_keyboard.press.assert_called_once_with(Key.enter)


def test_key_up_releases_resolved_key(injector):
    instance, _, mock_keyboard = injector

    instance.handle_message({"type": "key-up", "key": "a"})

    mock_keyboard.release.assert_called_once_with("a")


def test_unknown_message_type_is_ignored(injector):
    instance, mock_mouse, mock_keyboard = injector

    instance.handle_message({"type": "not-a-real-type"})

    mock_mouse.press.assert_not_called()
    mock_keyboard.press.assert_not_called()


def test_exception_during_dispatch_is_caught_and_warned_once(injector, capsys):
    instance, mock_mouse, _ = injector
    mock_mouse.press.side_effect = RuntimeError("boom")

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    captured = capsys.readouterr()
    assert captured.out.count("Accessibility") == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd host-app && venv\Scripts\python.exe -m pytest tests/test_input_injector.py -v`
Expected: FAIL — `ImportError: cannot import name 'InputInjector'`

- [ ] **Step 4: Write minimal implementation**

`host-app/screentracker_host/input_injector.py`'nin başına importları ekle, sonuna `InputInjector`'ı ekle:

```python
from pynput import keyboard, mouse
from pynput.keyboard import Key
from pynput.mouse import Button

# ... (KEY_MAP, clamp_unit, normalize_to_pixels, wheel_delta_to_scroll_units, resolve_key — Task 2'den aynen kalır)

_BUTTON_MAP: dict[str, Button] = {"left": Button.left, "right": Button.right}


class InputInjector:
    """Translates DataChannel input messages into OS-level events via pynput.
    Never raises: a bad message or a permissions error (e.g. missing macOS
    Accessibility access) is caught and logged once, not left to crash the
    host app's main loop."""

    def __init__(self, screen_size: tuple[int, int]) -> None:
        self._screen_width, self._screen_height = screen_size
        self._mouse = mouse.Controller()
        self._keyboard = keyboard.Controller()
        self._warned = False

    def handle_message(self, message: dict) -> None:
        try:
            self._dispatch(message)
        except Exception:
            if not self._warned:
                print(
                    "Input control failed to inject an event. On macOS this usually "
                    "means Accessibility permission hasn't been granted — see "
                    "System Settings > Privacy & Security > Accessibility."
                )
                self._warned = True

    def _dispatch(self, message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == "pointer-down":
            self._move(message["x"], message["y"])
            self._mouse.press(_BUTTON_MAP[message.get("button", "left")])
        elif msg_type == "pointer-move":
            self._move(message["x"], message["y"])
        elif msg_type == "pointer-up":
            self._move(message["x"], message["y"])
            self._mouse.release(_BUTTON_MAP[message.get("button", "left")])
        elif msg_type == "wheel":
            dx, dy = wheel_delta_to_scroll_units(message.get("deltaX", 0), message.get("deltaY", 0))
            self._mouse.scroll(dx, dy)
        elif msg_type == "key-down":
            self._keyboard.press(resolve_key(message["key"]))
        elif msg_type == "key-up":
            self._keyboard.release(resolve_key(message["key"]))

    def _move(self, x: float, y: float) -> None:
        self._mouse.position = normalize_to_pixels(x, y, self._screen_width, self._screen_height)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd host-app && venv\Scripts\python.exe -m pytest tests/test_input_injector.py -v`
Expected: tüm testler PASS

- [ ] **Step 6: Run full host-app suite**

Run: `cd host-app && venv\Scripts\python.exe -m pytest -q`
Expected: tüm testler PASS (mevcutlar + yeni)

- [ ] **Step 7: Commit**

```bash
git add host-app/screentracker_host/input_injector.py host-app/requirements.txt host-app/tests/test_input_injector.py
git commit -m "feat: add InputInjector wrapping pynput for mouse/keyboard/scroll"
```

---

## Task 4: Host — DataChannel oluşturma ve mesaj yönlendirme

**Files:**
- Modify: `host-app/screentracker_host/webrtc_peer.py`
- Test: `host-app/tests/test_webrtc_peer.py`

**Interfaces:**
- Consumes: `InputInjector` (Task 3), `get_monitor_size` (Task 1)
- Produces: `HostPeerConnection.__init__(self, screen_size: tuple[int, int] | None = None)` — geriye dönük uyumlu (parametre opsiyonel, `main.py`'deki `HostPeerConnection()` çağrısı değişmeden çalışır); `self._input_channel: RTCDataChannel` (label `"input"`)

- [ ] **Step 1: Write the failing tests**

`host-app/tests/test_webrtc_peer.py`'nin başındaki `from unittest.mock import AsyncMock` satırını şu şekilde değiştir:

```python
from unittest.mock import AsyncMock, MagicMock
```

ve importların başına ekle:

```python
import json
```

Dosyanın sonuna ekle:

```python
def test_host_peer_connection_creates_labeled_input_data_channel(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))

    assert peer._input_channel.label == "input"


def test_input_channel_message_is_forwarded_to_injector(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    payload = {"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"}
    peer._input_channel.emit("message", json.dumps(payload))

    fake_injector.handle_message.assert_called_once_with(payload)


def test_malformed_input_channel_message_is_dropped(monkeypatch):
    fake_injector = MagicMock()
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector", lambda screen_size: fake_injector
    )

    peer = HostPeerConnection(screen_size=(1920, 1080))
    peer._input_channel.emit("message", "not valid json")

    fake_injector.handle_message.assert_not_called()


def test_host_peer_connection_defaults_screen_size_from_monitor(monkeypatch):
    fake_injector = MagicMock()
    captured_sizes = []
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.InputInjector",
        lambda screen_size: captured_sizes.append(screen_size) or fake_injector,
    )
    monkeypatch.setattr(
        "screentracker_host.webrtc_peer.get_monitor_size", lambda: (2560, 1440)
    )

    HostPeerConnection()

    assert captured_sizes == [(2560, 1440)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd host-app && venv\Scripts\python.exe -m pytest tests/test_webrtc_peer.py -v`
Expected: FAIL — `AttributeError: 'HostPeerConnection' object has no attribute '_input_channel'` (veya `TypeError: HostPeerConnection() takes no arguments` ilk testte)

- [ ] **Step 3: Write minimal implementation**

`host-app/screentracker_host/webrtc_peer.py`'nin başındaki importlara ekle:

```python
import json
```

`from screentracker_host.capture import capture_frame` satırını şu şekilde genişlet:

```python
from screentracker_host.capture import capture_frame, get_monitor_size
from screentracker_host.input_injector import InputInjector
```

`HostPeerConnection.__init__`'i şu şekilde değiştir:

```python
class HostPeerConnection:
    def __init__(self, screen_size: tuple[int, int] | None = None) -> None:
        self._pc = RTCPeerConnection(RTCConfiguration(iceServers=build_ice_servers()))
        self._pc.addTrack(ScreenCaptureTrack())

        self._input_injector = InputInjector(screen_size or get_monitor_size())
        self._input_channel = self._pc.createDataChannel("input")

        @self._input_channel.on("message")
        def _on_input_message(message: str) -> None:
            try:
                payload = json.loads(message)
            except (ValueError, TypeError):
                return
            self._input_injector.handle_message(payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd host-app && venv\Scripts\python.exe -m pytest tests/test_webrtc_peer.py -v`
Expected: tüm testler PASS

- [ ] **Step 5: Run full host-app suite**

Run: `cd host-app && venv\Scripts\python.exe -m pytest -q`
Expected: tüm testler PASS

- [ ] **Step 6: Commit**

```bash
git add host-app/screentracker_host/webrtc_peer.py host-app/tests/test_webrtc_peer.py
git commit -m "feat: wire an input DataChannel into HostPeerConnection"
```

---

## Task 5: Viewer — `useInputControl` gesture yakalama hook'u

**Files:**
- Create: `viewer-app/src/hooks/useInputControl.ts`
- Test: `viewer-app/tests/useInputControl.test.ts`

**Interfaces:**
- Consumes: —
- Produces: `useInputControl(options: { videoRef: RefObject<HTMLVideoElement>; channel: RTCDataChannel | null }) -> void`

- [ ] **Step 1: Write the failing tests**

`viewer-app/tests/useInputControl.test.ts` (yeni dosya):

```typescript
import { renderHook } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useInputControl } from "../src/hooks/useInputControl";

function setupVideo(rect: Partial<DOMRect> = {}) {
  const video = document.createElement("video");
  document.body.appendChild(video);
  vi.spyOn(video, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    width: 200,
    height: 100,
    right: 200,
    bottom: 100,
    x: 0,
    y: 0,
    toJSON: () => ({}),
    ...rect,
  } as DOMRect);
  return video;
}

function fakeChannel(readyState: RTCDataChannelState = "open") {
  return { readyState, send: vi.fn() } as unknown as RTCDataChannel;
}

function pointerEvent(type: string, clientX: number, clientY: number) {
  return new PointerEvent(type, { clientX, clientY, bubbles: true });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
});

describe("useInputControl", () => {
  it("sends a left click (down immediately followed by up) on a quick tap", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - assigning a ref's current for the test
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(channel.send).toHaveBeenCalledTimes(2);
    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "pointer-down",
      x: 0.5,
      y: 0.5,
      button: "left",
    });
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "pointer-up",
      x: 0.5,
      y: 0.5,
      button: "left",
    });
  });

  it("sends a right click after the long-press threshold elapses", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    vi.advanceTimersByTime(500);

    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "pointer-down",
      x: 0.5,
      y: 0.5,
      button: "right",
    });

    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "pointer-up",
      x: 0.5,
      y: 0.5,
      button: "right",
    });
  });

  it("starts a left-button drag once movement exceeds the threshold before the long-press fires", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointermove", 130, 50));

    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "pointer-down",
      x: 0.5,
      y: 0.5,
      button: "left",
    });
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "pointer-move",
      x: 0.65,
      y: 0.5,
    });

    // The long-press timer must have been cancelled by the drag — advancing
    // past the threshold must NOT also fire a right-click pointer-down.
    vi.advanceTimersByTime(500);
    expect(channel.send).toHaveBeenCalledTimes(2);
  });

  it("drops events silently when the channel is not open", () => {
    const video = setupVideo();
    const channel = fakeChannel("connecting");
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(pointerEvent("pointerdown", 100, 50));
    video.dispatchEvent(pointerEvent("pointerup", 100, 50));

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("relays wheel deltas", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    video.dispatchEvent(
      new WheelEvent("wheel", { deltaX: 10, deltaY: 20, bubbles: true })
    );

    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "wheel",
      deltaX: 10,
      deltaY: 20,
    });
  });

  it("relays keydown and keyup key values", () => {
    const video = setupVideo();
    const channel = fakeChannel();
    const videoRef = createRef<HTMLVideoElement>();
    // @ts-expect-error - test assignment
    videoRef.current = video;

    renderHook(() => useInputControl({ videoRef, channel }));

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    window.dispatchEvent(new KeyboardEvent("keyup", { key: "a" }));

    expect(JSON.parse((channel.send as any).mock.calls[0][0])).toEqual({
      type: "key-down",
      key: "a",
    });
    expect(JSON.parse((channel.send as any).mock.calls[1][0])).toEqual({
      type: "key-up",
      key: "a",
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd viewer-app && npx vitest run tests/useInputControl.test.ts`
Expected: FAIL — `Failed to resolve import "../src/hooks/useInputControl"`

- [ ] **Step 3: Write minimal implementation**

`viewer-app/src/hooks/useInputControl.ts` (yeni dosya):

```typescript
import { useEffect, type RefObject } from "react";

const LONG_PRESS_MS = 500;
const DRAG_THRESHOLD_PX = 20;

interface UseInputControlOptions {
  videoRef: RefObject<HTMLVideoElement | null>;
  channel: RTCDataChannel | null;
}

type Button = "left" | "right";

export function useInputControl({ videoRef, channel }: UseInputControlOptions): void {
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    function send(message: Record<string, unknown>) {
      if (channel?.readyState === "open") {
        channel.send(JSON.stringify(message));
      }
    }

    function toNormalized(clientX: number, clientY: number): { x: number; y: number } {
      const rect = video!.getBoundingClientRect();
      return {
        x: (clientX - rect.left) / rect.width,
        y: (clientY - rect.top) / rect.height,
      };
    }

    let longPressTimer: ReturnType<typeof setTimeout> | null = null;
    let downAt: { x: number; y: number; clientX: number; clientY: number } | null = null;
    let activeButton: Button | null = null;

    function handlePointerDown(event: PointerEvent) {
      event.preventDefault();
      // Without capture, releasing the pointer outside the video's bounds
      // (e.g. dragging off the edge) never fires pointerup on this element,
      // leaving the mouse button stuck "down" on the host forever. Optional
      // chaining because jsdom's test environment doesn't implement this.
      video!.setPointerCapture?.(event.pointerId);
      const { x, y } = toNormalized(event.clientX, event.clientY);
      downAt = { x, y, clientX: event.clientX, clientY: event.clientY };
      activeButton = null;
      longPressTimer = setTimeout(() => {
        if (!downAt) return;
        activeButton = "right";
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "right" });
      }, LONG_PRESS_MS);
    }

    function handlePointerMove(event: PointerEvent) {
      if (!downAt) return;
      const { x, y } = toNormalized(event.clientX, event.clientY);

      if (activeButton === null) {
        const dx = event.clientX - downAt.clientX;
        const dy = event.clientY - downAt.clientY;
        if (Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;

        if (longPressTimer) clearTimeout(longPressTimer);
        activeButton = "left";
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "left" });
      }

      send({ type: "pointer-move", x, y });
    }

    function handlePointerUp(event: PointerEvent) {
      video!.releasePointerCapture?.(event.pointerId);
      if (longPressTimer) clearTimeout(longPressTimer);
      if (!downAt) return;
      const { x, y } = toNormalized(event.clientX, event.clientY);

      if (activeButton === null) {
        // Never moved past the drag threshold or the long-press timer: a
        // plain tap. Send a synthetic down+up pair at the same spot.
        send({ type: "pointer-down", x: downAt.x, y: downAt.y, button: "left" });
        send({ type: "pointer-up", x: downAt.x, y: downAt.y, button: "left" });
      } else {
        send({ type: "pointer-up", x, y, button: activeButton });
      }

      downAt = null;
      activeButton = null;
    }

    function handleWheel(event: WheelEvent) {
      event.preventDefault();
      send({ type: "wheel", deltaX: event.deltaX, deltaY: event.deltaY });
    }

    function handleKeyDown(event: KeyboardEvent) {
      send({ type: "key-down", key: event.key });
    }

    function handleKeyUp(event: KeyboardEvent) {
      send({ type: "key-up", key: event.key });
    }

    video.addEventListener("pointerdown", handlePointerDown);
    video.addEventListener("pointermove", handlePointerMove);
    video.addEventListener("pointerup", handlePointerUp);
    video.addEventListener("wheel", handleWheel);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      if (longPressTimer) clearTimeout(longPressTimer);
      video.removeEventListener("pointerdown", handlePointerDown);
      video.removeEventListener("pointermove", handlePointerMove);
      video.removeEventListener("pointerup", handlePointerUp);
      video.removeEventListener("wheel", handleWheel);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [videoRef, channel]);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd viewer-app && npx vitest run tests/useInputControl.test.ts`
Expected: tüm testler PASS

- [ ] **Step 5: Run full viewer-app suite**

Run: `cd viewer-app && npx vitest run`
Expected: tüm testler PASS (mevcutlar + yeni)

- [ ] **Step 6: Commit**

```bash
git add viewer-app/src/hooks/useInputControl.ts viewer-app/tests/useInputControl.test.ts
git commit -m "feat: add useInputControl hook for pointer/wheel/keyboard capture"
```

---

## Task 6: Viewer — DataChannel'ı bağlama ve `VideoPlayer`'a kablolama

**Files:**
- Modify: `viewer-app/src/hooks/useWebRTCViewer.ts`
- Modify: `viewer-app/src/components/VideoPlayer.tsx`
- Modify: `viewer-app/src/components/VideoPlayer.module.css`
- Modify: `viewer-app/src/App.tsx`

**Interfaces:**
- Consumes: `useInputControl` (Task 5)
- Produces: `useWebRTCViewer(...)` artık `inputChannel: RTCDataChannel | null` da döndürür; `VideoPlayer` yeni bir `inputChannel` prop'u kabul eder

Not: `useWebRTCViewer`'ın `ondatachannel` kablolaması, tarayıcının native `RTCPeerConnection`'ına bağlı — bu dosyadaki `handleOffer`/`handleRemoteIceCandidate` gibi mevcut fonksiyonlar da aynı sebeple (jsdom'da gerçek WebRTC yok) otomatik test edilmiyor; bu değişiklik de aynı kapsamda, manuel E2E ile doğrulanacak (bkz. Task 7).

- [ ] **Step 1: `useWebRTCViewer.ts`'yi genişlet**

`viewer-app/src/hooks/useWebRTCViewer.ts` içinde `UseWebRTCViewerResult` interface'ine ekle:

```typescript
interface UseWebRTCViewerResult {
  remoteStream: MediaStream | null;
  handleOffer: (sdp: string) => Promise<string>;
  handleRemoteIceCandidate: (candidate: RTCIceCandidateInit) => Promise<void>;
  inputChannel: RTCDataChannel | null;
}
```

`useWebRTCViewer` fonksiyonu içine bir state ekle ve `useEffect`'i genişlet:

```typescript
export function useWebRTCViewer({
  onIceCandidate,
}: UseWebRTCViewerOptions): UseWebRTCViewerResult {
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [inputChannel, setInputChannel] = useState<RTCDataChannel | null>(null);

  useEffect(() => {
    const pc = new RTCPeerConnection({ iceServers: buildIceServers() });
    pcRef.current = pc;

    pc.ontrack = (event) => setRemoteStream(event.streams[0]);
    pc.onicecandidate = (event) => {
      if (event.candidate) onIceCandidate(event.candidate);
    };
    pc.ondatachannel = (event) => setInputChannel(event.channel);

    return () => pc.close();
  }, [onIceCandidate]);

  // ... handleOffer, handleRemoteIceCandidate aynen kalır ...

  return { remoteStream, handleOffer, handleRemoteIceCandidate, inputChannel };
}
```

- [ ] **Step 2: `VideoPlayer.tsx`'i genişlet**

`viewer-app/src/components/VideoPlayer.tsx`'in tamamını değiştir:

```typescript
import { useEffect, useRef } from "react";
import { useInputControl } from "../hooks/useInputControl";
import styles from "./VideoPlayer.module.css";

interface VideoPlayerProps {
  stream: MediaStream | null;
  inputChannel: RTCDataChannel | null;
}

export function VideoPlayer({ stream, inputChannel }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  useInputControl({ videoRef, channel: inputChannel });

  if (!stream) {
    return <p className={styles.waiting}>Waiting for host to start streaming…</p>;
  }

  const inputReady = inputChannel?.readyState === "open";

  return (
    <div className={styles.wrapper}>
      <video className={styles.video} ref={videoRef} autoPlay playsInline />
      <span className={inputReady ? `${styles.inputStatus} ${styles.inputReady}` : styles.inputStatus}>
        {inputReady ? "Input active" : "Input connecting…"}
      </span>
    </div>
  );
}
```

- [ ] **Step 3: `VideoPlayer.module.css`'e stil ekle**

`viewer-app/src/components/VideoPlayer.module.css`'in tamamını şu içerikle değiştir (mevcut `.waiting` ve `.video` kuralları korunuyor, `.video`'ya `touch-action: none;` eklendi, üç yeni kural eklendi):

```css
.waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-family: var(--font-display);
  font-size: 0.9rem;
}

.wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: var(--bg);
  touch-action: none;
}

.inputStatus {
  position: absolute;
  bottom: var(--space-2);
  right: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text-secondary);
  font-family: var(--font-display);
  font-size: 12px;
}

.inputReady {
  color: var(--accent);
}
```

- [ ] **Step 4: `App.tsx`'i kabloya**

`viewer-app/src/App.tsx` içinde:

```typescript
const { remoteStream, handleOffer, handleRemoteIceCandidate, inputChannel } = useWebRTCViewer({
  onIceCandidate: handleIceCandidate,
});
```

ve

```typescript
{status === "streaming" && <VideoPlayer stream={remoteStream} inputChannel={inputChannel} />}
```

- [ ] **Step 5: Mevcut testleri güncelle**

`viewer-app/tests/VideoPlayer.test.tsx`'in tamamını şu içerikle değiştir (yeni zorunlu `inputChannel` prop'u her iki `render` çağrısına eklendi):

```typescript
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VideoPlayer } from "../src/components/VideoPlayer";

describe("VideoPlayer", () => {
  it("shows a waiting message when there is no stream", () => {
    render(<VideoPlayer stream={null} inputChannel={null} />);
    expect(screen.getByText(/waiting for host/i)).toBeInTheDocument();
  });

  it("renders a video element bound to the stream when present", () => {
    const fakeStream = {} as MediaStream;
    const { container } = render(<VideoPlayer stream={fakeStream} inputChannel={null} />);
    expect(container.querySelector("video")).not.toBeNull();
  });
});
```

- [ ] **Step 6: Build ve testleri çalıştır**

Run: `cd viewer-app && npm run build && npx vitest run`
Expected: build temiz, tüm testler PASS

- [ ] **Step 7: Commit**

```bash
git add viewer-app/src/hooks/useWebRTCViewer.ts viewer-app/src/components/VideoPlayer.tsx viewer-app/src/components/VideoPlayer.module.css viewer-app/src/App.tsx viewer-app/tests/VideoPlayer.test.tsx
git commit -m "feat: wire input DataChannel through VideoPlayer with a connection-status indicator"
```

---

## Task 7: Dokümantasyon

**Files:**
- Modify: `docs/api-spec.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes: Task 1-6'nın gerçek kodu (aspiratif değil, gerçekten yazılan mesaj alanları/tipleri belgelenir)
- Produces: —

- [ ] **Step 1: `docs/api-spec.md`'ye yeni bölüm ekle**

Dosyanın sonuna ekle:

```markdown
## Input control (WebRTC DataChannel)

Signaling server'dan tamamen bağımsız: bu mesajlar host ile viewer arasındaki
WebRTC bağlantısına eklenen `"input"` etiketli `RTCDataChannel` üzerinden,
JSON string olarak akar. Host bu kanalı offer'dan önce oluşturur (`aiortc`
`createDataChannel`), viewer `ondatachannel` event'iyle alır.

| Mesaj | Alanlar | Anlamı |
|---|---|---|
| `pointer-down` | `x, y` (0-1 normalize), `button: "left" \| "right"` | Basış başladı |
| `pointer-move` | `x, y` | Basılıyken hareket |
| `pointer-up` | `x, y`, `button` | Basış bitti |
| `wheel` | `deltaX, deltaY` | Scroll (tarayıcı `WheelEvent` değerleri, ham) |
| `key-down` | `key` (tarayıcı `KeyboardEvent.key` değeri) | Tuşa basıldı |
| `key-up` | `key` | Tuş bırakıldı |

Host, `x`/`y`'yi kendi ekran boyutuyla çarpıp gerçek piksele çevirir,
`[0, 1]` aralığına clamp'ler. Tık ile sürükleme host'ta ayrıca ayırt
edilmez — `pointer-down`/`pointer-move`/`pointer-up`'ın `pynput`
press/move/release çağrılarından kendiliğinden çıkar. Uzun basış (sağ tık),
viewer'da 500ms eşikle tespit edilip `button: "right"` olarak gönderilir.

Yetkilendirme: bu kanal, zaten kurulmuş bir WebRTC bağlantısı üzerinde —
yani zaten pairing onayından geçmiş bir cihaz için var. Ayrı bir input
onay adımı yok (bilinçli kapsam kararı, bkz. tasarım spec'i).
```

- [ ] **Step 2: `docs/architecture.md`'nin decisions log'una ekle**

Mevcut son satırdan sonra ekle:

```markdown
- **Input kontrolü ayrı bir DataChannel üzerinden, signaling protokolüne dokunmadan**: `RTCDataChannel`, mevcut offer/answer SDP değişimi içinde otomatik müzakere ediliyor — yeni bir WebSocket mesaj tipi gerekmiyor, host'un offer'ı oluşturma sırası (Faz 1'den beri değişmedi) bunu doğal olarak destekliyor.
- **Input yetkilendirmesi = mevcut device pairing onayı, ayrı bir adım yok**: ekranı görebilen bir cihaza ayrıca "kontrol edemez" demenin kendi-cihazların-arası kullanım senaryosunda pratik faydası yok; bilinçli olarak kabul edilen risk (bkz. Faz 2 tasarım spec'i, §0 Güvenlik).
```

- [ ] **Step 3: Commit**

```bash
git add docs/api-spec.md docs/architecture.md
git commit -m "docs: document the input control DataChannel protocol"
```

---

## Self-Review Notları (planı yazan ajan tarafından dolduruldu)

- **Spec kapsaması:** §0 fonksiyonel gereksinimlerin hepsi (tık→sol tık, uzun basış→sağ tık, sürükleme, scroll, klavye, koordinat eşleme) Task 2/3/5'te; §1 mimari (DataChannel, koordinat eşleme) Task 4/5/6'da; §4 hata yönetimi (DataChannel kapalı, clamp, Accessibility uyarısı, istisna yutma) Task 3/5'te; §5 test stratejisi Task 1-6'nın her birinde; §6 kapsam dışı maddelere (cursor overlay, çoklu monitör, ayrı onay, clipboard, dosya transferi) hiçbir task'ta dokunulmadı — doğrulandı.
- **Placeholder taraması:** yok — her adımda çalıştırılabilir gerçek kod var.
- **Tip tutarlılığı:** `InputInjector.__init__(screen_size: tuple[int, int])` Task 3 ve Task 4'te aynı; `useInputControl({ videoRef, channel })` Task 5 ve Task 6'da aynı; `VideoPlayer`'ın `inputChannel` prop adı Task 6'nın kendi içinde tutarlı.
