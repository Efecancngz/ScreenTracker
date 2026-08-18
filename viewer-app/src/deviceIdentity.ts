const DEVICE_ID_KEY = "screentracker_device_id";
const PAIRING_KEY = "screentracker_pairing";

export interface StoredPairing {
  hostId: string;
  token: string;
}

// crypto.randomUUID() only exists in secure contexts (HTTPS or localhost).
// Opening the viewer from a phone over plain HTTP via a LAN IP — the normal
// way to reach it during local testing — is not a secure context, so the
// browser omits randomUUID entirely. crypto.getRandomValues() has no such
// restriction, so build a UUIDv4 from it by hand as a fallback.
function generateDeviceId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();

  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function getOrCreateDeviceId(): string {
  const existing = localStorage.getItem(DEVICE_ID_KEY);
  if (existing) return existing;
  const id = generateDeviceId();
  localStorage.setItem(DEVICE_ID_KEY, id);
  return id;
}

export function getStoredPairing(): StoredPairing | null {
  const raw = localStorage.getItem(PAIRING_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredPairing;
  } catch {
    return null;
  }
}

export function storePairing(pairing: StoredPairing): void {
  localStorage.setItem(PAIRING_KEY, JSON.stringify(pairing));
}

export function clearStoredPairing(): void {
  localStorage.removeItem(PAIRING_KEY);
}
