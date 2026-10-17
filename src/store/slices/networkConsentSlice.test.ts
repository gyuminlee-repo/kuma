/**
 * The per-service switches in Settings have to refuse the call they name.
 *
 * They did not. Four checkboxes wrote `consent_*` into the preferences bundle
 * and every external call went through one global flag, so switching BLAST off
 * left BLAST running. Same shape as the fill-on-failure box that let a run
 * pinned to 18 nt return 17mers: a control that stores a preference and gates
 * nothing.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createStore } from "zustand/vanilla";

vi.mock("../../lib/networkSettings", () => ({
  loadNetworkSettings: () => ({
    networkConsentGranted: true,
    networkConsentTimestamp: null,
    networkConsentServices: null,
    offlineMode: false,
  }),
  saveNetworkSettings: vi.fn(),
}));

import { createNetworkConsentSlice } from "./networkConsentSlice";
import { useAppStore } from "../appStore";
import type { NetworkService } from "../slice-interfaces";
import type { AppState } from "../types";

type Bundle = AppState["settings"];

const SERVICES: NetworkService[] = ["uniprot", "blast", "alphafold", "interpro", "esmfold"];

function makeSlice(opts: {
  granted: boolean;
  offline: boolean;
  settings: Bundle;
  /**
   * Recipients listed in the dialog when consent was granted. Omitted means a
   * grant from the current dialog (every service); `null` means a grant saved
   * before this list existed.
   */
  services?: NetworkService[] | null;
}) {
  return createStore<AppState>()((...args) => ({
    ...useAppStore.getInitialState(),
    ...createNetworkConsentSlice(...args),
    networkConsentGranted: opts.granted,
    networkConsentServices: opts.services === undefined ? [...SERVICES] : opts.services,
    offlineMode: opts.offline,
    networkConsentPending: false,
    settings: opts.settings,
  }));
}


describe("per-service network consent", () => {
  let slice: ReturnType<typeof makeSlice>;

  beforeEach(() => {
    slice = makeSlice({ granted: true, offline: false, settings: null });
  });

  it("treats an absent bundle as every service enabled", () => {
    // SettingsNetwork defaults every consent_* to True. A first run, whose
    // preferences.json has no network section, must not read as all-off.
    for (const service of SERVICES) {
      expect(slice.getState().isNetworkServiceEnabled(service)).toBe(true);
    }
  });

  it.each(SERVICES)("refuses %s once that switch is off, with consent granted", async (service) => {
    const off = makeSlice({
      granted: true,
      offline: false,
      settings: { network: { [`consent_${service}`]: false } },
    });
    await expect(off.getState().requireNetworkConsent(service)).resolves.toBe(false);
    // Only the named service is refused; the others still pass.
    for (const other of SERVICES.filter((s) => s !== service)) {
      await expect(off.getState().requireNetworkConsent(other)).resolves.toBe(true);
    }
  });

  it("does not prompt for global consent when the service itself is off", async () => {
    const off = makeSlice({
      granted: false,
      offline: false,
      settings: { network: { consent_blast: false } },
    });
    await expect(off.getState().requireNetworkConsent("blast")).resolves.toBe(false);
    // Prompting would ask a question whose answer cannot change the outcome.
    expect(off.getState().networkConsentPending).toBe(false);
  });

  it("still refuses everything in offline mode", async () => {
    const off = makeSlice({
      granted: true,
      offline: true,
      settings: { network: { consent_uniprot: true } },
    });
    await expect(off.getState().requireNetworkConsent("uniprot")).resolves.toBe(false);
  });

  it("allows a service left on", async () => {
    const on = makeSlice({
      granted: true,
      offline: false,
      settings: { network: { consent_interpro: true } },
    });
    await expect(on.getState().requireNetworkConsent("interpro")).resolves.toBe(true);
  });
});

/**
 * ESMFold sends the sequence to Meta (api.esmatlas.com), a recipient the
 * consent dialog did not list before. A grant given against the old list must
 * not cover it: the user has to be asked again.
 */
describe("ESMFold consent is not inherited from an earlier grant", () => {
  it("prompts for esmfold when consent was granted before ESMFold was listed", async () => {
    const legacy = makeSlice({ granted: true, offline: false, settings: null, services: null });
    // The services the old dialog named still pass without a prompt.
    await expect(legacy.getState().requireNetworkConsent("alphafold")).resolves.toBe(true);

    let settled = false;
    const pending = legacy.getState().requireNetworkConsent("esmfold").then((v) => {
      settled = true;
      return v;
    });
    await Promise.resolve();
    expect(settled).toBe(false);
    expect(legacy.getState().networkConsentPending).toBe(true);

    // Accepting the dialog, which now lists ESMFold, lets the call through.
    legacy.getState().grantNetworkConsent();
    await expect(pending).resolves.toBe(true);
  });

  it("refuses esmfold when the re-prompt is declined", async () => {
    const legacy = makeSlice({ granted: true, offline: false, settings: null, services: null });
    const pending = legacy.getState().requireNetworkConsent("esmfold");
    legacy.getState().denyNetworkConsent();
    await expect(pending).resolves.toBe(false);
  });

  it("passes esmfold without a prompt once a grant listed it", async () => {
    const current = makeSlice({ granted: true, offline: false, settings: null });
    await expect(current.getState().requireNetworkConsent("esmfold")).resolves.toBe(true);
    expect(current.getState().networkConsentPending).toBe(false);
  });
});

describe("submitContactEmail when the save fails", () => {
  // The waiter retries the EBI submission on true. The sidecar reads the
  // address from preferences.json, so an unsaved address must not read as
  // provided: the retry would be refused again with the same error.
  function makeEmailSlice(saveSettings: () => Promise<void>) {
    const slice = makeSlice({ granted: true, offline: false, settings: { network: {} } });
    slice.setState({ saveSettings, isDirty: false });
    return slice;
  }

  it("returns false and resumes the waiter with false when saveSettings rejects", async () => {
    const slice = makeEmailSlice(() => Promise.reject(new Error("disk full")));
    const waiter = slice.getState().requireContactEmail();
    expect(slice.getState().contactEmailPending).toBe(true);
    await expect(slice.getState().submitContactEmail("me@example.org")).resolves.toBe(false);
    await expect(waiter).resolves.toBe(false);
    expect(slice.getState().contactEmailPending).toBe(false);
  });

  it("returns false when saveSettings swallows the error and leaves the bundle dirty", async () => {
    // settingsSlice.saveSettings catches the RPC error itself; the only sign of
    // failure is that isDirty stays true.
    const slice = makeEmailSlice(async () => {});
    const waiter = slice.getState().requireContactEmail();
    await expect(slice.getState().submitContactEmail("me@example.org")).resolves.toBe(false);
    await expect(waiter).resolves.toBe(false);
    expect(slice.getState().contactEmailPending).toBe(false);
  });

  it("returns true and resumes the waiter with true when the save lands", async () => {
    const slice = makeEmailSlice(async () => {
      slice.setState({ isDirty: false });
    });
    const waiter = slice.getState().requireContactEmail();
    await expect(slice.getState().submitContactEmail("me@example.org")).resolves.toBe(true);
    await expect(waiter).resolves.toBe(true);
    expect(slice.getState().contactEmailPending).toBe(false);
  });
});
