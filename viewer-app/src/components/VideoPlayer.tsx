import { useEffect, useRef } from "react";
import { useInputControl } from "../hooks/useInputControl";
import styles from "./VideoPlayer.module.css";

interface VideoPlayerProps {
  stream: MediaStream | null;
  inputChannel: RTCDataChannel | null;
}

export function VideoPlayer({ stream, inputChannel }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  useInputControl({ videoRef, channel: inputChannel });

  if (!stream) {
    return <p className={styles.waiting}>Waiting for host to start streaming…</p>;
  }

  const inputReady = inputChannel?.readyState === "open";

  return (
    <div className={styles.wrapper}>
      <video className={styles.video} ref={videoRef} autoPlay playsInline />
      <span className={inputReady ? `${styles.inputStatus} ${styles.inputReady}` : styles.inputStatus}>
        {inputReady ? "Input active" : "Input connecting…"}
      </span>
    </div>
  );
}
