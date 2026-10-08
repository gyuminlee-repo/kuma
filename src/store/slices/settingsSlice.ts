/**
 * settingsSlice — Phase 3 전역 설정 Zustand 슬라이스.
 *
 * IPC settings_load / settings_save 를 통해 ~/.kuma/preferences.json 과 동기화.
 * theme: ThemeToggle 의 "system" ↔ backend SettingsBundle 의 "auto" 간 변환 포함.
 */
import type { StateCreator } from "zustand";
import { sendRequest } from "../../lib/ipc-kuro";
import type { SettingsBundle } from "../../types/models.generated";
import type { SettingsSlice } from "../slice-interfaces";
import type { AppState } from "../types";
import { useThemeStore, type Theme } from "../settingsThemeSync";

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
  contactEmailResolution: null,

  loadSettings: async () => {
    set({ isLoading: true });
    try {
      const response = await sendRequest("settings_load", {});
      const bundle = response.settings;

      // offlineMode 동기화: settingsSlice → networkConsentSlice. 저장을 일으키지
      // 않는 원시 setter 를 쓴다. 방금 읽은 값을 다시 쓸 이유가 없다.
      const state = get();
      if (typeof state.setOfflineMode === "function" && bundle.network?.offline_mode !== undefined) {
        state.setOfflineMode(bundle.network.offline_mode);
      }

      set({
        settings: bundle,
        isDirty: false,
        isLoading: false,
        contactEmailResolution: response.contact_email_source
          ? {
              email: response.effective_contact_email ?? null,
              source: response.contact_email_source,
            }
          : null,
      });

      // theme 동기화: backend "auto" → ThemeToggle "system". 번들을 먼저 둔 뒤에
      // 적용하므로 이 호출은 저장을 일으키지 않는다(applyTheme 은 로컬 전용).
      // bundle.theme 이 undefined 이면 기존 localStorage 값을 보존한다 (업그레이드 안전).
      if (bundle.theme !== undefined) {
        useThemeStore.getState().applyTheme(mapThemeFromBundle(bundle.theme));
      }
    } catch {
      // 로드 실패 시 빈 기본값으로 초기화 (오프라인 또는 첫 실행). 이후 저장은
      // 바뀐 필드만 담지만 사이드카가 기존 파일 위에 병합하므로 다른 값을 잃지 않는다.
      set({ settings: {}, isDirty: false, isLoading: false });
    }
  },

  setThemePreference: (next: Theme) => {
    useThemeStore.getState().applyTheme(next);
    const bundleTheme = mapThemeToBundle(next);
    if (get().settings?.theme !== bundleTheme) {
      get().updateSettings({ theme: bundleTheme });
    }
  },

  setOfflinePreference: (value: boolean) => {
    get().setOfflineMode(value);
    get().updateSettings({ network: { ...get().settings?.network, offline_mode: value } });
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
      await sendRequest("settings_save", { settings });
      set({ isDirty: false, lastSavedAt: Date.now() });
    } catch {
      // 저장 실패는 무시 (다음 변경에 재시도)
    }
  },

  resetDirty: () => set({ isDirty: false }),
});
