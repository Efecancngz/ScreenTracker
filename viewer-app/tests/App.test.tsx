import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";

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

  close() {}

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

class FakeRTCPeerConnection {
  onicecandidate: unknown;
  ontrack: unknown;
  close() {}
}

async function joinWithCode(code: string) {
  for (let i = 0; i < code.length; i++) {
    await userEvent.type(screen.getByLabelText(`Digit ${i + 1} of 6`), code[i]);
  }
  await userEvent.click(screen.getByRole("button", { name: "Connect →" }));
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  vi.stubGlobal("RTCPeerConnection", FakeRTCPeerConnection as unknown as typeof RTCPeerConnection);
});

describe("App", () => {
  it("shows a human-readable error when the session has expired", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");

    const socket = FakeWebSocket.instances[0];
    act(() => socket.emitMessage({ type: "session-expired", reason: "expired" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This session code has expired."
    );
  });

  it("shows a human-readable error when the session is already claimed", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");

    const socket = FakeWebSocket.instances[0];
    act(() => socket.emitMessage({ type: "session-expired", reason: "already-claimed" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This session is already being viewed."
    );
  });

  it("shows a human-readable error when the host disconnects", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");

    const socket = FakeWebSocket.instances[0];
    act(() => socket.emitMessage({ type: "peer-disconnected" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Host disconnected.");
  });
});
