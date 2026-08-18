import { beforeEach, describe, expect, it } from "vitest";
import {
  clearStoredPairing,
  getOrCreateDeviceId,
  getStoredPairing,
  storePairing,
} from "../src/deviceIdentity";

beforeEach(() => {
  localStorage.clear();
});

describe("getOrCreateDeviceId", () => {
  it("creates and persists a device id on first call", () => {
    const id = getOrCreateDeviceId();
    expect(id).toBeTruthy();
    expect(getOrCreateDeviceId()).toBe(id);
  });

  it("still creates a device id when crypto.randomUUID is unavailable", () => {
    // crypto.randomUUID only exists in secure contexts (HTTPS or localhost).
    // Opening the viewer over plain HTTP via a LAN IP — the normal way to
    // reach it from a phone during local testing — is not a secure context,
    // so the browser omits randomUUID entirely.
    const original = crypto.randomUUID;
    // @ts-expect-error - simulating a browser without this API (assignment,
    // not delete: randomUUID lives on the prototype, so delete is a no-op)
    crypto.randomUUID = undefined;
    try {
      const id = getOrCreateDeviceId();
      expect(id).toBeTruthy();
      expect(getOrCreateDeviceId()).toBe(id);
    } finally {
      crypto.randomUUID = original;
    }
  });
});

describe("stored pairing", () => {
  it("returns null when nothing is stored", () => {
    expect(getStoredPairing()).toBeNull();
  });

  it("round-trips a stored pairing", () => {
    storePairing({ hostId: "host-1", token: "tok-1" });
    expect(getStoredPairing()).toEqual({ hostId: "host-1", token: "tok-1" });
  });

  it("clears a stored pairing", () => {
    storePairing({ hostId: "host-1", token: "tok-1" });
    clearStoredPairing();
    expect(getStoredPairing()).toBeNull();
  });

  it("treats corrupted stored JSON as no pairing", () => {
    localStorage.setItem("screentracker_pairing", "{not-json");
    expect(getStoredPairing()).toBeNull();
  });
});
