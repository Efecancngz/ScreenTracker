"""Background launcher for ScreenTracker.

Runs the signaling server and host app as hidden subprocesses and exposes a
single system tray icon with the controls needed for daily use: see the
current session code, copy it, start a fresh session (which drops any
connected viewer and issues a new code), open the logs, or quit everything.
Meant to be started with `pythonw.exe` so no console window ever appears —
see start.bat at the repo root.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import pystray
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
LOG_DIR = REPO_ROOT / "launcher" / "logs"

_SESSION_CODE_RE = re.compile(r"Share this code with your viewer:\s*([A-Z0-9]+)")

# Popen's creationflags kwarg is Windows-only; on other platforms it must be
# omitted entirely rather than passed as 0.
_POPEN_KWARGS: dict[str, object] = (
    {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # CREATE_NO_WINDOW
)


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE .env file. Blank lines and lines starting
    with # (including commented-out settings) are skipped."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def parse_session_code(line: str) -> str | None:
    """Pull the session code out of the host app's
    "Session ready. Share this code with your viewer: XXXXXX" startup line."""
    match = _SESSION_CODE_RE.search(line)
    return match.group(1) if match else None


def signaling_server_argv(env: dict[str, str]) -> list[str]:
    host = env.get("SIGNALING_SERVER_HOST", "0.0.0.0")
    port = env.get("SIGNALING_SERVER_PORT", "8000")
    return [sys.executable, "-m", "uvicorn", "app.main:app", "--host", host, "--port", port]


def viewer_url_from_signaling_url(signaling_server_url: str) -> str | None:
    """Derive the URL to open in a browser from the host app's
    SIGNALING_SERVER_URL (e.g. "ws://100.106.113.59:8000/ws" ->
    "http://100.106.113.59:8000/"). The viewer is served by the signaling
    server itself, on the same host and port, at "/" instead of "/ws"."""
    if signaling_server_url.startswith("wss://"):
        rest = signaling_server_url[len("wss://") :]
        scheme = "https://"
    elif signaling_server_url.startswith("ws://"):
        rest = signaling_server_url[len("ws://") :]
        scheme = "http://"
    else:
        return None
    host = rest.split("/", 1)[0]
    if not host:
        return None
    return f"{scheme}{host}/"


def host_app_argv() -> list[str]:
    # -u: unbuffered stdout/stderr. Without it, CPython fully buffers output
    # that isn't connected to a terminal (which a piped subprocess never is),
    # so the "Session ready..." line — and everything else — would sit in
    # the child's internal buffer indefinitely instead of reaching the log
    # or the on_line callback that detects the session code.
    return [sys.executable, "-u", "-m", "screentracker_host.main"]


class ManagedProcess:
    """Runs one subprocess with a hidden window, tees its output to a log
    file, and optionally calls a callback for every line it prints (used to
    pull the session code out of the host app's stdout)."""

    def __init__(
        self,
        name: str,
        argv: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        log_path: Path,
        on_line: Callable[[str], None] | None = None,
    ) -> None:
        self.name = name
        self._argv = argv
        self._cwd = cwd
        self._env = env
        self._log_path = log_path
        self._on_line = on_line
        self._proc: subprocess.Popen | None = None
        self._pump_thread: threading.Thread | None = None
        self._stopping = False

    def start(self) -> None:
        self._stopping = False
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(
            self._argv,
            cwd=self._cwd,
            env=self._env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **_POPEN_KWARGS,
        )
        self._pump_thread = threading.Thread(target=self._pump_output, daemon=True)
        self._pump_thread.start()

    def _pump_output(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        with self._log_path.open("a", encoding="utf-8") as log_file:
            for line in self._proc.stdout:
                log_file.write(line)
                log_file.flush()
                if self._on_line:
                    self._on_line(line)
        if not self._stopping:
            logging.warning("%s exited unexpectedly — check %s", self.name, self._log_path)

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self, timeout: float = 5.0) -> None:
        self._stopping = True
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=timeout)
        self._proc = None


def _build_icon_image() -> Image.Image:
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size - 4, size - 4), fill=(184, 115, 51, 255))  # copper accent
    return image


def _fatal_error(message: str) -> None:
    logging.error(message)
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(0, message, "ScreenTracker", 0x10)


