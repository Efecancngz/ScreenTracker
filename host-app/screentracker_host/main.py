import asyncio
import os
import sys
from collections.abc import Callable

from screentracker_host.host_identity import load_or_create_host_id, load_or_create_host_secret
from screentracker_host.paired_devices import PairedDevices
from screentracker_host.pairing import gui_prompt, request_approval
from screentracker_host.signaling_client import SignalingClient
from screentracker_host.webrtc_peer import HostPeerConnection


def select_prompt_fn() -> Callable[[str], str]:
    """input() needs a real console to read from. Running under
    pythonw.exe (the tray launcher) leaves sys.stdin as None; running under
    a plain console (python.exe, or start-dev.bat) leaves it a real,
    interactive stream. Fall back to a GUI dialog whenever there's no
    console to prompt on."""
    if sys.stdin is not None and sys.stdin.isatty():
        return input
    return gui_prompt


RECONNECT_BASE_DELAY_SECONDS = 1.0
RECONNECT_MAX_DELAY_SECONDS = 30.0


async def run() -> None:
    signaling_url = os.environ["SIGNALING_SERVER_URL"]
    host_id = load_or_create_host_id()
    host_secret = load_or_create_host_secret()
    paired_devices = PairedDevices()
    prompt_fn = select_prompt_fn()
    peer_connection = HostPeerConnection()
    # Tracks whether the current peer_connection has already completed a
    # handshake. A single aiortc RTCPeerConnection can't be renegotiated
    # against a different remote peer, so it only gets replaced lazily,
    # right before the next real offer — never eagerly on peer-disconnected.
    # An eager swap there was closing a live, perfectly healthy WebRTC
    # connection every time the *signaling* channel merely blipped (mobile
    # screen lock, a Wi-Fi/cell handoff): the video would vanish with no
    # error and no way back, even though the underlying stream never
    # actually failed. That same reasoning is why peer_connection lives
    # outside the reconnect loop below, instead of being rebuilt on every
    # signaling reconnect.
    peer_connection_used = False
    streaming = False
    reconnect_delay = RECONNECT_BASE_DELAY_SECONDS

    try:
        while True:
            client = SignalingClient(signaling_url)
            try:
                await client.connect()
                await client.send(
                    {"type": "register-host", "host_id": host_id, "host_secret": host_secret}
                )
                session_id = await client.create_session()
                print(f"Session ready. Share this code with your viewer: {session_id}")
                reconnect_delay = RECONNECT_BASE_DELAY_SECONDS

                async for message in client.messages():
                    if message["type"] == "peer-joined":
                        if peer_connection_used:
                            await peer_connection.close()
                            peer_connection = HostPeerConnection()
                            peer_connection_used = False
                        streaming = await _handle_peer_joined(
                            message,
                            client=client,
                            peer_connection=peer_connection,
                            paired_devices=paired_devices,
                            host_id=host_id,
                            prompt_fn=prompt_fn,
                        )
                        if streaming:
                            peer_connection_used = True
                    elif message["type"] == "answer":
                        await peer_connection.set_remote_answer(message["sdp"])
                    elif message["type"] == "ice-candidate":
                        await peer_connection.add_ice_candidate(message["candidate"])
                    elif message["type"] == "peer-disconnected":
                        if streaming:
                            print("Viewer disconnected. Waiting for the next viewer...")
                        else:
                            print("A pending viewer disconnected before pairing completed.")
                        streaming = False
            except Exception as exc:
                # The signaling WebSocket dropping (a network blip, the
                # signaling server restarting, a Tailscale hiccup) used to
                # propagate straight out of run() and kill the entire host
                # process -- confirmed live: the process was gone from the
                # task list afterward, with nothing left for even the
                # viewer's own client-side reconnect to reconnect TO.
                # Reconnect instead, the same way the viewer already does.
                print(f"Signaling connection lost ({exc!r}); reconnecting in {reconnect_delay:.0f}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_DELAY_SECONDS)
            finally:
                await client.close()
    finally:
        await peer_connection.close()


async def _handle_peer_joined(
    message: dict,
    *,
    client: SignalingClient,
    peer_connection: HostPeerConnection,
    paired_devices: PairedDevices,
    host_id: str,
    prompt_fn: Callable[[str], str] = input,
) -> bool:
    """Decide whether a joining viewer gets streamed to. Returns True once an
    offer has actually been sent (the caller uses this to know whether a
    later peer-disconnected means a real stream ended)."""
    device_id = message.get("device_id")
    token = message.get("token")

    if not device_id:
        await client.send({"type": "pair-rejected", "reason": "missing-device-id"})
        await client.send({"type": "release-peer"})
        return False

    if token is not None:
        if not device_id or not paired_devices.is_paired(device_id, token):
            await client.send({"type": "authenticate-failed"})
            await client.send({"type": "release-peer"})
            return False
    elif device_id and not paired_devices.is_known(device_id):
        approved = await request_approval(
            label="viewer device", device_id=device_id, prompt_fn=prompt_fn
        )
        if not approved:
            await client.send({"type": "pair-rejected", "reason": "denied"})
            await client.send({"type": "release-peer"})
            return False
        new_token = paired_devices.approve(device_id, label="viewer device")
        await client.send({"type": "pair-approved", "token": new_token, "host_id": host_id})

    offer = await peer_connection.create_offer()
    await client.send({"type": "offer", "sdp": offer.sdp})
    return True


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
