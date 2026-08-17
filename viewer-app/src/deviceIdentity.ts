const DEVICE_ID_KEY = "screentracker_device_id";
const PAIRING_KEY = "screentracker_pairing";

export interface StoredPairing {
  hostId: string;
  token: string;
}

export function getOrCreateDeviceId(): string {
  const existing = localStorage.getItem(DEVICE_ID_KEY);
  if (existing) return existing;
  const id = crypto.randomUUID();
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
