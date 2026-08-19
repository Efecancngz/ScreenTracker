import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Touch Injection API is Windows-only"
)

from unittest.mock import patch

from screentracker_host.touch_injector import (
    POINTER_FLAG_DOWN,
    POINTER_FLAG_INCONTACT,
    POINTER_FLAG_INRANGE,
    POINTER_FLAG_UP,
    POINTER_FLAG_UPDATE,
    TOUCH_FEEDBACK_DEFAULT,
    TouchInjector,
)


@pytest.fixture
def mock_user32():
    with patch("screentracker_host.touch_injector.user32") as mock:
        mock.InitializeTouchInjection.return_value = True
        mock.InjectTouchInput.return_value = True
        yield mock


def test_init_calls_initialize_touch_injection_with_one_contact(mock_user32):
    TouchInjector()

    mock_user32.InitializeTouchInjection.assert_called_once_with(1, TOUCH_FEEDBACK_DEFAULT)


def test_init_raises_runtime_error_when_initialize_fails(mock_user32):
    mock_user32.InitializeTouchInjection.return_value = False

    with pytest.raises(RuntimeError, match="InitializeTouchInjection failed"):
        TouchInjector()


def test_down_injects_down_flags_at_the_given_pixel(mock_user32):
    injector = TouchInjector()

    injector.down(100, 200)

    count, contact_ptr = mock_user32.InjectTouchInput.call_args[0]
    contact = contact_ptr.contents
    assert count == 1
    assert contact.pointerInfo.pointerFlags == (
        POINTER_FLAG_DOWN | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
    )
    assert contact.pointerInfo.ptPixelLocation.x == 100
    assert contact.pointerInfo.ptPixelLocation.y == 200


def test_move_injects_update_flags_at_the_given_pixel(mock_user32):
    injector = TouchInjector()

    injector.move(50, 60)

    contact = mock_user32.InjectTouchInput.call_args[0][1].contents
    assert contact.pointerInfo.pointerFlags == (
        POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
    )
    assert contact.pointerInfo.ptPixelLocation.x == 50
    assert contact.pointerInfo.ptPixelLocation.y == 60


def test_up_injects_up_flags_at_the_given_pixel(mock_user32):
    injector = TouchInjector()

    injector.up(10, 20)

    contact = mock_user32.InjectTouchInput.call_args[0][1].contents
    assert contact.pointerInfo.pointerFlags == POINTER_FLAG_UP
    assert contact.pointerInfo.ptPixelLocation.x == 10
    assert contact.pointerInfo.ptPixelLocation.y == 20


def test_down_uses_pointer_id_zero(mock_user32):
    injector = TouchInjector()

    injector.down(1, 1)

    contact = mock_user32.InjectTouchInput.call_args[0][1].contents
    assert contact.pointerInfo.pointerId == 0


def test_down_uses_pointer_type_touch(mock_user32):
    from screentracker_host.touch_injector import PT_TOUCH

    injector = TouchInjector()

    injector.down(1, 1)

    contact = mock_user32.InjectTouchInput.call_args[0][1].contents
    assert contact.pointerInfo.pointerType == PT_TOUCH


def test_inject_raises_runtime_error_when_inject_touch_input_fails(mock_user32):
    mock_user32.InjectTouchInput.return_value = False
    injector = TouchInjector()

    with pytest.raises(RuntimeError, match="InjectTouchInput failed"):
        injector.down(1, 1)
