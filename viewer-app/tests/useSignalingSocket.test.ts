import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSignalingSocket } from "../src/hooks/useSignalingSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.onclose?.();
  }

  emitOpen() {
    this.onopen?.();
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
});

describe("useSignalingSocket", () => {
  it("reports connected once the socket opens", async () => {
    const { result } = renderHook(() => useSignalingSocket("ws://localhost/ws"));
    const socket = FakeWebSocket.instances[0];

    act(() => socket.emitOpen());

    await waitFor(() => expect(result.current.isConnected).toBe(true));
  });

  it("exposes the last parsed message", async () => {
    const { result } = renderHook(() => useSignalingSocket("ws://localhost/ws"));
    const socket = FakeWebSocket.instances[0];

    act(() => socket.emitMessage({ type: "peer-joined" }));

    await waitFor(() => expect(result.current.lastMessage).toEqual({ type: "peer-joined" }));
  });

  it("serializes messages sent through send()", () => {
    const { result } = renderHook(() => useSignalingSocket("ws://localhost/ws"));
    const socket = FakeWebSocket.instances[0];

    act(() => result.current.send({ type: "join-session", session_id: "abc" }));

    expect(socket.sent).toEqual([JSON.stringify({ type: "join-session", session_id: "abc" })]);
  });

  describe("reconnection", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it("reconnects with backoff after the socket closes unexpectedly", async () => {
      const { result } = renderHook(() => useSignalingSocket("ws://localhost/ws"));
      act(() => FakeWebSocket.instances[0].emitOpen());
      expect(result.current.isConnected).toBe(true);

      act(() => FakeWebSocket.instances[0].close());
      expect(result.current.isConnected).toBe(false);
      expect(FakeWebSocket.instances).toHaveLength(1); // not yet — waiting out the backoff

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });

      expect(FakeWebSocket.instances).toHaveLength(2);
      act(() => FakeWebSocket.instances[1].emitOpen());
      expect(result.current.isConnected).toBe(true);
    });

    it("does not reconnect after the hook unmounts", async () => {
      const { unmount } = renderHook(() => useSignalingSocket("ws://localhost/ws"));
      act(() => FakeWebSocket.instances[0].emitOpen());

      unmount();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(20000);
      });

      expect(FakeWebSocket.instances).toHaveLength(1);
    });
  });
});
