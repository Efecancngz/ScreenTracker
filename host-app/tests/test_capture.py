from unittest.mock import MagicMock, patch

import numpy as np

from screentracker_host.capture import ScreenCapturer, get_monitor_size


def _make_mock_sct(monitor_size, grab_shape):
    """Build a MagicMock standing in for the object returned by mss.mss()."""
    mock_sct = MagicMock()
    width, height = monitor_size
    mock_sct.monitors = [None, {"left": 0, "top": 0, "width": width, "height": height}]
    fake_raw = MagicMock()
    fake_raw.width = grab_shape[1]
    fake_raw.height = grab_shape[0]
    mock_sct.grab.return_value = fake_raw
    return mock_sct


def test_init_does_not_construct_mss_context():
    """mss keeps its GDI handles in threading.local(), populated only on the
    thread that calls mss.mss(). ScreenCapturer is constructed on the event
    loop thread but capture() runs on a separate executor worker thread, so
    the context must not be built eagerly in __init__ -- only lazily, on
    whatever thread first calls capture()."""
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        ScreenCapturer()

    mock_mss_cls.assert_not_called()


def test_capture_constructs_mss_context_lazily_on_first_call_only():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_mss_cls.return_value = _make_mock_sct((100, 50), (50, 100))

        capturer = ScreenCapturer()
        mock_mss_cls.assert_not_called()

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((50, 100, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((50, 100, 3), dtype=np.uint8),
        ):
            capturer.capture()
            mock_mss_cls.assert_called_once_with()

            capturer.capture()

    # Still just the one construction, from the first call.
    mock_mss_cls.assert_called_once_with()


def test_capture_reuses_context_across_multiple_calls():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = _make_mock_sct((100, 50), (50, 100))
        mock_mss_cls.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((50, 100, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((50, 100, 3), dtype=np.uint8),
        ):
            capturer = ScreenCapturer()
            capturer.capture()
            capturer.capture()

    mock_mss_cls.assert_called_once_with()
    assert mock_sct.grab.call_count == 2


def test_capture_returns_rgb_frame_matching_source_when_below_max_dim():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = _make_mock_sct((100, 50), (50, 100))
        mock_mss_cls.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((50, 100, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((50, 100, 3), dtype=np.uint8),
        ) as mock_cvt, patch(
            "screentracker_host.capture.cv2.resize"
        ) as mock_resize:
            capturer = ScreenCapturer(max_dim=1280)
            frame = capturer.capture()

    mock_cvt.assert_called_once()
    mock_resize.assert_not_called()
    assert frame.width == 100
    assert frame.height == 50
    assert frame.data.shape == (50, 100, 3)


def test_capture_downscales_when_source_exceeds_max_dim():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = _make_mock_sct((200, 100), (100, 200))
        mock_mss_cls.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((100, 200, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((100, 200, 3), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.resize",
            return_value=np.zeros((50, 100, 3), dtype=np.uint8),
        ) as mock_resize:
            capturer = ScreenCapturer(max_dim=100)
            frame = capturer.capture()

    mock_resize.assert_called_once()
    args, kwargs = mock_resize.call_args
    assert args[1] == (100, 50)  # (width, height), aspect ratio preserved
    assert max(frame.width, frame.height) == 100


def test_capture_does_not_downscale_when_longest_side_equals_max_dim():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = _make_mock_sct((100, 50), (50, 100))
        mock_mss_cls.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((50, 100, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((50, 100, 3), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.resize"
        ) as mock_resize:
            capturer = ScreenCapturer(max_dim=100)
            frame = capturer.capture()

    mock_resize.assert_not_called()
    assert frame.width == 100
    assert frame.height == 50


def test_close_closes_underlying_mss_context():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = _make_mock_sct((100, 50), (50, 100))
        mock_mss_cls.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((50, 100, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((50, 100, 3), dtype=np.uint8),
        ):
            capturer = ScreenCapturer()
            capturer.capture()  # lazily creates self._sct
            capturer.close()

    mock_sct.close.assert_called_once_with()


def test_close_is_a_safe_noop_when_capture_was_never_called():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        capturer = ScreenCapturer()
        capturer.close()  # must not raise, must not construct mss.mss()

    mock_mss_cls.assert_not_called()


def test_get_monitor_size_returns_width_and_height_without_grabbing():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [None, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        size = get_monitor_size()

    assert size == (1920, 1080)
    mock_sct.grab.assert_not_called()
