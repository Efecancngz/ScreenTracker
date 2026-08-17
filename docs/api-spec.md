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
| `ice-candidate` | either direction, relayed | `candidate: string`, `sdp_mid?: string`, `sdp_mline_index?: number` |
| `session-expired` | Server → Viewer | `reason: "not-found" \| "expired"` |
| `peer-disconnected` | Server → remaining peer | — |
