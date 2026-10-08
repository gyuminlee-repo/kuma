import type { StateCreator } from "zustand";
import type { AppState } from "../types";
import type { NetworkConsentSlice, NetworkService } from "../slice-interfaces";
export type { NetworkConsentSlice, NetworkService };

import {
  loadNetworkSettings,
  saveNetworkSettings,
} from "../../lib/networkSettings";
import { isValidContactEmail } from "../../lib/contactEmail";

/**
 * 동의 모달의 Promise resolver 를 외부에서 resolve/reject 할 수 있도록 보관.
 * 모달 확인/취소 액션이 이를 호출한다.
 */
let pendingResolver: ((granted: boolean) => void) | null = null;

/** Same pattern for the contact email dialog: one dialog, every waiter resumed. */
let emailResolver: ((provided: boolean) => void) | null = null;

/**
 * Every service the consent dialog lists. A grant records this list, and a
 * service outside the recorded list is asked about again.
 */
export const CONSENT_DIALOG_SERVICES: readonly NetworkService[] = [
  "uniprot",
  "blast",
  "alphafold",
  "interpro",
  "esmfold",
];

/**
 * What the dialog listed before grants recorded their services. ESMFold is not
 * here: it sends the sequence to Meta, a recipient those users never saw.
 */
const LEGACY_CONSENT_SERVICES: readonly string[] = ["uniprot", "blast", "alphafold", "interpro"];

export const createNetworkConsentSlice: StateCreator<
  AppState,
  [],
  [],
  NetworkConsentSlice
> = (set, get) => ({
  networkConsentGranted: false,
  networkConsentServices: null,
  offlineMode: false,
  networkConsentPending: false,
  contactEmailPending: false,

  loadNetworkConsentSettings: () => {
    const settings = loadNetworkSettings();
    set({
      networkConsentGranted: settings.networkConsentGranted,
      networkConsentServices: settings.networkConsentServices,
      offlineMode: settings.offlineMode,
    });
  },

  grantNetworkConsent: () => {
    const resolver = pendingResolver;
    pendingResolver = null;

    const services = [...CONSENT_DIALOG_SERVICES];
    const settings = loadNetworkSettings();
    saveNetworkSettings({
      ...settings,
      networkConsentGranted: true,
      networkConsentTimestamp: new Date().toISOString(),
      networkConsentServices: services,
    });
    set({
      networkConsentGranted: true,
      networkConsentServices: services,
      networkConsentPending: false,
    });
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
      // A grant covers only the recipients its dialog listed. A grant saved
      // before the list was recorded covers the four services named then.
      const covered = state.networkConsentServices ?? LEGACY_CONSENT_SERVICES;
      if (service === undefined || covered.includes(service)) {
        return Promise.resolve(true);
      }
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

  requireContactEmail: (): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      const prev = emailResolver;
      emailResolver = prev
        ? (provided: boolean) => {
            prev(provided);
            resolve(provided);
          }
        : resolve;
      set({ contactEmailPending: true });
    });
  },

  submitContactEmail: async (email: string): Promise<boolean> => {
    const address = email.trim();
    if (!isValidContactEmail(address)) return false;
    // Written and saved directly rather than through updateSettings: its
    // 500 ms debounce would let the caller retry before preferences.json,
    // which is where the sidecar reads the address, holds it.
    const current = get().settings ?? {};
    set({
      settings: { ...current, network: { ...current.network, contact_email: address } },
      isDirty: true,
    });
    // saveSettings swallows the RPC error and leaves isDirty set, so a dirty
    // bundle after the await is a failed save. The waiter retries on true, and
    // the sidecar would refuse again without the address on disk, so a failed
    // save ends as a skip and the caller reports it with its skipped message.
    let saved = false;
    try {
      await get().saveSettings();
      saved = !get().isDirty;
    } catch {
      saved = false;
    } finally {
      const resolver = emailResolver;
      emailResolver = null;
      set({ contactEmailPending: false });
      resolver?.(saved);
    }
    return saved;
  },

  cancelContactEmail: () => {
    const resolver = emailResolver;
    emailResolver = null;
    set({ contactEmailPending: false });
    resolver?.(false);
  },
});
