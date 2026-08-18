from unittest.mock import MagicMock, patch

import numpy as np

from screentracker_host.capture import capture_frame, get_monitor_size


def test_capture_frame_returns_frame_with_expected_shape():
    fake_raw = MagicMock()
    fake_raw.width = 100
    fake_raw.height = 50

    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [None, {"left": 0, "top": 0, "width": 100, "height": 50}]
        mock_sct.grab.return_value = fake_raw
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((50, 100, 4), dtype=np.uint8),
        ):
            frame = capture_frame()

    assert frame.width == 100
    assert frame.height == 50
    assert frame.data.shape == (50, 100, 4)
    mock_sct.grab.assert_called_once_with({"left": 0, "top": 0, "width": 100, "height": 50})


def test_get_monitor_size_returns_width_and_height_without_grabbing():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [None, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        size = get_monitor_size()

    assert size == (1920, 1080)
    mock_sct.grab.assert_not_called()
