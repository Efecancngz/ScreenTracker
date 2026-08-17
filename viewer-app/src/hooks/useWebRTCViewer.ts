import { useEffect, useRef, useState } from "react";

interface UseWebRTCViewerOptions {
  onIceCandidate: (candidate: RTCIceCandidate) => void;
}

interface UseWebRTCViewerResult {
  remoteStream: MediaStream | null;
  handleOffer: (sdp: string) => Promise<string>;
  handleRemoteIceCandidate: (candidate: RTCIceCandidateInit) => Promise<void>;
}

export function useWebRTCViewer({
  onIceCandidate,
}: UseWebRTCViewerOptions): UseWebRTCViewerResult {
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);

  useEffect(() => {
    const pc = new RTCPeerConnection();
    pcRef.current = pc;

    pc.ontrack = (event) => setRemoteStream(event.streams[0]);
    pc.onicecandidate = (event) => {
      if (event.candidate) onIceCandidate(event.candidate);
    };

    return () => pc.close();
  }, [onIceCandidate]);

  async function handleOffer(sdp: string): Promise<string> {
    const pc = pcRef.current;
    if (!pc) throw new Error("Peer connection not ready");
    await pc.setRemoteDescription({ type: "offer", sdp });
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    if (!pc.localDescription) throw new Error("Failed to create local description");
    return pc.localDescription.sdp;
  }

  async function handleRemoteIceCandidate(candidate: RTCIceCandidateInit): Promise<void> {
    await pcRef.current?.addIceCandidate(candidate);
  }

  return { remoteStream, handleOffer, handleRemoteIceCandidate };
}
