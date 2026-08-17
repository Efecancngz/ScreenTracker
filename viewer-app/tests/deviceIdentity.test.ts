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
