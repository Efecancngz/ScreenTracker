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
