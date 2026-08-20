import json
import secrets
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent / "paired_devices.json"


class PairedDevices:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self._path = path
        self._devices: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text())
        return {}

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._devices, indent=2))

    def is_known(self, device_id: str) -> bool:
        return device_id in self._devices

    def is_paired(self, device_id: str, token: str) -> bool:
        entry = self._devices.get(device_id)
        # Constant-time comparison: this is a bearer-token check, and a
        # naive == leaks how many leading characters matched via timing.
        return entry is not None and secrets.compare_digest(entry["token"], token)

    def approve(self, device_id: str, label: str) -> str:
        token = secrets.token_urlsafe(24)
        self._devices[device_id] = {"token": token, "label": label, "paired_at": time.time()}
        self._save()
        return token
