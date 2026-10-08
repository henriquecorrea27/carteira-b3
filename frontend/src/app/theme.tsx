import * as React from "react";

export type ThemePreference = "light" | "dark" | "system";

interface ThemeContextValue {
  preference: ThemePreference;
  resolved: "light" | "dark";
  setPreference: (p: ThemePreference) => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

function readStored(): ThemePreference {
  try {
    const v = localStorage.getItem("theme");
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

/** Applied synchronously (not in an effect) so components reading CSS variables see the new theme. */
function applyToDom(preference: ThemePreference) {
  const root = document.documentElement;
  if (preference === "system") delete root.dataset.theme;
  else root.dataset.theme = preference;
  try {
    if (preference === "system") localStorage.removeItem("theme");
    else localStorage.setItem("theme", preference);
  } catch {
    // Storage unavailable (private mode): the choice lasts for this session only.
  }
}

const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPref] = React.useState<ThemePreference>(readStored);
  const [systemDark, setSystemDark] = React.useState(() => media().matches);

  React.useEffect(() => {
    const m = media();
    const onChange = () => setSystemDark(m.matches);
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, []);

  const setPreference = React.useCallback((p: ThemePreference) => {
    applyToDom(p);
    setPref(p);
  }, []);

  const resolved = preference === "system" ? (systemDark ? "dark" : "light") : preference;
  const value = React.useMemo(() => ({ preference, resolved, setPreference }), [preference, resolved, setPreference]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}

/** Concrete values of CSS custom properties, for canvas charts; re-read when the theme changes. */
export function useCssVars<T extends string>(names: readonly T[]): Record<T, string> {
  const { resolved } = useTheme();
  const key = names.join("|");
  return React.useMemo(() => {
    void resolved;
    const style = getComputedStyle(document.documentElement);
    return Object.fromEntries(key.split("|").map((n) => [n, style.getPropertyValue(n).trim()])) as Record<T, string>;
  }, [key, resolved]);
}
