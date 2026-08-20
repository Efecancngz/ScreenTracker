import json
import secrets
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent / "host_identity.json"


def load_or_create_host_id(path: Path = DEFAULT_PATH) -> str:
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {}
    if "host_id" not in data:
        data["host_id"] = secrets.token_urlsafe(16)
        path.write_text(json.dumps(data))
    host_id = data["host_id"]
    load_or_create_host_secret(path)  # a fresh identity needs a fresh secret too
    return host_id


def load_or_create_host_secret(path: Path = DEFAULT_PATH) -> str:
    """A per-host credential, sent alongside host_id on every
    register-host. host_id alone identifies a host but doesn't prove
    ownership of it -- without this, anyone who learns a host_id (a
    paired viewer stores it, for one) could register the same host_id
    themselves and hijack it. The signaling server remembers the secret
    the first connection to claim a host_id registered with, and refuses
    later registrations under that host_id that don't present the same
    one."""
    data = json.loads(path.read_text()) if path.exists() else {}
    if "host_secret" not in data:
        data["host_secret"] = secrets.token_urlsafe(24)
        path.write_text(json.dumps(data))
    return data["host_secret"]
