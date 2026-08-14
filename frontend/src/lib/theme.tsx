"use client";

import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark";

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = "ss-theme";

/** Runs before React hydrates (see the inline script in layout.tsx), so by
 * the time this component mounts, document.documentElement already has the
 * correct class. We just read it back into React state here rather than
 * guessing again, which avoids a hydration flash/mismatch. */
function readInitialTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    setThemeState(readInitialTheme());
  }, []);

  const applyTheme = (t: Theme) => {
    document.documentElement.classList.toggle("dark", t === "dark");
    window.localStorage.setItem(STORAGE_KEY, t);
    setThemeState(t);
  };

  const setTheme = (t: Theme) => applyTheme(t);
  const toggleTheme = () => applyTheme(theme === "dark" ? "light" : "dark");

  return <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}

/** Inlined into <head> as a raw script (see layout.tsx) — must run
 * synchronously before first paint to avoid a flash of the wrong theme.
 * Priority: explicit user choice (localStorage) > OS preference > dark
 * (this product's original default). Wrapped in try/catch because
 * localStorage/matchMedia can throw in locked-down browser contexts
 * (private browsing in some older Safari versions, sandboxed iframes) —
 * a theme-detection failure must never block the page from rendering. */
export const NO_FLASH_THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem('${STORAGE_KEY}');
    var theme = stored === 'light' || stored === 'dark'
      ? stored
      : (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    document.documentElement.classList.toggle('dark', theme === 'dark');
  } catch (e) {
    document.documentElement.classList.add('dark');
  }
})();
`;
