# Signaling WebSocket API

Single endpoint: `ws://<signaling-host>/ws`. All messages are JSON objects with a
`type` field.

| Message | Direction | Payload |
|---|---|---|
| `create-session` | Host → Server | — |
| `session-created` | Server → Host | `session_id: string` |
| `join-session` | Viewer → Server | `session_id: string` |
| `peer-joined` | Server → Host | — |
| `offer` | Host → Server → Viewer | `sdp: string` |
| `answer` | Viewer → Server → Host | `sdp: string` |
| `ice-candidate` | Viewer → Server → Host (relayed) | `candidate: object` — the browser's `RTCIceCandidateInit` verbatim: `{candidate, sdpMid, sdpMLineIndex, usernameFragment}` |
| `session-expired` | Server → Viewer | `reason: "not-found" \| "expired"` |
| `peer-disconnected` | Server → remaining peer | — |

The host (aiortc) does not trickle ICE: every host candidate is already carried in
the `offer` SDP, so the host never sends `ice-candidate`. Only the viewer does.
