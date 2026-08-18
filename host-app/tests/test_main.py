from unittest.mock import AsyncMock, MagicMock

import pytest

from screentracker_host.main import _handle_peer_joined, select_prompt_fn
from screentracker_host.paired_devices import PairedDevices
from screentracker_host.pairing import gui_prompt


@pytest.mark.asyncio
async def test_known_device_with_valid_token_streams_without_a_prompt(tmp_path):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    token = paired_devices.approve("dev-1", label="Test Phone")
    client = AsyncMock()
    peer_connection = AsyncMock()
    peer_connection.create_offer.return_value.sdp = "v=0..."

    streaming = await _handle_peer_joined(
        {"device_id": "dev-1", "token": token},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is True
    client.send.assert_awaited_with({"type": "offer", "sdp": "v=0..."})


@pytest.mark.asyncio
async def test_invalid_token_is_rejected_and_releases_the_peer(tmp_path):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    client = AsyncMock()
    peer_connection = AsyncMock()

    streaming = await _handle_peer_joined(
        {"device_id": "dev-1", "token": "wrong-token"},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is False
    client.send.assert_any_await({"type": "authenticate-failed"})
    client.send.assert_any_await({"type": "release-peer"})
    peer_connection.create_offer.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_device_approved_by_operator_gets_paired_and_streams(tmp_path, monkeypatch):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    client = AsyncMock()
    peer_connection = AsyncMock()
    peer_connection.create_offer.return_value.sdp = "v=0..."
    monkeypatch.setattr(
        "screentracker_host.main.request_approval", AsyncMock(return_value=True)
    )

    streaming = await _handle_peer_joined(
        {"device_id": "dev-2", "token": None},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is True
    assert paired_devices.is_known("dev-2")
    sent_types = [call.args[0]["type"] for call in client.send.await_args_list]
    assert "pair-approved" in sent_types
    assert "offer" in sent_types


@pytest.mark.asyncio
async def test_unknown_device_rejected_by_operator_does_not_stream(tmp_path, monkeypatch):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    client = AsyncMock()
    peer_connection = AsyncMock()
    monkeypatch.setattr(
        "screentracker_host.main.request_approval", AsyncMock(return_value=False)
    )

    streaming = await _handle_peer_joined(
        {"device_id": "dev-3", "token": None},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is False
    assert not paired_devices.is_known("dev-3")
    client.send.assert_any_await({"type": "pair-rejected", "reason": "denied"})
    peer_connection.create_offer.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_known_device_without_a_token_skips_the_prompt(tmp_path, monkeypatch):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    paired_devices.approve("dev-4", label="Already paired")
    client = AsyncMock()
    peer_connection = AsyncMock()
    peer_connection.create_offer.return_value.sdp = "v=0..."
    request_approval_mock = AsyncMock()
    monkeypatch.setattr("screentracker_host.main.request_approval", request_approval_mock)

    streaming = await _handle_peer_joined(
        {"device_id": "dev-4", "token": None},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is True
    request_approval_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_device_id_is_rejected_without_streaming(tmp_path):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    client = AsyncMock()
    peer_connection = AsyncMock()

    streaming = await _handle_peer_joined(
        {"device_id": None, "token": None},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
    )

    assert streaming is False
    client.send.assert_any_await({"type": "pair-rejected", "reason": "missing-device-id"})
    client.send.assert_any_await({"type": "release-peer"})
    peer_connection.create_offer.assert_not_awaited()


def test_select_prompt_fn_uses_input_on_a_real_console(monkeypatch):
    monkeypatch.setattr("sys.stdin", MagicMock(isatty=MagicMock(return_value=True)))
    assert select_prompt_fn() is input


def test_select_prompt_fn_falls_back_to_gui_when_stdin_is_none(monkeypatch):
    # pythonw.exe (the tray launcher) sets sys.stdin to None — there is no
    # console for input() to read from.
    monkeypatch.setattr("sys.stdin", None)
    assert select_prompt_fn() is gui_prompt


def test_select_prompt_fn_falls_back_to_gui_when_stdin_is_not_a_tty(monkeypatch):
    # Piped/redirected stdin (e.g. run from another launcher) isn't
    # interactive either, even though it isn't None.
    monkeypatch.setattr("sys.stdin", MagicMock(isatty=MagicMock(return_value=False)))
    assert select_prompt_fn() is gui_prompt


@pytest.mark.asyncio
async def test_unknown_device_prompt_uses_the_injected_prompt_fn(tmp_path):
    paired_devices = PairedDevices(tmp_path / "paired_devices.json")
    client = AsyncMock()
    peer_connection = AsyncMock()
    peer_connection.create_offer.return_value.sdp = "v=0..."
    prompt_fn = MagicMock(return_value="y")

    streaming = await _handle_peer_joined(
        {"device_id": "dev-6", "token": None},
        client=client,
        peer_connection=peer_connection,
        paired_devices=paired_devices,
        host_id="host-1",
        prompt_fn=prompt_fn,
    )

    assert streaming is True
    prompt_fn.assert_called_once()
