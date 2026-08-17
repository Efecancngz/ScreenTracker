import { useCallback, useEffect, useRef, useState } from "react";

export type SignalingMessage = Record<string, unknown> & { type: string };

interface UseSignalingSocketResult {
  isConnected: boolean;
  lastMessage: SignalingMessage | null;
  send: (message: SignalingMessage) => void;
}

export function useSignalingSocket(url: string): UseSignalingSocketResult {
  const socketRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<SignalingMessage | null>(null);

  useEffect(() => {
    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => setIsConnected(true);
    socket.onclose = () => setIsConnected(false);
    socket.onmessage = (event) => {
      setLastMessage(JSON.parse(event.data) as SignalingMessage);
    };

    return () => socket.close();
  }, [url]);

  const send = useCallback((message: SignalingMessage) => {
    socketRef.current?.send(JSON.stringify(message));
  }, []);

  return { isConnected, lastMessage, send };
}
