import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMonitorSelection } from "../src/hooks/useMonitorSelection";

class FakeDataChannel extends EventTarget {
  readyState: RTCDataChannelState;
  send = vi.fn();

  constructor(readyState: RTCDataChannelState = "open") {
    super();
    this.readyState = readyState;
  }

  receive(payload: unknown) {
    this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(payload) }));
  }
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useMonitorSelection", () => {
  it("starts with no monitors and no active index", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    expect(result.current.monitors).toEqual([]);
    expect(result.current.activeIndex).toBeNull();
  });

  it("stores the monitor list and defaults the active index to the first monitor", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.receive({
        type: "monitor-list",
        monitors: [
          { index: 1, width: 1920, height: 1080, left: 0, top: 0 },
          { index: 2, width: 1280, height: 720, left: 1920, top: 0 },
        ],
      });
    });

    expect(result.current.monitors).toHaveLength(2);
    expect(result.current.activeIndex).toBe(1);
  });

  it("ignores messages of other types", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.receive({ type: "pointer-down", x: 0.5, y: 0.5, button: "left" });
    });

    expect(result.current.monitors).toEqual([]);
  });

  it("ignores unparseable message data", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.dispatchEvent(new MessageEvent("message", { data: "not valid json" }));
    });

    expect(result.current.monitors).toEqual([]);
  });

  it("selectMonitor sends a select-monitor message and updates activeIndex optimistically", () => {
    const channel = new FakeDataChannel();
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.receive({
        type: "monitor-list",
        monitors: [
          { index: 1, width: 1920, height: 1080, left: 0, top: 0 },
          { index: 2, width: 1280, height: 720, left: 1920, top: 0 },
        ],
      });
    });

    act(() => {
      result.current.selectMonitor(2);
    });

    expect(channel.send).toHaveBeenCalledWith(JSON.stringify({ type: "select-monitor", index: 2 }));
    expect(result.current.activeIndex).toBe(2);
  });

  it("selectMonitor does nothing when the channel isn't open", () => {
    const channel = new FakeDataChannel("connecting");
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      result.current.selectMonitor(2);
    });

    expect(channel.send).not.toHaveBeenCalled();
  });

  it("sends request-monitor-list immediately when the channel is already open on mount", () => {
    const channel = new FakeDataChannel("open");
    renderHook(() => useMonitorSelection(channel as unknown as RTCDataChannel));

    expect(channel.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "request-monitor-list" })
    );
  });

  it("sends request-monitor-list when the channel opens after mount", () => {
    const channel = new FakeDataChannel("connecting");
    renderHook(() => useMonitorSelection(channel as unknown as RTCDataChannel));

    expect(channel.send).not.toHaveBeenCalled();

    act(() => {
      channel.readyState = "open";
      channel.dispatchEvent(new Event("open"));
    });

    expect(channel.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "request-monitor-list" })
    );
  });

  it("populates monitors from a monitor-list received after a request-monitor-list race", () => {
    const channel = new FakeDataChannel("connecting");
    const { result } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    act(() => {
      channel.readyState = "open";
      channel.dispatchEvent(new Event("open"));
    });
    expect(channel.send).toHaveBeenCalledWith(
      JSON.stringify({ type: "request-monitor-list" })
    );

    act(() => {
      channel.receive({
        type: "monitor-list",
        monitors: [{ index: 1, width: 1920, height: 1080, left: 0, top: 0 }],
      });
    });

    expect(result.current.monitors).toHaveLength(1);
    expect(result.current.activeIndex).toBe(1);
  });

  it("removes both the message and open listeners on cleanup", () => {
    const channel = new FakeDataChannel();
    const removeSpy = vi.spyOn(channel, "removeEventListener");
    const { unmount } = renderHook(() =>
      useMonitorSelection(channel as unknown as RTCDataChannel)
    );

    unmount();

    expect(removeSpy).toHaveBeenCalledWith("message", expect.any(Function));
    expect(removeSpy).toHaveBeenCalledWith("open", expect.any(Function));
  });

  it("resets to no monitors when the channel becomes null", () => {
    const channel = new FakeDataChannel();
    const { result, rerender } = renderHook(
      ({ ch }: { ch: RTCDataChannel | null }) => useMonitorSelection(ch),
      { initialProps: { ch: channel as unknown as RTCDataChannel } }
    );

    act(() => {
      channel.receive({
        type: "monitor-list",
        monitors: [{ index: 1, width: 1920, height: 1080, left: 0, top: 0 }],
      });
    });
    expect(result.current.monitors).toHaveLength(1);

    rerender({ ch: null });

    expect(result.current.monitors).toEqual([]);
    expect(result.current.activeIndex).toBeNull();
  });
});
