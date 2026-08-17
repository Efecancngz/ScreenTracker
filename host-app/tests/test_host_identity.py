import json

from screentracker_host.host_identity import load_or_create_host_id


def test_creates_a_new_host_id_when_the_file_does_not_exist(tmp_path):
    path = tmp_path / "host_identity.json"

    host_id = load_or_create_host_id(path)

    assert host_id
    assert json.loads(path.read_text())["host_id"] == host_id


def test_returns_the_same_host_id_on_subsequent_calls(tmp_path):
    path = tmp_path / "host_identity.json"

    first = load_or_create_host_id(path)
    second = load_or_create_host_id(path)

    assert first == second
