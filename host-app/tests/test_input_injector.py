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
    """Default fixture: sys.platform is win32, so left-button pointer
    events route through a MouseInjector. Use `injector_no_mouse_injector`
    below for the pynput-fallback cases."""
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller") as mock_keyboard_cls, \
         patch("screentracker_host.input_injector.sys.platform", "win32"), \
         patch("screentracker_host.mouse_injector.user32") as mock_user32:
        mock_user32.SendInput.return_value = 1
        mock_user32.GetSystemMetrics.side_effect = lambda metric: {
            76: 0, 77: 0, 78: 1920, 79: 1080,
        }[metric]
        mock_mouse = MagicMock()
        mock_keyboard = MagicMock()
        mock_mouse_cls.return_value = mock_mouse
        mock_keyboard_cls.return_value = mock_keyboard
        instance = InputInjector(screen_size=(1920, 1080))
        yield instance, mock_mouse, mock_keyboard, mock_user32


@pytest.fixture
def injector_no_mouse_injector():
    """Fixture for the pynput-fallback path: sys.platform isn't win32,
    so InputInjector never attempts to construct a MouseInjector at
    all, and every pointer path (left AND right) uses pynput -- this
    is also representative of "MouseInjector construction failed"."""
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller") as mock_keyboard_cls, \
         patch("screentracker_host.input_injector.sys.platform", "linux"):
        mock_mouse = MagicMock()
        mock_keyboard = MagicMock()
        mock_mouse_cls.return_value = mock_mouse
        mock_keyboard_cls.return_value = mock_keyboard
        instance = InputInjector(screen_size=(1920, 1080))
        yield instance, mock_mouse, mock_keyboard


def _last_mouse_input(mock_user32):
    """Reads back the INPUT struct most recently passed to the mocked
    SendInput call."""
    return mock_user32.SendInput.call_args[0][1].contents


def test_left_pointer_down_goes_through_mouse_injector(injector):
    from screentracker_host.mouse_injector import MOUSEEVENTF_LEFTDOWN

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    inp = _last_mouse_input(mock_user32)
    assert inp.mi.dwFlags == MOUSEEVENTF_LEFTDOWN
    mock_mouse.press.assert_not_called()


def test_left_pointer_move_goes_through_mouse_injector_after_left_down(injector):
    from screentracker_host.mouse_injector import MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_MOVE, MOUSEEVENTF_VIRTUALDESK

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    instance.handle_message({"type": "pointer-move", "x": 0.1, "y": 0.9})

    inp = _last_mouse_input(mock_user32)
    assert inp.mi.dwFlags == (MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK)
    mock_mouse.press.assert_not_called()


def test_left_pointer_up_goes_through_mouse_injector_and_clears_active_button(injector):
    from screentracker_host.mouse_injector import MOUSEEVENTF_LEFTUP

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})
    instance.handle_message({"type": "pointer-up", "x": 0.25, "y": 0.75, "button": "left"})

    inp = _last_mouse_input(mock_user32)
    assert inp.mi.dwFlags == MOUSEEVENTF_LEFTUP
    mock_mouse.release.assert_not_called()

    # A pointer-move after pointer-up (no active gesture) falls back to
    # the pynput path, proving _active_button was actually cleared.
    call_count_before = mock_user32.SendInput.call_count
    instance.handle_message({"type": "pointer-move", "x": 0.1, "y": 0.1})
    assert mock_user32.SendInput.call_count == call_count_before
    assert mock_mouse.position == (192, 108)


def test_right_pointer_down_still_uses_pynput_even_with_mouse_injector_available(injector):
    from pynput.mouse import Button

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.0, "y": 0.0, "button": "right"})

    mock_mouse.press.assert_called_once_with(Button.right)
    assert mock_mouse.position == (0, 0)
    mock_user32.SendInput.assert_not_called()


def test_right_pointer_move_still_uses_pynput_after_right_down(injector):
    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.0, "y": 0.0, "button": "right"})
    instance.handle_message({"type": "pointer-move", "x": 0.5, "y": 0.5})

    assert mock_mouse.position == (960, 540)
    mock_user32.SendInput.assert_not_called()


def test_right_pointer_up_still_uses_pynput(injector):
    from pynput.mouse import Button

    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.0, "y": 0.0, "button": "right"})
    instance.handle_message({"type": "pointer-up", "x": 0.25, "y": 0.75, "button": "right"})

    mock_mouse.release.assert_called_once_with(Button.right)
    assert mock_mouse.position == (480, 810)
    mock_user32.SendInput.assert_not_called()


def test_wheel_still_scrolls_via_pynput(injector):
    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "wheel", "deltaX": 0, "deltaY": 200})

    mock_mouse.scroll.assert_called_once_with(0, -2)
    mock_user32.SendInput.assert_not_called()


def test_key_down_still_presses_via_pynput(injector):
    from pynput.keyboard import Key

    instance, _, mock_keyboard, mock_user32 = injector

    instance.handle_message({"type": "key-down", "key": "Enter"})

    mock_keyboard.press.assert_called_once_with(Key.enter)
    mock_user32.SendInput.assert_not_called()


