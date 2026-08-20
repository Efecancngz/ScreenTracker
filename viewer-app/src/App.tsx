import { useCallback, useEffect, useRef, useState } from "react";
import { SessionJoinForm } from "./components/SessionJoinForm";
import { VideoPlayer } from "./components/VideoPlayer";
import { useSignalingSocket } from "./hooks/useSignalingSocket";
import { useWebRTCViewer } from "./hooks/useWebRTCViewer";
import { clearStoredPairing, getOrCreateDeviceId, getStoredPairing, storePairing } from "./deviceIdentity";
import styles from "./App.module.css";

type ViewerStatus = "idle" | "authenticating" | "joining" | "streaming" | "error";

// Matches the server's own RateLimiter (FAILURE_THRESHOLD=5 free failures)
// so this gives up right around when retrying blindly would start tripping
// it anyway, and backs off the same way the signaling socket's own
// reconnect does.
const NOT_FOUND_MAX_RETRIES = 5;
const NOT_FOUND_RETRY_BASE_DELAY_MS = 1000;
const NOT_FOUND_RETRY_MAX_DELAY_MS = 15000;

function sessionRejectedMessage(reason: string, retryAfterSeconds?: number): string {
  switch (reason) {
    case "expired":
      return "This session code has expired.";
    case "already-claimed":
      return "This session is already being viewed.";
    case "rate-limited": {
      const seconds = Math.ceil(retryAfterSeconds ?? 0);
      return `Too many attempts. Try again in ${seconds} second${seconds === 1 ? "" : "s"}.`;
    }
    default:
      return "Session code not found.";
  }
}

// When the viewer is built and served by the signaling server itself (the
// normal setup — see the background app / launcher), the websocket lives on
// the same origin the page was loaded from, so no configuration is needed.
// VITE_SIGNALING_SERVER_URL remains available to override this for cases
// where the two are served separately (e.g. `npm run dev` on its own port).
function resolveSignalingServerUrl(): string | undefined {
  const configured = import.meta.env.VITE_SIGNALING_SERVER_URL as string | undefined;
  if (configured) return configured;
  if (!window.location.host) return undefined;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}

export function App() {
  const signalingServerUrl = resolveSignalingServerUrl();

  if (!signalingServerUrl) {
    return (
      <div className={styles.shell}>
        <header className={styles.topBar}>
          <span className={styles.wordmark}>ScreenTracker</span>
        </header>
        <main className={styles.main}>
          <p className={styles.error} role="alert">
            Configuration error: could not determine the signaling server address. Set
            VITE_SIGNALING_SERVER_URL in .env and restart the dev server.
          </p>
        </main>
      </div>
    );
  }

  return <Viewer signalingServerUrl={signalingServerUrl} />;
}

