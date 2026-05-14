/**
 * settingsSlice — Phase 3 전역 설정 Zustand 슬라이스.
 *
 * IPC settings_load / settings_save 를 통해 ~/.kuma/preferences.json 과 동기화.
 * theme: ThemeToggle 의 "system" ↔ backend SettingsBundle 의 "auto" 간 변환 포함.
 */
import type { StateCreator } from "zustand";
import { rpc } from "../../lib/ipc";
import type { SettingsBundle } from "../../types/models.generated";
import type { SettingsSlice } from "../slice-interfaces";
import type { AppState } from "../types";
import { THEME_STORAGE_KEY, applyThemeValue } from "../settingsThemeSync";

export type { SettingsSlice, SettingsBundle };

let debounceTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * ThemeToggle 의 "system" 값을 backend 의 "auto" 로 변환.
 * 반대 방향(auto → system)도 처리.
 */
export function mapThemeToBundle(theme: string): "light" | "dark" | "auto" {
  if (theme === "system") return "auto";
  if (theme === "light" || theme === "dark") return theme;
  return "auto";
}

export function mapThemeFromBundle(theme: "light" | "dark" | "auto" | undefined): "light" | "dark" | "system" {
  if (theme === "auto") return "system";
  if (theme === "light" || theme === "dark") return theme;
  return "system";
}

export const createSettingsSlice: StateCreator<
  AppState,
  [],
  [],
  SettingsSlice
> = (set, get) => ({
  settings: null,
  isDirty: false,
  isLoading: false,
  lastSavedAt: null,

  loadSettings: async () => {
    set({ isLoading: true });
    try {
      const response = await rpc<{ settings: SettingsBundle }>("kuro", "settings_load", {});
      const bundle = response.settings;

      // theme 동기화: backend "auto" → ThemeToggle "system"
      const mappedTheme = mapThemeFromBundle(bundle.theme);
      try {
        localStorage.setItem(THEME_STORAGE_KEY, mappedTheme);
        applyThemeValue(mappedTheme);
      } catch {
        // localStorage 불가 환경
      }

      // offlineMode 동기화: settingsSlice → networkConsentSlice
      const state = get();
      if (typeof state.setOfflineMode === "function" && bundle.network?.offline_mode !== undefined) {
        state.setOfflineMode(bundle.network.offline_mode);
      }

      set({ settings: bundle, isDirty: false, isLoading: false });
    } catch {
      // 로드 실패 시 빈 기본값으로 초기화 (오프라인 또는 첫 실행)
      set({ settings: {}, isDirty: false, isLoading: false });
    }
  },

  updateSettings: (partial: Partial<SettingsBundle>) => {
    const current = get().settings ?? {};
    const next: SettingsBundle = {
      ...current,
      ...partial,
      // 중첩 객체 병합
      network: partial.network !== undefined
        ? { ...current.network, ...partial.network }
        : current.network,
      sidecar: partial.sidecar !== undefined
        ? { ...current.sidecar, ...partial.sidecar }
        : current.sidecar,
      telemetry: partial.telemetry !== undefined
        ? { ...current.telemetry, ...partial.telemetry }
        : current.telemetry,
    };
    set({ settings: next, isDirty: true });

    // debounce 500ms 후 자동 저장
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      void get().saveSettings();
    }, 500);
  },

  saveSettings: async () => {
    const { settings } = get();
    if (!settings) return;
    try {
      await rpc<{ ok: boolean; path: string }>("kuro", "settings_save", { settings });
      set({ isDirty: false, lastSavedAt: Date.now() });
    } catch {
      // 저장 실패는 무시 (다음 변경에 재시도)
    }
  },

  resetDirty: () => set({ isDirty: false }),
});
