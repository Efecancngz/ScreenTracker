import { useEffect, useRef, useState } from "react";
import { useInputControl } from "../hooks/useInputControl";
import styles from "./VideoPlayer.module.css";

interface VideoPlayerProps {
  stream: MediaStream | null;
  inputChannel: RTCDataChannel | null;
}

export function VideoPlayer({ stream, inputChannel }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [inputReady, setInputReady] = useState(inputChannel?.readyState === "open");
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  useInputControl({ videoRef, channel: inputChannel });

  useEffect(() => {
    function handleFullscreenChange() {
      setIsFullscreen(document.fullscreenElement === wrapperRef.current);
    }
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  async function toggleFullscreen() {
    // Fullscreening the wrapper (not the video element itself) keeps the
    // input-status badge and this button visible instead of handing the
    // whole screen to the browser's native video-fullscreen UI. Requires a
    // real user gesture (this click) — cannot be done automatically when
    // the stream starts. Optional chaining throughout: not implemented in
    // jsdom, and some browsers (notably iOS Safari for orientation lock, or
    // desktop browsers for either API) don't support one or both at all —
    // best-effort, silently do nothing where unsupported.
    if (document.fullscreenElement) {
      await document.exitFullscreen?.();
      await (screen.orientation as ScreenOrientation & { unlock?: () => void })?.unlock?.();
    } else {
      await wrapperRef.current?.requestFullscreen?.();
      // A remote desktop is inherently landscape-shaped; lock to it the way
      // a video app would, and swallow the rejection where unsupported
      // (desktop browsers, iOS Safari, or when this isn't running in
      // fullscreen) rather than letting it surface as an unhandled error.
      try {
        await screen.orientation?.lock?.("landscape");
      } catch {
        // Not supported here — the user can still rotate their device manually.
      }
    }
  }

  useEffect(() => {
    if (!inputChannel) {
      setInputReady(false);
      return;
    }
    setInputReady(inputChannel.readyState === "open");

    const handleOpen = () => setInputReady(true);
    const handleClose = () => setInputReady(false);
    inputChannel.addEventListener("open", handleOpen);
    inputChannel.addEventListener("close", handleClose);

    return () => {
      inputChannel.removeEventListener("open", handleOpen);
      inputChannel.removeEventListener("close", handleClose);
    };
  }, [inputChannel]);

  if (!stream) {
    return <p className={styles.waiting}>Waiting for host to start streaming…</p>;
  }

  return (
    <div className={styles.wrapper} ref={wrapperRef}>
      <video
        className={styles.video}
        ref={videoRef}
        autoPlay
        playsInline
        onContextMenu={(event) => event.preventDefault()}
      />
      <span className={inputReady ? `${styles.inputStatus} ${styles.inputReady}` : styles.inputStatus}>
        {inputReady ? "Input active" : "Input connecting…"}
      </span>
      <button type="button" className={styles.fullscreenButton} onClick={() => void toggleFullscreen()}>
        {isFullscreen ? "⤡ Exit fullscreen" : "⛶ Fullscreen"}
      </button>
    </div>
  );
}