def test_key_up_still_releases_via_pynput(injector):
    instance, _, mock_keyboard, mock_user32 = injector

    instance.handle_message({"type": "key-up", "key": "a"})

    mock_keyboard.release.assert_called_once_with("a")
    mock_user32.SendInput.assert_not_called()


def test_unknown_message_type_is_ignored(injector):
    instance, mock_mouse, mock_keyboard, mock_user32 = injector

    instance.handle_message({"type": "not-a-real-type"})

    mock_mouse.press.assert_not_called()
    mock_keyboard.press.assert_not_called()
    mock_user32.SendInput.assert_not_called()


def test_exception_during_dispatch_is_caught_and_warned_once(injector, capsys):
    instance, mock_mouse, _, _ = injector
    mock_mouse.press.side_effect = RuntimeError("boom")

    # Use the right button so this exercises the pynput press() path
    # (left goes through MouseInjector, which doesn't call mock_mouse.press).
    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "right"})
    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "right"})

    captured = capsys.readouterr()
    assert captured.out.count("Input control failed to inject an event") == 1


def test_left_pointer_down_falls_back_to_pynput_when_mouse_injector_construction_fails():
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller"), \
         patch("screentracker_host.input_injector.sys.platform", "win32"), \
         patch(
             "screentracker_host.input_injector.InputInjector._build_mouse_injector",
             return_value=None,
         ):
        mock_mouse = MagicMock()
        mock_mouse_cls.return_value = mock_mouse

        instance = InputInjector(screen_size=(1920, 1080))
        instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

        assert mock_mouse.position == (960, 540)
        mock_mouse.press.assert_called_once()


def test_left_pointer_down_uses_pynput_on_non_windows(injector_no_mouse_injector):
    instance, mock_mouse, _ = injector_no_mouse_injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    assert mock_mouse.position == (960, 540)
    mock_mouse.press.assert_called_once()


def test_build_mouse_injector_survives_exceptions_from_construction():
    """_build_mouse_injector() must swallow any construction error (a
    missing user32.dll export on some unusual Windows build, etc.) and
    fall back to pynput rather than let it propagate out of __init__
    and have HostPeerConnection kill ALL input control."""
    with patch("screentracker_host.input_injector.mouse.Controller") as mock_mouse_cls, \
         patch("screentracker_host.input_injector.keyboard.Controller"), \
         patch("screentracker_host.input_injector.sys.platform", "win32"), \
         patch(
             "screentracker_host.mouse_injector.MouseInjector",
             side_effect=OSError("user32.dll not usable"),
         ):
        mock_mouse = MagicMock()
        mock_mouse_cls.return_value = mock_mouse

        instance = InputInjector(screen_size=(1920, 1080))
        instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

        assert instance._mouse_injector is None
        assert mock_mouse.position == (960, 540)
        mock_mouse.press.assert_called_once()


def test_pointer_up_clears_active_button_even_when_mouse_injector_up_raises(injector):
    """If MouseInjector.up() raises (SendInput can fail), _active_button
    must still be cleared, otherwise every subsequent bare pointer-move
    keeps trying to route through the (possibly broken) mouse injector
    forever and never falls back to pynput."""
    instance, mock_mouse, _, mock_user32 = injector

    instance.handle_message({"type": "pointer-down", "x": 0.5, "y": 0.5, "button": "left"})

    with patch.object(instance._mouse_injector, "up", side_effect=RuntimeError("boom")):
        instance.handle_message({"type": "pointer-up", "x": 0.25, "y": 0.75, "button": "left"})

    assert instance._active_button is None

    call_count_before = mock_user32.SendInput.call_count
    instance.handle_message({"type": "pointer-move", "x": 0.1, "y": 0.1})
    assert mock_user32.SendInput.call_count == call_count_before
    assert mock_mouse.position == (192, 108)


def test_host_peer_connection_survives_mouse_injector_construction_failure_message():
    """The fallback message is printed (not silently swallowed) so a
    developer reading host app logs can see why drag-and-drop won't
    work correctly on this host."""
    with patch("screentracker_host.input_injector.mouse.Controller"), \
         patch("screentracker_host.input_injector.keyboard.Controller"), \
         patch("screentracker_host.input_injector.sys.platform", "win32"), \
         patch(
             "screentracker_host.mouse_injector.MouseInjector",
             side_effect=OSError("user32.dll not usable"),
         ), \
         patch("builtins.print") as mock_print:
        InputInjector(screen_size=(1920, 1080))

        assert any(
            "Mouse injection unavailable" in str(call.args[0])
            for call in mock_print.call_args_list
        )


def test_close_is_safe_to_call_even_without_an_active_gesture(injector):
    """close() must not raise regardless of gesture state -- it's called
    unconditionally by HostPeerConnection.close()."""
    instance, _, _, _ = injector

    instance.close()


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
