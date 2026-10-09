import { useSyncExternalStore } from "react";

/**
 * Privacy mode: blurs the portfolio's money amounts and quantities (elements with the `sensitive` class, see
 * index.css). Unit prices and percentages stay visible. Remembered per browser; the flag lives on <html> so the
 * CSS applies everywhere without re-rendering.
 */

const KEY = "privacy";
const listeners = new Set<() => void>();

function read(): boolean {
  try {
    return localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

let hidden = read();
apply(hidden);

function apply(value: boolean) {
  if (typeof document === "undefined") return;
  if (value) document.documentElement.dataset.privacy = "on";
  else delete document.documentElement.dataset.privacy;
}

export function setPrivacy(value: boolean) {
  hidden = value;
  apply(value);
  try {
    if (value) localStorage.setItem(KEY, "on");
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

export function usePrivacy(): [boolean, (value: boolean) => void] {
  return [useSyncExternalStore(subscribe, () => hidden), setPrivacy];
}
