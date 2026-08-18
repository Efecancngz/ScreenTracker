from screentracker_host.paired_devices import PairedDevices


def test_approve_generates_a_token_and_marks_the_device_known(tmp_path):
    store = PairedDevices(tmp_path / "paired_devices.json")

    token = store.approve("dev-1", label="Test Phone")

    assert token
    assert store.is_known("dev-1")
    assert store.is_paired("dev-1", token)


def test_is_paired_rejects_a_wrong_token(tmp_path):
    store = PairedDevices(tmp_path / "paired_devices.json")
    store.approve("dev-1", label="Test Phone")

    assert not store.is_paired("dev-1", "wrong-token")


def test_unknown_device_is_neither_known_nor_paired(tmp_path):
    store = PairedDevices(tmp_path / "paired_devices.json")

    assert not store.is_known("dev-nope")
    assert not store.is_paired("dev-nope", "any-token")


def test_approvals_persist_across_a_fresh_instance_on_the_same_path(tmp_path):
    path = tmp_path / "paired_devices.json"
    first_store = PairedDevices(path)
    token = first_store.approve("dev-2", label="Test Tablet")

    second_store = PairedDevices(path)

    assert second_store.is_paired("dev-2", token)
