import type { StateCreator } from "zustand";
import type { AppState } from "../types";
import type { NetworkConsentSlice, NetworkService } from "../slice-interfaces";
export type { NetworkConsentSlice, NetworkService };

import {
  loadNetworkSettings,
  saveNetworkSettings,
} from "../../lib/networkSettings";

/**
 * 동의 모달의 Promise resolver 를 외부에서 resolve/reject 할 수 있도록 보관.
 * 모달 확인/취소 액션이 이를 호출한다.
 */
let pendingResolver: ((granted: boolean) => void) | null = null;

export const createNetworkConsentSlice: StateCreator<
  AppState,
  [],
  [],
  NetworkConsentSlice
> = (set, get) => ({
  networkConsentGranted: false,
  offlineMode: false,
  networkConsentPending: false,

  loadNetworkConsentSettings: () => {
    const settings = loadNetworkSettings();
    set({
      networkConsentGranted: settings.networkConsentGranted,
      offlineMode: settings.offlineMode,
    });
  },

  grantNetworkConsent: () => {
    const resolver = pendingResolver;
    pendingResolver = null;

    const settings = loadNetworkSettings();
    saveNetworkSettings({
      ...settings,
      networkConsentGranted: true,
      networkConsentTimestamp: new Date().toISOString(),
    });
    set({ networkConsentGranted: true, networkConsentPending: false });
    resolver?.(true);
  },

  denyNetworkConsent: () => {
    const resolver = pendingResolver;
    pendingResolver = null;
    set({ networkConsentPending: false });
    resolver?.(false);
  },

  setOfflineMode: (enabled: boolean) => {
    const settings = loadNetworkSettings();
    saveNetworkSettings({ ...settings, offlineMode: enabled });
    set({ offlineMode: enabled });
  },

  isNetworkServiceEnabled: (service: NetworkService): boolean => {
    // Absent means enabled, which is what SettingsNetwork declares in
    // python-core/sidecar_kuro/models.py. A bundle that has never been written
    // must not read as "every service switched off".
    return get().settings?.network?.[`consent_${service}`] ?? true;
  },

  requireNetworkConsent: (service?: NetworkService): Promise<boolean> => {
    const state = get();

    if (state.offlineMode) {
      return Promise.resolve(false);
    }
    // A service the user switched off in Settings is refused before the modal.
    // Prompting for global consent would be the wrong question: consent is
    // already a separate decision, and granting it must not silently re-enable
    // a service that was individually turned off.
    if (service !== undefined && !state.isNetworkServiceEnabled(service)) {
      return Promise.resolve(false);
    }
    if (state.networkConsentGranted) {
      return Promise.resolve(true);
    }

    // 이미 모달이 열려 있는 경우 — 동일 Promise 재사용
    if (state.networkConsentPending && pendingResolver !== null) {
      return new Promise<boolean>((resolve) => {
        const prev = pendingResolver;
        pendingResolver = (granted: boolean) => {
          prev?.(granted);
          resolve(granted);
        };
      });
    }

    return new Promise<boolean>((resolve) => {
      pendingResolver = resolve;
      set({ networkConsentPending: true });
    });
  },
});
