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

Signaling server'dan tamamen bağımsız: bu mesajlar host ile viewer arasındaki
WebRTC bağlantısına eklenen `"input"` etiketli `RTCDataChannel` üzerinden,
JSON string olarak akar. Host bu kanalı offer'dan önce oluşturur (`aiortc`
`createDataChannel`), viewer `ondatachannel` event'iyle alır.

| Mesaj | Alanlar | Anlamı |
|---|---|---|
| `pointer-down` | `x, y` (0-1 normalize), `button: "left" \| "right"` | Basış başladı |
| `pointer-move` | `x, y` | Basılıyken hareket |
| `pointer-up` | `x, y`, `button` | Basış bitti |
| `wheel` | `deltaX, deltaY` | Scroll (tarayıcı `WheelEvent` değerleri, ham) |
| `key-down` | `key` (tarayıcı `KeyboardEvent.key` değeri) | Tuşa basıldı |
| `key-up` | `key` | Tuş bırakıldı |

Host, `x`/`y`'yi kendi ekran boyutuyla çarpıp gerçek piksele çevirir,
`[0, 1]` aralığına clamp'ler. Tık ile sürükleme host'ta ayrıca ayırt
edilmez — `pointer-down`/`pointer-move`/`pointer-up`'ın `pynput`
press/move/release çağrılarından kendiliğinden çıkar. Uzun basış (sağ tık),
viewer'da 500ms eşikle tespit edilip `button: "right"` olarak gönderilir.

Bilinmeyen veya bozuk (`JSON.parse` hatası veren) mesajlar host tarafında
sessizce atlanır; `pynput` çağrısı bir istisna fırlatırsa (örn. macOS'ta
Accessibility izni verilmemişse) host bunu bir kere loglar ve çalışmaya
devam eder — mesaj başına tekrar tekrar loglamaz.

Yetkilendirme: bu kanal, zaten kurulmuş bir WebRTC bağlantısı üzerinde —
yani zaten pairing onayından geçmiş bir cihaz için var. Ayrı bir input
onay adımı yok (bilinçli kapsam kararı, bkz. tasarım spec'i).
