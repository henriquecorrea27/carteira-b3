import { useSyncExternalStore } from "react";

/**
 * Active profile (an independent portfolio, each in its own database on the backend). Sent as the X-Profile
 * header on every API call; null → the backend's first profile. Remembered per browser.
 */

const KEY = "profile";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

let current = read();

export function currentProfileId(): string | null {
  return current;
}

export function setProfileId(id: string | null) {
  current = id;
  try {
    if (id) localStorage.setItem(KEY, id);
    else localStorage.removeItem(KEY);
  } catch {
    // Storage unavailable: lasts for this session only
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useProfileId(): string | null {
  return useSyncExternalStore(subscribe, currentProfileId, currentProfileId);
}
