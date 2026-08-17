import { useCallback, useEffect, useState } from "react";
import { SessionJoinForm } from "./components/SessionJoinForm";
import { VideoPlayer } from "./components/VideoPlayer";
import { useSignalingSocket } from "./hooks/useSignalingSocket";
import { useWebRTCViewer } from "./hooks/useWebRTCViewer";
import styles from "./App.module.css";

type ViewerStatus = "idle" | "joining" | "streaming" | "error";

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

export function App() {
  const signalingServerUrl = import.meta.env.VITE_SIGNALING_SERVER_URL as string | undefined;

  if (!signalingServerUrl) {
    return (
      <div className={styles.shell}>
        <header className={styles.topBar}>
          <span className={styles.wordmark}>ScreenTracker</span>
        </header>
        <main className={styles.main}>
          <p className={styles.error} role="alert">
            Configuration error: VITE_SIGNALING_SERVER_URL is not set. Copy .env.example to
            .env in the repository root and restart the dev server.
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
  const { send, lastMessage } = useSignalingSocket(signalingServerUrl);

  const handleIceCandidate = useCallback(
    (candidate: RTCIceCandidate) => {
      send({ type: "ice-candidate", candidate: candidate.toJSON() });
    },
    [send]
  );

  const { remoteStream, handleOffer, handleRemoteIceCandidate } = useWebRTCViewer({
    onIceCandidate: handleIceCandidate,
  });

  useEffect(() => {
    if (!lastMessage) return;

    switch (lastMessage.type) {
      case "offer":
        void handleOffer(lastMessage.sdp as string).then((answerSdp) => {
          send({ type: "answer", sdp: answerSdp });
          setStatus("streaming");
        });
        break;
      case "ice-candidate":
        void handleRemoteIceCandidate(lastMessage.candidate as RTCIceCandidateInit);
        break;
      case "session-expired":
        setStatus("error");
        setErrorMessage(
          sessionRejectedMessage(
            lastMessage.reason as string,
            lastMessage.retry_after_seconds as number | undefined
          )
        );
        break;
      case "peer-disconnected":
        setStatus("error");
        setErrorMessage("Host disconnected.");
        break;
    }
  }, [lastMessage, handleOffer, handleRemoteIceCandidate, send]);

  function handleJoin(sessionId: string) {
    setStatus("joining");
    setErrorMessage(null);
    send({ type: "join-session", session_id: sessionId });
  }

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
        {status !== "streaming" && <SessionJoinForm onJoin={handleJoin} />}
        {errorMessage && (
          <p className={styles.error} role="alert">
            {errorMessage}
          </p>
        )}
        {status === "streaming" && <VideoPlayer stream={remoteStream} />}
      </main>
    </div>
  );
}