function Viewer({ signalingServerUrl }: { signalingServerUrl: string }) {
  const [status, setStatus] = useState<ViewerStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Bumped whenever the connection needs to be renegotiated from scratch
  // (WebRTC can't reuse a single RTCPeerConnection against a different
  // remote peer) — forces useWebRTCViewer to build a fresh one.
  const [connectionGeneration, setConnectionGeneration] = useState(0);
  const { send, lastMessage, isConnected } = useSignalingSocket(signalingServerUrl);
  const deviceIdRef = useRef(getOrCreateDeviceId());
  const attemptedAutoAuthRef = useRef(false);
  // Distinguishes the very first connect (nothing to recover) from a
  // reconnect after the signaling socket dropped and came back — mobile
  // screen lock, a Wi-Fi/cell handoff, a brief server blip. Without this,
  // a reconnect used to leave the page showing a permanently dead video
  // with no error and no way back short of a manual refresh.
  const everConnectedRef = useRef(false);
  // How many consecutive "not-found" session-expired retries have fired --
  // see the session-expired case below. Bounded and backed off: a naive
  // zero-delay retry was observed live to fire a tight synchronous loop of
  // authenticate attempts whenever the race it targets took more than an
  // instant to resolve, tripping the SERVER's own rate limiter (5 free
  // failures) almost immediately and landing the viewer in a worse spot
  // (locked out) than not retrying at all.
  const notFoundRetryCountRef = useRef(0);

  const handleIceCandidate = useCallback(
    (candidate: RTCIceCandidate) => {
      send({ type: "ice-candidate", candidate: candidate.toJSON() });
    },
    [send]
  );

  const tryAutoAuthenticate = useCallback((): boolean => {
    const pairing = getStoredPairing();
    if (!pairing) return false;
    attemptedAutoAuthRef.current = true;
    setStatus("authenticating");
    setErrorMessage(null);
    send({
      type: "authenticate",
      host_id: pairing.hostId,
      device_id: deviceIdRef.current,
      token: pairing.token,
    });
    return true;
  }, [send]);

  const { remoteStream, handleOffer, handleRemoteIceCandidate, inputChannel } = useWebRTCViewer({
    onIceCandidate: handleIceCandidate,
    resetKey: connectionGeneration,
  });

  useEffect(() => {
    if (!isConnected) return;
    // A reconnect with a stored pairing: the old RTCPeerConnection (on both
    // ends) is likely stale or dead, so start the whole handshake over.
    if (everConnectedRef.current && getStoredPairing()) {
      attemptedAutoAuthRef.current = false;
      setConnectionGeneration((generation) => generation + 1);
    }
    everConnectedRef.current = true;
  }, [isConnected]);

  useEffect(() => {
    if (!isConnected || attemptedAutoAuthRef.current) return;
    tryAutoAuthenticate();
  }, [isConnected, tryAutoAuthenticate]);

  useEffect(() => {
    if (!lastMessage) return;

    switch (lastMessage.type) {
      case "offer":
        notFoundRetryCountRef.current = 0;
        void handleOffer(lastMessage.sdp as string).then((answerSdp) => {
          send({ type: "answer", sdp: answerSdp });
          setStatus("streaming");
        });
        break;
      case "ice-candidate":
        void handleRemoteIceCandidate(lastMessage.candidate as RTCIceCandidateInit);
        break;
      case "pair-approved":
        storePairing({
          hostId: lastMessage.host_id as string,
          token: lastMessage.token as string,
        });
        break;
      case "pair-rejected":
        setStatus("error");
        setErrorMessage("Access denied by host.");
        break;
      case "authenticate-failed":
        clearStoredPairing();
        attemptedAutoAuthRef.current = false;
        setStatus("idle");
        break;
      case "session-expired": {
        const reason = lastMessage.reason as string;
        // "not-found" from an auto-authenticate attempt usually means a
        // startup race, not a truly gone host: start.bat launches the
        // signaling server and host app together, so a reconnecting paired
        // viewer can authenticate before the host has finished
        // re-registering with a freshly restarted signaling server. The
        // host will be there moments later, so this gets retried too,
        // instead of a dead end that only a manual page refresh could
        // recover from -- but with backoff and a cap (see
        // notFoundRetryCountRef's declaration for why: a zero-delay retry
        // here tripped the server's own rate limiter almost instantly).
        if (
          reason === "not-found" &&
          getStoredPairing() &&
          notFoundRetryCountRef.current < NOT_FOUND_MAX_RETRIES
        ) {
          const delay = Math.min(
            NOT_FOUND_RETRY_BASE_DELAY_MS * 2 ** notFoundRetryCountRef.current,
            NOT_FOUND_RETRY_MAX_DELAY_MS
          );
          notFoundRetryCountRef.current += 1;
          setTimeout(() => tryAutoAuthenticate(), delay);
          break;
        }
        notFoundRetryCountRef.current = 0;
        setStatus("error");
        setErrorMessage(
          sessionRejectedMessage(reason, lastMessage.retry_after_seconds as number | undefined)
        );
        break;
      }
      case "peer-disconnected": {
        // The host's own connection dropped — its process restarted, its
        // network blipped, etc. The host app survives disconnects and
        // keeps its session alive, so a paired device retries automatically
        // instead of being left on a dead page; only show a dead-end error
        // when there's no stored pairing to retry with.
        notFoundRetryCountRef.current = 0;
        setConnectionGeneration((generation) => generation + 1);
        const willRetry = tryAutoAuthenticate();
        if (!willRetry) {
          setStatus("error");
          setErrorMessage("Host disconnected.");
        }
        break;
      }
    }
  }, [lastMessage, handleOffer, handleRemoteIceCandidate, send, tryAutoAuthenticate]);

  function handleJoin(sessionId: string) {
    setStatus("joining");
    setErrorMessage(null);
    send({ type: "join-session", session_id: sessionId, device_id: deviceIdRef.current });
  }

  const showJoinForm = status === "idle" || status === "joining";

  return (
    <div className={styles.shell}>
      <header className={styles.topBar}>
        <span className={styles.wordmark}>ScreenTracker</span>
        <span className={styles.status}>
          <span className={status === "streaming" ? `${styles.dot} ${styles.dotLive}` : styles.dot} />
          {status === "streaming" ? "LIVE" : status}
        </span>
      </header>
      <main className={styles.main}>
        {showJoinForm && <SessionJoinForm onJoin={handleJoin} />}
        {status === "authenticating" && <p className={styles.error}>Connecting with saved access…</p>}
        {errorMessage && (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        )}
        {status === "streaming" && <VideoPlayer stream={remoteStream} inputChannel={inputChannel} />}
      </main>
    </div>
  );
}
