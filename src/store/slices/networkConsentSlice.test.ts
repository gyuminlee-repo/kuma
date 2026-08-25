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
    offlineMode: false,
  }),
  saveNetworkSettings: vi.fn(),
}));

import { createNetworkConsentSlice } from "./networkConsentSlice";
import type { NetworkService } from "../slice-interfaces";

type Bundle = { network?: Record<string, boolean> } | null;

function makeSlice(opts: { granted: boolean; offline: boolean; settings: Bundle }) {
  let state: Record<string, unknown> = {};
  const set = (patch: Record<string, unknown>) => {
    state = { ...state, ...patch };
  };
  const get = () => state as never;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const slice = createNetworkConsentSlice(set as any, get as any, {} as any);
  state = {
    ...slice,
    networkConsentGranted: opts.granted,
    offlineMode: opts.offline,
    networkConsentPending: false,
    settings: opts.settings,
  };
  return state as unknown as ReturnType<typeof createNetworkConsentSlice> & {
    isNetworkServiceEnabled: (s: NetworkService) => boolean;
    requireNetworkConsent: (s?: NetworkService) => Promise<boolean>;
  };
}

const SERVICES: NetworkService[] = ["uniprot", "blast", "alphafold", "interpro"];

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
