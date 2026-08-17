import asyncio
import os

from screentracker_host.signaling_client import SignalingClient
from screentracker_host.webrtc_peer import HostPeerConnection


async def run() -> None:
    signaling_url = os.environ["SIGNALING_SERVER_URL"]
    client = SignalingClient(signaling_url)
    await client.connect()

    session_id = await client.create_session()
    print(f"Session ready. Share this code with your viewer: {session_id}")

    peer_connection = HostPeerConnection()

    async for message in client.messages():
        if message["type"] == "peer-joined":
            offer = await peer_connection.create_offer()
            await client.send({"type": "offer", "sdp": offer.sdp})
        elif message["type"] == "answer":
            await peer_connection.set_remote_answer(message["sdp"])
        elif message["type"] == "ice-candidate":
            await peer_connection.add_ice_candidate(message["candidate"])
        elif message["type"] == "peer-disconnected":
            print("Viewer disconnected.")
            break

    await peer_connection.close()
    await client.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
