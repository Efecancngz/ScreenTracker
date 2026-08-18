import { useCallback, useEffect, useRef, useState } from "react";

// A public STUN server is enough for most NATs; TURN is the relay fallback for
// the symmetric-NAT cases where no direct path can be found.
const STUN_SERVER_URL = "stun:stun.l.google.com:19302";

export function buildIceServers(): RTCIceServer[] {
  const iceServers: RTCIceServer[] = [{ urls: STUN_SERVER_URL }];

  const turnUrl = import.meta.env.VITE_TURN_SERVER_URL as string | undefined;
  const turnUsername = import.meta.env.VITE_TURN_USERNAME as string | undefined;
  const turnPassword = import.meta.env.VITE_TURN_PASSWORD as string | undefined;
  if (turnUrl && turnUsername && turnPassword) {
    iceServers.push({ urls: turnUrl, username: turnUsername, credential: turnPassword });
  }

  return iceServers;
}

interface UseWebRTCViewerOptions {
  onIceCandidate: (candidate: RTCIceCandidate) => void;
}

interface UseWebRTCViewerResult {
  remoteStream: MediaStream | null;
  handleOffer: (sdp: string) => Promise<string>;
  handleRemoteIceCandidate: (candidate: RTCIceCandidateInit) => Promise<void>;
  inputChannel: RTCDataChannel | null;
}

export function useWebRTCViewer({
  onIceCandidate,
}: UseWebRTCViewerOptions): UseWebRTCViewerResult {
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [inputChannel, setInputChannel] = useState<RTCDataChannel | null>(null);

  useEffect(() => {
    const pc = new RTCPeerConnection({ iceServers: buildIceServers() });
    pcRef.current = pc;

    pc.ontrack = (event) => setRemoteStream(event.streams[0]);
    pc.onicecandidate = (event) => {
      if (event.candidate) onIceCandidate(event.candidate);
    };
    pc.ondatachannel = (event) => setInputChannel(event.channel);

    return () => pc.close();
  }, [onIceCandidate]);

  const handleOffer = useCallback(async (sdp: string): Promise<string> => {
    const pc = pcRef.current;
    if (!pc) throw new Error("Peer connection not ready");
    await pc.setRemoteDescription({ type: "offer", sdp });
    const answer = await pc.createAnswer();
    await pc.setLocalDescription(answer);
    if (!pc.localDescription) throw new Error("Failed to create local description");
    return pc.localDescription.sdp;
  }, []);

  const handleRemoteIceCandidate = useCallback(async (candidate: RTCIceCandidateInit): Promise<void> => {
    await pcRef.current?.addIceCandidate(candidate);
  }, []);

  return { remoteStream, handleOffer, handleRemoteIceCandidate, inputChannel };
}
