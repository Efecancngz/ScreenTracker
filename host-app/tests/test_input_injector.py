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
