# Architecture

## Components

```mermaid
graph LR
    Host["Host App<br/>(Python: aiortc + mss)"]
    Signal["Signaling Server<br/>(FastAPI + WebSocket)"]
    Turn["TURN Server<br/>(coturn)"]
    Viewer["Viewer Web App<br/>(React + WebRTC)"]

    Host -- "WebSocket: session mgmt,<br/>SDP/ICE exchange" --> Signal
    Viewer -- "WebSocket: session mgmt,<br/>SDP/ICE exchange" --> Signal
    Host -. "media stream<br/>(P2P veya relay)" .-> Turn
    Turn -. "media stream" .-> Viewer
    Host == "media stream (doğrudan P2P mümkünse)" ==> Viewer
```

## Session flow

```mermaid
sequenceDiagram
    participant H as Host App
    participant S as Signaling Server
    participant V as Viewer

    H->>S: create-session
    S-->>H: session_id (link/kod)
    V->>S: join-session(session_id)
    S-->>H: peer-joined
    H->>S: offer (SDP)
    S-->>V: offer (SDP)
    V->>S: answer (SDP)
    S-->>H: answer (SDP)
    H->>S: ice-candidate
    S-->>V: ice-candidate
    V->>S: ice-candidate
    S-->>H: ice-candidate
    Note over H,V: ICE tamamlanınca medya doğrudan veya TURN üzerinden akar
    H-->>V: video stream (WebRTC media)
```

## Decisions log

- **Native host app, not browser-based**: keeping the host process persistent (no browser tab dependency) and ready for Phase 2 OS-level input injection outweighed the simplicity of a pure browser-to-browser WebRTC app. See design spec for the rejected alternatives (pure-browser, Electron, from-scratch transport).
- **`aiortc` + `mss` over a from-scratch capture/encode pipeline**: WebRTC transport is a solved problem; only the signaling protocol is hand-rolled.
- **In-memory session store, no database**: Phase 1 has no requirement that survives a signaling server restart.
