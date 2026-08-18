import json
import secrets
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent.parent / "host_identity.json"


def load_or_create_host_id(path: Path = DEFAULT_PATH) -> str:
    if path.exists():
        return json.loads(path.read_text())["host_id"]
    host_id = secrets.token_urlsafe(16)
    path.write_text(json.dumps({"host_id": host_id}))
    return host_id
