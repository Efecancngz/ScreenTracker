import { useCallback, useEffect, useState } from "react";

export interface MonitorInfo {
  index: number;
  width: number;
  height: number;
  left: number;
  top: number;
}

interface UseMonitorSelectionResult {
  monitors: MonitorInfo[];
  activeIndex: number | null;
  selectMonitor: (index: number) => void;
}

// Listens on the same "input" RTCDataChannel useInputControl already sends
// on -- the host broadcasts monitor-list once on channel open, this hook
// just needs a message listener, not a separate channel.
export function useMonitorSelection(channel: RTCDataChannel | null): UseMonitorSelectionResult {
  const [monitors, setMonitors] = useState<MonitorInfo[]>([]);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  useEffect(() => {
    setMonitors([]);
    setActiveIndex(null);
    if (!channel) return;

    function handleMessage(event: Event) {
      const data = (event as MessageEvent).data;
      let payload: { type?: string; monitors?: MonitorInfo[] };
      try {
        payload = JSON.parse(data);
      } catch {
        return;
      }
      if (payload.type !== "monitor-list" || !Array.isArray(payload.monitors)) return;
      setMonitors(payload.monitors);
      setActiveIndex(payload.monitors[0]?.index ?? null);
    }

    channel.addEventListener("message", handleMessage);
    return () => channel.removeEventListener("message", handleMessage);
  }, [channel]);

  const selectMonitor = useCallback(
    (index: number) => {
      if (!channel || channel.readyState !== "open") return;
      channel.send(JSON.stringify({ type: "select-monitor", index }));
      setActiveIndex(index);
    },
    [channel]
  );

  return { monitors, activeIndex, selectMonitor };
}
