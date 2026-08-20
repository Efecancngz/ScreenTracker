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

    // The host also broadcasts monitor-list once, on its side of the
    // channel opening -- that's the fast path with zero extra round trips.
    // But this effect (and its message listener) only attaches after React
    // re-renders with a non-null channel, which happens asynchronously
    // after the channel actually opens. On a fast connection (e.g.
    // same-machine loopback) the host can already have sent and finished
    // sending that one-shot broadcast before this listener attaches --
    // RTCDataChannel doesn't buffer/replay messages for late listeners, so
    // it would be lost permanently. Proactively requesting the list here
    // covers both race orderings: request immediately if already open
    // (covers the host having already broadcast), and also request on the
    // channel's own "open" event (covers this effect attaching before the
    // underlying transport has actually opened yet).
    function requestMonitorList() {
      if (channel && channel.readyState === "open") {
        channel.send(JSON.stringify({ type: "request-monitor-list" }));
      }
    }

    channel.addEventListener("message", handleMessage);
    channel.addEventListener("open", requestMonitorList);
    if (channel.readyState === "open") requestMonitorList();

    return () => {
      channel.removeEventListener("message", handleMessage);
      channel.removeEventListener("open", requestMonitorList);
    };
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
