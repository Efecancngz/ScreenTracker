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


def test_build_touch_injector_survives_attribute_error_from_missing_touch_injection_api():
    """Important #1: on a Windows build where InitializeTouchInjection
    isn't a user32.dll export (older/embedded Windows), ctypes raises
    AttributeError, not RuntimeError, the first time that attribute is
    accessed. _build_touch_injector() must swallow that too and fall
    back to pynput rather than let it propagate out of __init__ and
    have HostPeerConnection kill ALL input control."""
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller"), \
         patch("screentracker_host.input_injector.sys.platform", "win32"), \
         patch(
             "screentracker_host.touch_injector.TouchInjector",
             side_effect=AttributeError(
                 "function 'InitializeTouchInjection' not found"
             ),
         ):
        mock_mouse = MagicMock()
        mock_mouse_cls.return_value = mock_mouse

        instance = InputInjector(screen_size=(1920, 1080))
        instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

        assert instance._touch_injector is None
        assert mock_mouse.position == (960, 540)
        mock_mouse.press.assert_called_once()


def test_pointer_up_clears_active_button_even_when_touch_injector_up_raises(injector):
    """Important #2: if TouchInjector.up() raises (a real, designed-for
    failure mode -- InjectTouchInput can return false), _active_button
    must still be cleared, otherwise every subsequent bare pointer-move
    keeps trying to route through the (possibly broken) touch injector
    forever and never falls back to pynput."""
    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    with patch.object(instance._touch_injector, "up", side_effect=RuntimeError("boom")):
        instance.handle_message({"type": "pointer-up", "x": 0.25, "y": 0.75, "button": "left"})

    assert instance._active_button is None

    call_count_before = mock_user32.InjectTouchInput.call_count
    instance.handle_message({"type": "pointer-move", "x": 0.1, "y": 0.1})
    assert mock_user32.InjectTouchInput.call_count == call_count_before
    assert mock_mouse.position == (192, 108)


@pytest.mark.asyncio
async def test_left_pointer_down_schedules_touch_keepalive_when_loop_available(injector):
    """Confirmed via real on-device testing: an injected touch contact
    times out (GetLastError=1460 then 87 on every subsequent call) if
    left idle for too long between injections -- observed with an
    ~875ms gap between a pointer-down and its first pointer-move. A
    keepalive timer must be scheduled on left pointer-down so the
    contact never goes stale even if the client sends no further
    pointer-move for a while (a deliberate slow drag, or a brief pause
    mid-drag)."""
    instance, _, _, _ = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    assert instance._touch_keepalive_handle is not None


def test_touch_keepalive_tick_reinjects_last_known_position(injector):
    from screentracker_host.touch_injector import POINTER_FLAG_INCONTACT, POINTER_FLAG_INRANGE, POINTER_FLAG_UPDATE

    instance, _, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    call_count_before = mock_user32.InjectTouchInput.call_count

    instance._touch_keepalive_tick()

    assert mock_user32.InjectTouchInput.call_count == call_count_before + 1
    contact = _touch_contact(mock_user32)
    assert contact.pointerInfo.pointerFlags == (
        POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
    )
    assert contact.pointerInfo.ptPixelLocation.x == 960
    assert contact.pointerInfo.ptPixelLocation.y == 540


def test_touch_keepalive_tick_uses_latest_position_after_a_real_move(injector):
    instance, _, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    instance.handle_message({"type": "pointer-move", "x": 0.1, "y": 0.9})

    instance._touch_keepalive_tick()

    contact = _touch_contact(mock_user32)
    assert contact.pointerInfo.ptPixelLocation.x == 192
    assert contact.pointerInfo.ptPixelLocation.y == 972


def test_touch_keepalive_tick_is_a_no_op_after_pointer_up(injector):
    instance, _, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    instance.handle_message({"type": "pointer-up", "x": 0.5, "y": 0.5, "button": "left"})
    call_count_before = mock_user32.InjectTouchInput.call_count

    instance._touch_keepalive_tick()

    assert mock_user32.InjectTouchInput.call_count == call_count_before


@pytest.mark.asyncio
async def test_pointer_up_cancels_pending_touch_keepalive(injector):
    instance, _, _, _ = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    assert instance._touch_keepalive_handle is not None

    instance.handle_message({"type": "pointer-up", "x": 0.5, "y": 0.5, "button": "left"})

    assert instance._touch_keepalive_handle is None


@pytest.mark.asyncio
async def test_touch_keepalive_fires_on_its_own_via_the_real_event_loop_timer(injector):
    """Proves the scheduled callback actually re-arms itself and
    executes through a live event loop -- not just that a handle gets
    created (test_left_pointer_down_schedules_touch_keepalive_when_loop_available)
    or that the tick method works when called directly
    (test_touch_keepalive_tick_reinjects_last_known_position)."""
    import asyncio

    from screentracker_host.input_injector import TOUCH_KEEPALIVE_INTERVAL_SECONDS

    instance, _, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    call_count_before = mock_user32.InjectTouchInput.call_count

    await asyncio.sleep(TOUCH_KEEPALIVE_INTERVAL_SECONDS * 2)

    assert mock_user32.InjectTouchInput.call_count > call_count_before


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
