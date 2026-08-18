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
