from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_user32():
    with patch("screentracker_host.mouse_injector.user32") as mock:
        # A fixed, simple virtual desktop so absolute-coordinate math in
        # assertions is predictable: origin (0,0), size 1920x1080.
        mock.GetSystemMetrics.side_effect = lambda metric: {
            76: 0, 77: 0, 78: 1920, 79: 1080,
        }[metric]
        mock.SendInput.return_value = 1
        yield mock


def _last_input(mock_user32):
    """Reads back the INPUT struct most recently passed to the mocked
    SendInput call."""
    return mock_user32.SendInput.call_args[0][1].contents


def test_move_sends_an_absolute_move_input(mock_user32):
    from screentracker_host.mouse_injector import (
        MOUSEEVENTF_ABSOLUTE,
        MOUSEEVENTF_MOVE,
        MOUSEEVENTF_VIRTUALDESK,
        MouseInjector,
    )

    MouseInjector().move(960, 540)

    inp = _last_input(mock_user32)
    assert inp.mi.dwFlags == (MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK)
    # round(960 * 65535 / 1919) and round(540 * 65535 / 1079) -- the
    # virtual-desktop dimension minus 1, per SendInput's documented
    # absolute-coordinate convention.
    assert inp.mi.dx == 32785
    assert inp.mi.dy == 32798


def test_down_moves_to_the_position_then_presses_left_button(mock_user32):
    from screentracker_host.mouse_injector import MOUSEEVENTF_LEFTDOWN, MouseInjector

    MouseInjector().down(960, 540)

    assert mock_user32.SendInput.call_count == 2
    move_call, press_call = mock_user32.SendInput.call_args_list
    move_inp = move_call[0][1].contents
    press_inp = press_call[0][1].contents
    assert move_inp.mi.dx > 0  # the move happened first
    assert press_inp.mi.dwFlags == MOUSEEVENTF_LEFTDOWN


def test_up_moves_to_the_position_then_releases_left_button(mock_user32):
    from screentracker_host.mouse_injector import MOUSEEVENTF_LEFTUP, MouseInjector

    MouseInjector().up(960, 540)

    assert mock_user32.SendInput.call_count == 2
    _, release_call = mock_user32.SendInput.call_args_list
    release_inp = release_call[0][1].contents
    assert release_inp.mi.dwFlags == MOUSEEVENTF_LEFTUP


def test_a_failed_send_input_call_raises(mock_user32):
    from screentracker_host.mouse_injector import MouseInjector

    mock_user32.SendInput.return_value = 0

    with pytest.raises(RuntimeError):
        MouseInjector().move(960, 540)
