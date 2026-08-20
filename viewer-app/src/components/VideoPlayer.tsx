import { useEffect, useRef, useState } from "react";
import { useInputControl, type PrimaryButton } from "../hooks/useInputControl";
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
  // Which button single-finger press/drag/release simulates. An explicit
  // mode toggle instead of inferring intent from touch timing/finger count
  // -- simpler to use and to reason about than the two-finger-hold gesture
  // this replaced.
  const [primaryButton, setPrimaryButton] = useState<PrimaryButton>("left");

  useEffect(() => {
    if (!videoRef.current) return;
    videoRef.current.srcObject = stream;
    if (stream) {
      // The autoPlay attribute alone isn't reliable for a stream attached
      // programmatically after mount -- call play() explicitly. Muted (see
      // below), so this is never blocked by the autoplay policy; catch is
      // just to avoid an unhandled rejection if the element unmounts mid-call.
      videoRef.current.play?.()?.catch(() => {});
    }
  }, [stream]);

  useInputControl({ videoRef, channel: inputChannel, primaryButton });

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
        // The host's capture track never carries audio, so muting costs
        // nothing here -- and it's required: Chrome's autoplay policy
        // blocks an unmuted <video autoPlay> with NotAllowedError unless a
        // user gesture just happened, even when the stream has no audio
        // track at all. Confirmed live: the stream attached correctly
        // (readyState 4, right dimensions) but stayed paused at
        // currentTime 0 -- a black screen with a perfectly healthy stream,
        // which also explains why touch input kept working underneath it.
        muted
        draggable={false}
        onDragStart={(event) => event.preventDefault()}
        onContextMenu={(event) => event.preventDefault()}
      />
      <span className={inputReady ? `${styles.inputStatus} ${styles.inputReady}` : styles.inputStatus}>
        {inputReady ? "Input active" : "Input connecting…"}
      </span>
      <button
        type="button"
        className={styles.modeButton}
        onClick={() => setPrimaryButton((prev) => (prev === "left" ? "right" : "left"))}
      >
        {primaryButton === "left" ? "🖱️ Left-click mode" : "🖱️ Right-click mode"}
      </button>
      <button type="button" className={styles.fullscreenButton} onClick={() => void toggleFullscreen()}>
        {isFullscreen ? "⤡ Exit fullscreen" : "⛶ Fullscreen"}
      </button>
    </div>
  );
}
