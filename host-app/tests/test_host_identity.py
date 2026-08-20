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


def test_creating_a_new_host_id_also_creates_a_host_secret(tmp_path):
    path = tmp_path / "host_identity.json"

    load_or_create_host_id(path)

    secret = json.loads(path.read_text())["host_secret"]
    assert secret
    assert len(secret) >= 20  # meaningful entropy, not a placeholder


def test_load_or_create_host_secret_returns_the_same_secret_on_subsequent_calls(tmp_path):
    from screentracker_host.host_identity import load_or_create_host_secret

    path = tmp_path / "host_identity.json"
    load_or_create_host_id(path)

    first = load_or_create_host_secret(path)
    second = load_or_create_host_secret(path)

    assert first == second


def test_load_or_create_host_secret_migrates_a_file_saved_before_secrets_existed(tmp_path):
    """A host_identity.json written by an older version of this app has no
    host_secret field at all. Reading it must not crash -- generate and
    persist one instead, so upgrading doesn't strand an existing host
    without the credential the signaling server now requires to prove
    it's the same host reconnecting under a new host_id."""
    from screentracker_host.host_identity import load_or_create_host_secret

    path = tmp_path / "host_identity.json"
    path.write_text(json.dumps({"host_id": "pre-existing-host-id"}))

    secret = load_or_create_host_secret(path)

    assert secret
    assert json.loads(path.read_text())["host_secret"] == secret
