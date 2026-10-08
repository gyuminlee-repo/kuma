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
import type { NetworkService } from "../slice-interfaces";

type Bundle = { network?: Record<string, boolean> } | null;

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
  const state: Record<string, unknown> = {};
  // Patch in place so the object handed back below stays the live state and a
  // test can read networkConsentPending after the slice sets it.
  const set = (patch: Record<string, unknown>) => {
    Object.assign(state, patch);
  };
  const get = () => state as never;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const slice = createNetworkConsentSlice(set as any, get as any, {} as any);
  Object.assign(state, {
    ...slice,
    networkConsentGranted: opts.granted,
    networkConsentServices: opts.services === undefined ? [...SERVICES] : opts.services,
    offlineMode: opts.offline,
    networkConsentPending: false,
    settings: opts.settings,
  });
  return state as unknown as ReturnType<typeof createNetworkConsentSlice> & {
    isNetworkServiceEnabled: (s: NetworkService) => boolean;
    requireNetworkConsent: (s?: NetworkService) => Promise<boolean>;
  };
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
      expect(slice.isNetworkServiceEnabled(service)).toBe(true);
    }
  });

  it.each(SERVICES)("refuses %s once that switch is off, with consent granted", async (service) => {
    const off = makeSlice({
      granted: true,
      offline: false,
      settings: { network: { [`consent_${service}`]: false } },
    });
    await expect(off.requireNetworkConsent(service)).resolves.toBe(false);
    // Only the named service is refused; the others still pass.
    for (const other of SERVICES.filter((s) => s !== service)) {
      await expect(off.requireNetworkConsent(other)).resolves.toBe(true);
    }
  });

  it("does not prompt for global consent when the service itself is off", async () => {
    const off = makeSlice({
      granted: false,
      offline: false,
      settings: { network: { consent_blast: false } },
    });
    await expect(off.requireNetworkConsent("blast")).resolves.toBe(false);
    // Prompting would ask a question whose answer cannot change the outcome.
    expect((off as unknown as { networkConsentPending: boolean }).networkConsentPending).toBe(false);
  });

  it("still refuses everything in offline mode", async () => {
    const off = makeSlice({
      granted: true,
      offline: true,
      settings: { network: { consent_uniprot: true } },
    });
    await expect(off.requireNetworkConsent("uniprot")).resolves.toBe(false);
  });

  it("allows a service left on", async () => {
    const on = makeSlice({
      granted: true,
      offline: false,
      settings: { network: { consent_interpro: true } },
    });
    await expect(on.requireNetworkConsent("interpro")).resolves.toBe(true);
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
    await expect(legacy.requireNetworkConsent("alphafold")).resolves.toBe(true);

    let settled = false;
    const pending = legacy.requireNetworkConsent("esmfold").then((v) => {
      settled = true;
      return v;
    });
    await Promise.resolve();
    expect(settled).toBe(false);
    expect((legacy as unknown as { networkConsentPending: boolean }).networkConsentPending).toBe(true);

    // Accepting the dialog, which now lists ESMFold, lets the call through.
    (legacy as unknown as { grantNetworkConsent: () => void }).grantNetworkConsent();
    await expect(pending).resolves.toBe(true);
  });

  it("refuses esmfold when the re-prompt is declined", async () => {
    const legacy = makeSlice({ granted: true, offline: false, settings: null, services: null });
    const pending = legacy.requireNetworkConsent("esmfold");
    (legacy as unknown as { denyNetworkConsent: () => void }).denyNetworkConsent();
    await expect(pending).resolves.toBe(false);
  });

  it("passes esmfold without a prompt once a grant listed it", async () => {
    const current = makeSlice({ granted: true, offline: false, settings: null });
    await expect(current.requireNetworkConsent("esmfold")).resolves.toBe(true);
    expect((current as unknown as { networkConsentPending: boolean }).networkConsentPending).toBe(false);
  });
});

describe("submitContactEmail when the save fails", () => {
  // The waiter retries the EBI submission on true. The sidecar reads the
  // address from preferences.json, so an unsaved address must not read as
  // provided: the retry would be refused again with the same error.
  function makeEmailSlice(saveSettings: () => Promise<void>) {
    const slice = makeSlice({ granted: true, offline: false, settings: { network: {} } });
    Object.assign(slice, { saveSettings, isDirty: false });
    return slice as typeof slice & {
      requireContactEmail: () => Promise<boolean>;
      submitContactEmail: (email: string) => Promise<boolean>;
      contactEmailPending: boolean;
    };
  }

  it("returns false and resumes the waiter with false when saveSettings rejects", async () => {
    const slice = makeEmailSlice(() => Promise.reject(new Error("disk full")));
    const waiter = slice.requireContactEmail();
    expect(slice.contactEmailPending).toBe(true);
    await expect(slice.submitContactEmail("me@example.org")).resolves.toBe(false);
    await expect(waiter).resolves.toBe(false);
    expect(slice.contactEmailPending).toBe(false);
  });

  it("returns false when saveSettings swallows the error and leaves the bundle dirty", async () => {
    // settingsSlice.saveSettings catches the RPC error itself; the only sign of
    // failure is that isDirty stays true.
    const slice = makeEmailSlice(async () => {});
    const waiter = slice.requireContactEmail();
    await expect(slice.submitContactEmail("me@example.org")).resolves.toBe(false);
    await expect(waiter).resolves.toBe(false);
    expect(slice.contactEmailPending).toBe(false);
  });

  it("returns true and resumes the waiter with true when the save lands", async () => {
    const slice = makeEmailSlice(async () => {
      Object.assign(slice, { isDirty: false });
    });
    const waiter = slice.requireContactEmail();
    await expect(slice.submitContactEmail("me@example.org")).resolves.toBe(true);
    await expect(waiter).resolves.toBe(true);
    expect(slice.contactEmailPending).toBe(false);
  });
});
