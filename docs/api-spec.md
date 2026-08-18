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

## Input control (WebRTC DataChannel)

Fully independent of the signaling server: these messages flow as JSON
strings over an `"input"`-labeled `RTCDataChannel` added to the existing
WebRTC connection between host and viewer. The host creates this channel
before the offer (`aiortc` `createDataChannel`); the viewer receives it via
the `ondatachannel` event.

| Message | Fields | Meaning |
|---|---|---|
| `pointer-down` | `x, y` (0-1 normalized), `button: "left" \| "right"` | Press started |
| `pointer-move` | `x, y` | Movement while pressed |
| `pointer-up` | `x, y`, `button` | Press ended |
| `wheel` | `deltaX, deltaY` | Scroll (raw browser `WheelEvent` values) |
| `key-down` | `key` (browser `KeyboardEvent.key` value) | Key pressed |
| `key-up` | `key` | Key released |

The host multiplies `x`/`y` by its own screen size to convert to real
pixels, clamping to `[0, 1]` first. Click-and-drag is not distinguished as
a separate message on the host side — it falls out naturally from the
`pynput` press/move/release calls driven by
`pointer-down`/`pointer-move`/`pointer-up`. A long press (right-click) is
detected on the viewer with a 500ms threshold and sent as
`button: "right"`.

Unknown or malformed messages (a `json.loads` parse failure) are silently
dropped on the host side; if a `pynput` call raises an exception (e.g. on
macOS when Accessibility permission hasn't been granted), the host logs it
once and keeps running — it does not log repeatedly per message.

Authorization: this channel exists on top of an already-established WebRTC
connection — i.e. for a device that has already passed pairing approval.
There is no separate input approval step (a deliberate scope decision, see
the design spec).
