from unittest.mock import MagicMock, patch

import numpy as np

from screentracker_host.capture import (
    ScreenCapturer,
    _DxcamBackend,
    _MssBackend,
    get_monitor_size,
)


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
        ScreenCapturer(backend_cls=_MssBackend)

    mock_mss_cls.assert_not_called()


def test_capture_constructs_mss_context_lazily_on_first_call_only():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_mss_cls.return_value = _make_mock_sct((100, 50), (50, 100))

        capturer = ScreenCapturer(backend_cls=_MssBackend)
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
            capturer = ScreenCapturer(backend_cls=_MssBackend)
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
            capturer = ScreenCapturer(max_dim=1280, backend_cls=_MssBackend)
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
            capturer = ScreenCapturer(max_dim=100, backend_cls=_MssBackend)
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
            capturer = ScreenCapturer(max_dim=100, backend_cls=_MssBackend)
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
            capturer = ScreenCapturer(backend_cls=_MssBackend)
            capturer.capture()  # lazily creates self._sct
            capturer.close()

    mock_sct.close.assert_called_once_with()


def test_close_is_a_safe_noop_when_capture_was_never_called():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        capturer = ScreenCapturer(backend_cls=_MssBackend)
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


def test_capture_recovers_from_a_grab_failure_by_recreating_the_context():
    """Observed real-world cause of the video track dying silently while
    the DataChannel stays healthy: mss's GDI/DXGI context can be
    invalidated by a display sleep/wake, resolution change, or screen
    lock/unlock while a capture loop is running. grab() then raises on
    every subsequent call against the now-stale context. Recovering by
    tearing down and rebuilding self._sct lets a transient invalidation
    heal itself instead of killing the stream for the rest of the
    connection's lifetime."""
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        stale_sct = _make_mock_sct((100, 50), (50, 100))
        stale_sct.grab.side_effect = Exception("GDI context invalidated")
        fresh_sct = _make_mock_sct((100, 50), (50, 100))
        mock_mss_cls.side_effect = [stale_sct, fresh_sct]

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((50, 100, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((50, 100, 3), dtype=np.uint8),
        ):
            capturer = ScreenCapturer(backend_cls=_MssBackend)
            # A single capture() call does the whole fail-then-recover cycle
            # internally: constructs stale_sct, grab() fails, rebuilds, and
            # retries against a fresh context -- all before returning.
            frame = capturer.capture()

    assert mock_mss_cls.call_count == 2
    stale_sct.close.assert_called_once_with()
    fresh_sct.grab.assert_called_once_with(fresh_sct.monitors[1])
    assert frame.width == 100
    assert frame.height == 50


def test_capture_raises_if_the_recreated_context_also_fails():
    """A second, distinct failure right after recovery is a real error
    (not a one-off transient blip) and must surface, not loop or hide
    the problem forever."""
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        first_sct = _make_mock_sct((100, 50), (50, 100))
        first_sct.grab.side_effect = Exception("first failure")
        second_sct = _make_mock_sct((100, 50), (50, 100))
        second_sct.grab.side_effect = Exception("second failure")
        mock_mss_cls.side_effect = [first_sct, second_sct]

        capturer = ScreenCapturer(backend_cls=_MssBackend)
        try:
            capturer.capture()
            raised = False
        except Exception as exc:
            raised = True
            assert "second failure" in str(exc)

    assert raised
    assert mock_mss_cls.call_count == 2


def test_list_monitors_excludes_the_synthetic_all_monitors_entry():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 3200, "height": 1080},  # index 0: synthetic combined
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 1920, "top": 0, "width": 1280, "height": 1080},
        ]
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        from screentracker_host.capture import list_monitors

        monitors = list_monitors()

    assert monitors == [
        {"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0},
        {"index": 2, "width": 1280, "height": 1080, "left": 1920, "top": 0},
    ]


def test_list_monitors_returns_single_entry_for_a_single_monitor_host():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        mock_sct.monitors = [
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]
        mock_mss_cls.return_value.__enter__.return_value = mock_sct

        from screentracker_host.capture import list_monitors

        monitors = list_monitors()

    assert monitors == [{"index": 1, "width": 1920, "height": 1080, "left": 0, "top": 0}]


def test_set_monitor_changes_which_monitor_the_next_capture_grabs():
    with patch("screentracker_host.capture.mss.mss") as mock_mss_cls:
        mock_sct = MagicMock()
        width, height = 100, 50
        mock_sct.monitors = [
            None,
            {"left": 0, "top": 0, "width": width, "height": height},
            {"left": width, "top": 0, "width": width, "height": height},
        ]
        fake_raw = MagicMock()
        fake_raw.width = width
        fake_raw.height = height
        mock_sct.grab.return_value = fake_raw
        mock_mss_cls.return_value = mock_sct

        with patch(
            "screentracker_host.capture.np.array",
            return_value=np.zeros((height, width, 4), dtype=np.uint8),
        ), patch(
            "screentracker_host.capture.cv2.cvtColor",
            return_value=np.zeros((height, width, 3), dtype=np.uint8),
        ):
            capturer = ScreenCapturer(backend_cls=_MssBackend)
            capturer.set_monitor(2)
            capturer.capture()

    mock_sct.grab.assert_called_once_with(mock_sct.monitors[2])


def test_default_backend_is_dxcam_on_windows():
    """The Task Manager freeze this backend switch exists to fix only
    reproduces via GDI/BitBlt (mss's Windows path). dxcam wraps DXGI
    Desktop Duplication, which doesn't share that DWM contention, so
    Windows must default to it -- not fall back to mss."""
    with patch("screentracker_host.capture.sys.platform", "win32"):
        capturer = ScreenCapturer()

    assert capturer._backend_cls is _DxcamBackend


def test_default_backend_is_mss_on_non_windows():
    """dxcam wraps DXGI Desktop Duplication, a Windows-only API. macOS and
    Linux have no equivalent, so they must keep using mss."""
    for platform in ("darwin", "linux"):
        with patch("screentracker_host.capture.sys.platform", platform):
            capturer = ScreenCapturer()

        assert capturer._backend_cls is _MssBackend


def _make_mock_dxcam_module(width, height, rgb_frame=None):
    """Build a MagicMock standing in for the `dxcam` module, whose
    `create()` returns a mock camera object with a `grab()` method."""
    mock_dxcam = MagicMock()
    mock_camera = MagicMock()
    mock_camera.grab.return_value = (
        rgb_frame if rgb_frame is not None else np.zeros((height, width, 3), dtype=np.uint8)
    )
    mock_dxcam.create.return_value = mock_camera
    return mock_dxcam, mock_camera


def test_dxcam_backend_creates_camera_lazily_for_requested_monitor():
    """monitor_index is mss-style 1-based (index 0 is mss's synthetic
    "all monitors" entry, never a real target); dxcam's output_idx is
    0-based, so it must be monitor_index - 1."""
    mock_dxcam, mock_camera = _make_mock_dxcam_module(100, 50)

    with patch("screentracker_host.capture.dxcam", mock_dxcam):
        capturer = ScreenCapturer(backend_cls=_DxcamBackend, monitor_index=2)
        mock_dxcam.create.assert_not_called()

        frame = capturer.capture()

    mock_dxcam.create.assert_called_once_with(device_idx=0, output_idx=1, output_color="RGB")
    mock_camera.grab.assert_called_once_with(new_frame_only=False)
    assert frame.width == 100
    assert frame.height == 50


def test_dxcam_backend_reuses_camera_across_multiple_calls():
    mock_dxcam, mock_camera = _make_mock_dxcam_module(100, 50)

    with patch("screentracker_host.capture.dxcam", mock_dxcam):
        capturer = ScreenCapturer(backend_cls=_DxcamBackend)
        capturer.capture()
        capturer.capture()

    mock_dxcam.create.assert_called_once_with(device_idx=0, output_idx=0, output_color="RGB")
    assert mock_camera.grab.call_count == 2


def test_dxcam_backend_recreates_camera_when_monitor_changes():
    mock_dxcam, mock_camera = _make_mock_dxcam_module(100, 50)

    with patch("screentracker_host.capture.dxcam", mock_dxcam):
        capturer = ScreenCapturer(backend_cls=_DxcamBackend)
        capturer.capture()
        capturer.set_monitor(2)
        capturer.capture()

    assert mock_dxcam.create.call_args_list == [
        (dict(device_idx=0, output_idx=0, output_color="RGB"),),
        (dict(device_idx=0, output_idx=1, output_color="RGB"),),
    ]
    mock_camera.release.assert_called_once_with()


def test_dxcam_backend_recovers_from_a_grab_failure_by_recreating_the_camera():
    """Mirrors the mss recovery test: DXGI Desktop Duplication can also be
    invalidated by a display sleep/wake, resolution change, or a mode
    switch (e.g. a UAC secure desktop, or an exclusive-fullscreen app
    taking the output) while a capture loop is running. Recover by
    releasing and rebuilding the camera once."""
    stale_camera = MagicMock()
    stale_camera.grab.side_effect = Exception("DXGI context invalidated")
    fresh_camera = MagicMock()
    fresh_camera.grab.return_value = np.zeros((50, 100, 3), dtype=np.uint8)

    mock_dxcam = MagicMock()
    mock_dxcam.create.side_effect = [stale_camera, fresh_camera]

    with patch("screentracker_host.capture.dxcam", mock_dxcam):
        capturer = ScreenCapturer(backend_cls=_DxcamBackend)
        frame = capturer.capture()

    assert mock_dxcam.create.call_count == 2
    stale_camera.release.assert_called_once_with()
    fresh_camera.grab.assert_called_once_with(new_frame_only=False)
    assert frame.width == 100
    assert frame.height == 50


def test_dxcam_backend_close_releases_the_camera():
    mock_dxcam, mock_camera = _make_mock_dxcam_module(100, 50)

    with patch("screentracker_host.capture.dxcam", mock_dxcam):
        capturer = ScreenCapturer(backend_cls=_DxcamBackend)
        capturer.capture()
        capturer.close()

    mock_camera.release.assert_called_once_with()


def test_dxcam_backend_close_is_a_safe_noop_when_capture_was_never_called():
    mock_dxcam, _ = _make_mock_dxcam_module(100, 50)

    with patch("screentracker_host.capture.dxcam", mock_dxcam):
        capturer = ScreenCapturer(backend_cls=_DxcamBackend)
        capturer.close()  # must not raise, must not construct a camera

    mock_dxcam.create.assert_not_called()
