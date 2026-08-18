import sys
import time

from tray_app import (
    ManagedProcess,
    host_app_argv,
    load_env_file,
    parse_session_code,
    signaling_server_argv,
    viewer_url_from_signaling_url,
)


def test_load_env_file_skips_blank_and_comment_lines(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# Signaling server",
                "SIGNALING_SERVER_HOST=0.0.0.0",
                "SIGNALING_SERVER_PORT=8000",
                "",
                "# Host app",
                "SIGNALING_SERVER_URL=ws://100.106.113.59:8000/ws",
                "#TURN_SERVER_URL=turn:example:3478",
            ]
        ),
        encoding="utf-8",
    )

    values = load_env_file(env_path)

    assert values == {
        "SIGNALING_SERVER_HOST": "0.0.0.0",
        "SIGNALING_SERVER_PORT": "8000",
        "SIGNALING_SERVER_URL": "ws://100.106.113.59:8000/ws",
    }


def test_load_env_file_on_missing_file_returns_empty_dict(tmp_path):
    assert load_env_file(tmp_path / "does-not-exist.env") == {}


def test_parse_session_code_extracts_the_code():
    line = "Session ready. Share this code with your viewer: X7K2M9\n"
    assert parse_session_code(line) == "X7K2M9"


def test_parse_session_code_ignores_unrelated_lines():
    assert parse_session_code("Viewer disconnected. Waiting for the next viewer...\n") is None


def test_signaling_server_argv_uses_env_host_and_port():
    argv = signaling_server_argv({"SIGNALING_SERVER_HOST": "0.0.0.0", "SIGNALING_SERVER_PORT": "9000"})
    assert argv == [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]


def test_signaling_server_argv_defaults_when_env_missing():
    argv = signaling_server_argv({})
    assert argv == [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


def test_viewer_url_from_signaling_url_ws():
    assert viewer_url_from_signaling_url("ws://100.106.113.59:8000/ws") == "http://100.106.113.59:8000/"


def test_viewer_url_from_signaling_url_wss():
    assert viewer_url_from_signaling_url("wss://example.com:8000/ws") == "https://example.com:8000/"


def test_viewer_url_from_signaling_url_rejects_unknown_scheme():
    assert viewer_url_from_signaling_url("http://example.com:8000/ws") is None


def test_viewer_url_from_signaling_url_rejects_empty_string():
    assert viewer_url_from_signaling_url("") is None


def test_host_app_argv():
    # -u is required: without it, the child's stdout is fully buffered
    # (not a TTY) and the session-code line never reaches the log/callback
    # until the process exits.
    assert host_app_argv() == [sys.executable, "-u", "-m", "screentracker_host.main"]


def test_managed_process_tees_output_to_log_and_calls_on_line(tmp_path):
    log_path = tmp_path / "proc.log"
    seen_lines: list[str] = []

    proc = ManagedProcess(
        name="printer",
        argv=[
            sys.executable,
            "-c",
            "print('Session ready. Share this code with your viewer: ABC123')",
        ],
        cwd=tmp_path,
        env=None,
        log_path=log_path,
        on_line=seen_lines.append,
    )
    proc.start()

    for _ in range(50):
        if not proc.is_running():
            break
        time.sleep(0.1)

    assert any("ABC123" in line for line in seen_lines)
    assert "ABC123" in log_path.read_text(encoding="utf-8")


def test_managed_process_stop_terminates_a_long_running_process(tmp_path):
    log_path = tmp_path / "proc.log"
    proc = ManagedProcess(
        name="sleeper",
        argv=[sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        env=None,
        log_path=log_path,
    )
    proc.start()
    time.sleep(0.3)
    assert proc.is_running()

    proc.stop(timeout=5.0)

    assert not proc.is_running()
