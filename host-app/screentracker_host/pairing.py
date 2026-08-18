import asyncio
from collections.abc import Callable

APPROVAL_TIMEOUT_SECONDS = 60.0


def gui_prompt(prompt_text: str) -> str:
    """Show a native Yes/No dialog and return "y"/"n" — used instead of
    input() when there's no console to read from (e.g. running under
    pythonw.exe via the tray launcher, where sys.stdin is None)."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        approved = messagebox.askyesno(
            "ScreenTracker — pairing request", prompt_text, parent=root
        )
    finally:
        root.destroy()
    return "y" if approved else "n"


async def request_approval(
    label: str,
    device_id: str,
    prompt_fn: Callable[[str], str] = input,
    timeout_seconds: float = APPROVAL_TIMEOUT_SECONDS,
) -> bool:
    """Ask a human at the terminal to approve a new device. Runs the
    (blocking) prompt in an executor so it never blocks the event loop.
    Returns False on timeout, on a closed/non-interactive stdin, or any
    answer that isn't 'y'."""
    loop = asyncio.get_event_loop()
    prompt_text = f"New device requesting access: {label} ({device_id[:8]}) — approve? [y/N]: "
    try:
        answer = await asyncio.wait_for(
            loop.run_in_executor(None, prompt_fn, prompt_text),
            timeout=timeout_seconds,
        )
    except (asyncio.TimeoutError, EOFError):
        return False
    return answer.strip().lower() == "y"
