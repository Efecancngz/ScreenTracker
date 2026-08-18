import asyncio
import os

from screentracker_host.host_identity import load_or_create_host_id
from screentracker_host.paired_devices import PairedDevices
from screentracker_host.pairing import request_approval
from screentracker_host.signaling_client import SignalingClient
from screentracker_host.webrtc_peer import HostPeerConnection


async def run() -> None:
    signaling_url = os.environ["SIGNALING_SERVER_URL"]
    client = SignalingClient(signaling_url)
    await client.connect()

    host_id = load_or_create_host_id()
    await client.send({"type": "register-host", "host_id": host_id})

    session_id = await client.create_session()
    print(f"Session ready. Share this code with your viewer: {session_id}")

    paired_devices = PairedDevices()
    peer_connection = HostPeerConnection()
    streaming = False

    try:
        async for message in client.messages():
            if message["type"] == "peer-joined":
                streaming = await _handle_peer_joined(
                    message,
                    client=client,
                    peer_connection=peer_connection,
                    paired_devices=paired_devices,
                    host_id=host_id,
                )
            elif message["type"] == "answer":
                await peer_connection.set_remote_answer(message["sdp"])
            elif message["type"] == "ice-candidate":
                await peer_connection.add_ice_candidate(message["candidate"])
            elif message["type"] == "peer-disconnected":
                if streaming:
                    print("Viewer disconnected.")
                    break
                print("A pending viewer disconnected before pairing completed.")
    finally:
        await peer_connection.close()
        await client.close()


async def _handle_peer_joined(
    message: dict,
    *,
    client: SignalingClient,
    peer_connection: HostPeerConnection,
    paired_devices: PairedDevices,
    host_id: str,
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
        approved = await request_approval(label="viewer device", device_id=device_id)
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
