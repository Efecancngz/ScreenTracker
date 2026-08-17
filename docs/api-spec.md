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
memory. The first 5 failures are free (typos happen); each failure after that
locks the client out for an exponentially growing backoff (2s, 4s, 8s, ...,
capped at 120s). An attempt made while locked counts as a failure too, so
ignoring the wait time escalates the lockout rather than resetting it. After
8 total failures the server closes the connection outright. A successful join
clears the client's failure count.

## Device pairing and authentication

| Message | Direction | Payload |
|---|---|---|
| `register-host` | Host → Server | `host_id: string` |
| `authenticate` | Viewer → Server | `host_id: string`, `device_id: string`, `token: string` |
| `pair-approved` | Host → Server → Viewer | `token: string`, `host_id: string` |
| `pair-rejected` | Host → Server → Viewer | `reason: string` |
| `authenticate-failed` | Host → Server → Viewer | — |
| `release-peer` | Host → Server | — |

`join-session` additionally carries an optional `device_id: string`. `peer-joined`
now carries `device_id: string | null` and `token: string | null` so the host can
tell a code-entry join (`token` absent) from a token-based `authenticate` join.

A device's first successful `join-session` triggers a one-time terminal approval
prompt on the host (60-second timeout). Approval issues a token via `pair-approved`,
which the viewer stores and uses via `authenticate` on every later connection —
no code entry needed again. Rejection or timeout sends `pair-rejected` and
`release-peer`, freeing the session slot for someone else. An `authenticate` with
an invalid or unknown token gets `authenticate-failed` and the same release.

`pair-rejected` `reason` values: `"denied"` (user rejected the pairing prompt), or
`"missing-device-id"` (join-session had no device_id field).
