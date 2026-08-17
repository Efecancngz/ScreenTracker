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
| `session-expired` | Server → Viewer | `reason: "not-found" \| "expired" \| "already-claimed" \| "rate-limited"`, plus `retry_after_seconds: number` when `reason` is `"rate-limited"` (and, transitionally, whenever a lockout is already active regardless of the underlying reason) |
| `peer-disconnected` | Server → remaining peer | — |

The host (aiortc) does not trickle ICE: every host candidate is already carried in
the `offer` SDP, so the host never sends `ice-candidate`. Only the viewer does.

## Join rate limiting

The server tracks failed `join-session` attempts per client IP address, in
memory. The first 3 failures are free (typos happen); each failure after that
locks the client out for an exponentially growing backoff (2s, 4s, 8s, ...,
capped at 60s). An attempt made while locked counts as a failure too, so
ignoring the wait time escalates the lockout rather than resetting it. After
8 total failures the server closes the connection outright. A successful join
clears the client's failure count.
