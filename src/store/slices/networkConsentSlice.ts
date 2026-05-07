import type { StateCreator } from "zustand";
import type { AppState } from "../types";
import type { NetworkConsentSlice } from "../slice-interfaces";
export type { NetworkConsentSlice };

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

  requireNetworkConsent: (): Promise<boolean> => {
    const state = get();

    if (state.offlineMode) {
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
