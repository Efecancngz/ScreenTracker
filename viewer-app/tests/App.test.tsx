import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { storePairing } from "../src/deviceIdentity";

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

  emitOpen() {
    this.onopen?.();
  }

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
  localStorage.clear();
  vi.stubEnv("VITE_SIGNALING_SERVER_URL", "ws://localhost:8000/ws");
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  vi.stubGlobal("RTCPeerConnection", FakeRTCPeerConnection as unknown as typeof RTCPeerConnection);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("App", () => {
  it("shows a configuration error and opens no socket when the signaling URL is unset", () => {
    vi.stubEnv("VITE_SIGNALING_SERVER_URL", "");

    render(<App />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "VITE_SIGNALING_SERVER_URL is not set"
    );
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

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

  it("shows a human-readable error with the wait time when rate-limited", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");

    const socket = FakeWebSocket.instances[0];
    act(() =>
      socket.emitMessage({ type: "session-expired", reason: "rate-limited", retry_after_seconds: 4 })
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many attempts. Try again in 4 seconds."
    );
  });

  it("shows a human-readable error when the host disconnects", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");

    const socket = FakeWebSocket.instances[0];
    act(() => socket.emitMessage({ type: "peer-disconnected" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Host disconnected.");
  });

  it("auto-authenticates with a stored pairing instead of showing the join form", async () => {
    storePairing({ hostId: "host-1", token: "tok-1" });
    render(<App />);
    const socket = FakeWebSocket.instances[0];
    act(() => socket.emitOpen());

    expect(JSON.parse(socket.sent[0])).toMatchObject({
      type: "authenticate",
      host_id: "host-1",
      token: "tok-1",
    });
  });

  it("stores the pairing when pair-approved arrives", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");
    const socket = FakeWebSocket.instances[0];

    act(() => socket.emitMessage({ type: "pair-approved", token: "tok-2", host_id: "host-2" }));

    expect(JSON.parse(localStorage.getItem("screentracker_pairing")!)).toEqual({
      hostId: "host-2",
      token: "tok-2",
    });
  });

  it("shows a human-readable error when pairing is rejected", async () => {
    render(<App />);
    await joinWithCode("X7K2M9");
    const socket = FakeWebSocket.instances[0];

    act(() => socket.emitMessage({ type: "pair-rejected", reason: "denied" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Access denied by host.");
  });

  it("clears the stored pairing and falls back to the join form on authenticate-failed", async () => {
    storePairing({ hostId: "host-1", token: "stale-token" });
    render(<App />);
    const socket = FakeWebSocket.instances[0];
    act(() => socket.emitOpen());

    act(() => socket.emitMessage({ type: "authenticate-failed" }));

    expect(await screen.findByLabelText("Digit 1 of 6")).toBeInTheDocument();
  });
});
