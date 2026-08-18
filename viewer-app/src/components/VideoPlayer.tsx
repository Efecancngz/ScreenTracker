import { useEffect, useRef, useState } from "react";
import { useInputControl } from "../hooks/useInputControl";
import styles from "./VideoPlayer.module.css";

interface VideoPlayerProps {
  stream: MediaStream | null;
  inputChannel: RTCDataChannel | null;
}

export function VideoPlayer({ stream, inputChannel }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [inputReady, setInputReady] = useState(inputChannel?.readyState === "open");

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  useInputControl({ videoRef, channel: inputChannel });

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
    <div className={styles.wrapper}>
      <video className={styles.video} ref={videoRef} autoPlay playsInline />
      <span className={inputReady ? `${styles.inputStatus} ${styles.inputReady}` : styles.inputStatus}>
        {inputReady ? "Input active" : "Input connecting…"}
      </span>
    </div>
  );
}