class TrayApp:
    def __init__(self) -> None:
        self._env = load_env_file(ENV_PATH)
        self._session_code: str | None = None
        self._icon: pystray.Icon | None = None
        self._viewer_url = viewer_url_from_signaling_url(
            self._env.get("SIGNALING_SERVER_URL", "")
        )

        self._signaling = ManagedProcess(
            name="signaling-server",
            argv=signaling_server_argv(self._env),
            cwd=REPO_ROOT / "signaling-server",
            env=None,
            log_path=LOG_DIR / "signaling-server.log",
        )
        self._host = ManagedProcess(
            name="host-app",
            argv=host_app_argv(),
            cwd=REPO_ROOT / "host-app",
            env=self._host_env(),
            log_path=LOG_DIR / "host-app.log",
            on_line=self._on_host_line,
        )

    def _host_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._env)
        return env

    def _on_host_line(self, line: str) -> None:
        code = parse_session_code(line)
        if code:
            self._session_code = code
            if self._icon is not None:
                self._icon.update_menu()
            if self._viewer_url:
                self._notify(f"{self._viewer_url}  —  code {code}")
            else:
                self._notify(f"Session code: {code}")

    def _notify(self, message: str, title: str = "ScreenTracker") -> None:
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title)
        except Exception:
            pass  # Notifications are a convenience; never let them crash the app.

    def _code_label(self, _item: object) -> str:
        return f"Code: {self._session_code}" if self._session_code else "Starting…"

    def _url_label(self, _item: object) -> str:
        return self._viewer_url or "URL: unknown (check SIGNALING_SERVER_URL in .env)"

    def _copy_code(self, _icon: pystray.Icon, _item: object) -> None:
        if not self._session_code:
            return
        try:
            subprocess.run(["clip"], input=self._session_code.encode(), check=True)
            self._notify("Session code copied to clipboard.")
        except Exception:
            logging.exception("Failed to copy session code to clipboard")

    def _copy_url(self, _icon: pystray.Icon, _item: object) -> None:
        if not self._viewer_url:
            return
        try:
            subprocess.run(["clip"], input=self._viewer_url.encode(), check=True)
            self._notify("Viewer URL copied to clipboard.")
        except Exception:
            logging.exception("Failed to copy viewer URL to clipboard")

    def _new_session(self, _icon: pystray.Icon, _item: object) -> None:
        """Drop the current viewer (if any) and issue a fresh session code —
        restarting the host app achieves both: its WebSocket disconnect makes
        the signaling server tear the old session down, and it registers a
        brand new one on the way back up."""
        self._session_code = None
        if self._icon is not None:
            self._icon.update_menu()
        self._host.stop()
        self._host.start()
        self._notify("New session started — the previous code and viewer are now disconnected.")

    def _open_logs(self, _icon: pystray.Icon, _item: object) -> None:
        if sys.platform == "win32":
            os.startfile(LOG_DIR)  # noqa: S606 - local folder, not user input

    def _quit(self, icon: pystray.Icon, _item: object) -> None:
        self._host.stop()
        self._signaling.stop()
        icon.stop()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(self._url_label, None, enabled=False),
            pystray.MenuItem(self._code_label, None, enabled=False),
            pystray.MenuItem("Copy viewer URL", self._copy_url),
            pystray.MenuItem("Copy code", self._copy_code),
            pystray.MenuItem("New session", self._new_session),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open logs folder", self._open_logs),
            pystray.MenuItem("Quit", self._quit),
        )

    def run(self) -> None:
        if not self._env.get("SIGNALING_SERVER_URL", "").strip():
            _fatal_error(
                "SIGNALING_SERVER_URL is not set in .env.\n\n"
                "Copy .env.example to .env in the repository root and fill it in "
                "before starting ScreenTracker."
            )
            return

        self._signaling.start()
        time.sleep(1.5)  # give the signaling server a moment before the host app dials in
        self._host.start()

        self._icon = pystray.Icon(
            "ScreenTracker", _build_icon_image(), "ScreenTracker", self._build_menu()
        )
        self._icon.run()


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_DIR / "launcher.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    TrayApp().run()


if __name__ == "__main__":
    main()
