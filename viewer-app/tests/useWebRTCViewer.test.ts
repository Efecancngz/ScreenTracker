import { afterEach, describe, expect, it, vi } from "vitest";
import { buildIceServers } from "../src/hooks/useWebRTCViewer";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("buildIceServers", () => {
  it("falls back to the public STUN server when TURN is not configured", () => {
    vi.stubEnv("VITE_TURN_SERVER_URL", "");
    vi.stubEnv("VITE_TURN_USERNAME", "");
    vi.stubEnv("VITE_TURN_PASSWORD", "");

    expect(buildIceServers()).toEqual([{ urls: "stun:stun.l.google.com:19302" }]);
  });

  it("appends the TURN relay when all TURN vars are set", () => {
    vi.stubEnv("VITE_TURN_SERVER_URL", "turn:turn.example.com:3478");
    vi.stubEnv("VITE_TURN_USERNAME", "screentracker");
    vi.stubEnv("VITE_TURN_PASSWORD", "s3cret");

    expect(buildIceServers()).toEqual([
      { urls: "stun:stun.l.google.com:19302" },
      {
        urls: "turn:turn.example.com:3478",
        username: "screentracker",
        credential: "s3cret",
      },
    ]);
  });
});
