/**
 * settingsThemeSync, the one place the current theme lives.
 *
 * Store-free on purpose: `ThemeToggle` and `settingsSlice` both read it, and
 * `appStore` imports `settingsSlice`, so this module must not import either of
 * them. It used to re-export the storage key from ThemeToggle, and every
 * `useTheme()` call held its own `useState`, so two menus could show two
 * different checked themes. Persisting to preferences.json is the settings
 * slice's job (`setThemePreference`), not this module's.
 */
import { create } from "zustand";

export type Theme = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "theme";

/** Reads the last applied theme; "system" when nothing usable is stored. */
export function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // localStorage 접근 실패 시 시스템 기본값 사용
  }
  return "system";
}

/** <html> 에 .dark 클래스를 적용한다. "system" 은 OS 설정을 따른다. */
export function applyThemeValue(theme: Theme): void {
  const resolved =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

interface ThemeState {
  theme: Theme;
  /** Applies and remembers the theme locally. Does not write preferences.json. */
  applyTheme: (next: Theme) => void;
}

export const useThemeStore = create<ThemeState>()((set) => ({
  theme: readStoredTheme(),
  applyTheme: (next) => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // 저장 실패해도 세션 내 동작 유지
    }
    applyThemeValue(next);
    set({ theme: next });
  },
}));
