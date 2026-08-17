import { useEffect, useRef } from "react";
import styles from "./VideoPlayer.module.css";

interface VideoPlayerProps {
  stream: MediaStream | null;
}

export function VideoPlayer({ stream }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  if (!stream) {
    return <p className={styles.waiting}>Waiting for host to start streaming…</p>;
  }

  return <video className={styles.video} ref={videoRef} autoPlay playsInline />;
}
