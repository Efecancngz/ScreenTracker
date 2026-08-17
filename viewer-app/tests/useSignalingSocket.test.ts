import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
});
