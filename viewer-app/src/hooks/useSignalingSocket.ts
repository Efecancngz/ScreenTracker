import { useCallback, useEffect, useRef, useState } from "react";

export type SignalingMessage = Record<string, unknown> & { type: string };

interface UseSignalingSocketResult {
  isConnected: boolean;
  lastMessage: SignalingMessage | null;
  send: (message: SignalingMessage) => void;
}

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 15000;

export function useSignalingSocket(url: string): UseSignalingSocketResult {
  const socketRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<SignalingMessage | null>(null);

  useEffect(() => {
    // A dropped WebSocket (mobile screen lock, backgrounding, a Wi-Fi/cell
    // handoff, a brief server blip) used to strand the viewer permanently —
    // nothing ever reconnected it, so the page just sat there with no video
    // and no way back short of a manual refresh. Reconnect with backoff
    // instead; unmountedRef stops that loop once the component goes away
    // rather than trying to reconnect a socket nobody wants anymore.
    let unmounted = false;
    let reconnectAttempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      const socket = new WebSocket(url);
      socketRef.current = socket;

      socket.onopen = () => {
        reconnectAttempt = 0;
        setIsConnected(true);
      };
      socket.onclose = () => {
        setIsConnected(false);
        if (unmounted) return;
        const delay = Math.min(
          RECONNECT_BASE_DELAY_MS * 2 ** reconnectAttempt,
          RECONNECT_MAX_DELAY_MS
        );
        reconnectAttempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };
      socket.onmessage = (event) => {
        setLastMessage(JSON.parse(event.data) as SignalingMessage);
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socketRef.current?.close();
    };
  }, [url]);

  const send = useCallback((message: SignalingMessage) => {
    socketRef.current?.send(JSON.stringify(message));
  }, []);

  return { isConnected, lastMessage, send };
}
