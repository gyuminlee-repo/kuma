/**
 * polymeraseMigration.test.ts, retired "Benchling" profile migration.
 *
 * The hazard this guards: a saved state selected "Benchling" (GC 30-70), the
 * profile no longer ships, and loadPolymerases runs after the restore. The old
 * fallback sent the unknown name through setSelectedPolymerase, which always
 * overwrites gcMin/gcMax/overlapMode, silently rewriting the design conditions
 * of an old run to the replacement profile defaults (KOD, 40-60).
 *
 * These tests drive the real ordering (restored state -> loadPolymerases), not
 * the alias helper in isolation.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { sendRequest } from "@/lib/ipc-kuro";
import { useAppStore } from "@/store/appStore";
import { DEFAULT_POLYMERASE } from "@/lib/polymeraseAliases";
import type { PolymeraseInfo, PolymeraseProfile } from "@/types/models";

const KOD: PolymeraseProfile = {
  name: "KOD",
  tm_method: "santalucia",
  salt_correction: "santalucia",
  opt_tm: 68,
  min_tm: 63,
  max_tm: 73,
  opt_size: 21,
  min_size: 18,
  max_size: 28,
  min_gc: 40,
  max_gc: 60,
  salt_monovalent: 50,
  salt_divalent: 1.5,
  dntp_conc: 0.8,
  dna_conc: 250,
  max_tm_diff: 4,
  opt_tm_fwd: 62,
  opt_tm_rev: 58,
  opt_tm_overlap: 42,
  default_overlap_mode: null,
};

/** Surviving 7-profile list: "Benchling" is deliberately absent. */
const PROFILE_LIST: PolymeraseInfo[] = [
  "Taq", "Phusion", "Q5", "KOD", "DreamTaq", "TAKARA_GXL", "Q5 SDM",
].map((name) => ({ name, manufacturer: "", fidelity: "" }));

const mockSend = vi.mocked(sendRequest);

function routeRpc() {
  mockSend.mockImplementation(((method: string) => {
    if (method === "list_polymerases") return Promise.resolve(PROFILE_LIST);
    if (method === "get_polymerase_details") return Promise.resolve(KOD);
    return Promise.reject(new Error(`unexpected rpc: ${method}`));
  }) as unknown as typeof sendRequest);
}

describe("retired polymerase profile migration", () => {
  beforeEach(() => {
    mockSend.mockReset();
    routeRpc();
    // The store is a module singleton shared across tests in this file.
    useAppStore.setState({ statusMessage: "Ready" });
  });

  it("remaps a saved Benchling selection to KOD and preserves the saved GC range", async () => {
    // Restored state, as a workspace/autosave load leaves it.
    useAppStore.setState({
      selectedPolymerase: "Benchling",
      gcMin: 30,
      gcMax: 70,
      overlapMode: "partial",
    });

    await useAppStore.getState().loadPolymerases();

    const s = useAppStore.getState();
    expect(s.selectedPolymerase).toBe("KOD");
    // The whole point: the retired profile's GC window survives the migration.
    expect(s.gcMin).toBe(30);
    expect(s.gcMax).toBe(70);
    expect(s.overlapMode).toBe("partial");
    expect(s.statusMessage).toContain("Benchling");
    expect(s.statusMessage).toContain("KOD");
    expect(s.statusMessage).toContain("30-70%");
    // The alias path must never ask for profile details, since that response is
    // what would clobber the GC range.
    expect(mockSend).not.toHaveBeenCalledWith("get_polymerase_details", expect.anything());
  });

  it("applies KOD profile defaults on a fresh start with no saved workspace", async () => {
    useAppStore.setState({
      selectedPolymerase: DEFAULT_POLYMERASE,
      gcMin: 40,
      gcMax: 60,
      overlapMode: "partial",
    });

    await useAppStore.getState().loadPolymerases();

    const s = useAppStore.getState();
    expect(s.selectedPolymerase).toBe("KOD");
    expect(s.gcMin).toBe(40);
    expect(s.gcMax).toBe(60);
    expect(s.statusMessage).not.toContain("was removed");
  });

  it("keeps a saved custom GC range for a profile that still exists", async () => {
    // Regression guard for the non-retired path: an unchanged selection must not
    // trigger the migration notice.
    useAppStore.setState({
      selectedPolymerase: "Q5",
      gcMin: 45,
      gcMax: 55,
      overlapMode: "partial",
    });

    await useAppStore.getState().loadPolymerases();

    expect(useAppStore.getState().selectedPolymerase).toBe("Q5");
    expect(useAppStore.getState().gcMin).toBe(45);
    expect(useAppStore.getState().gcMax).toBe(55);
    expect(useAppStore.getState().statusMessage).not.toContain("was removed");
  });

  it("does not reset a restored GC range when the selection is already valid", async () => {
    // Order-independence guard: loadPolymerases may run after a restore has
    // already landed a valid selection with a non-default GC range. Re-running
    // setSelectedPolymerase there would silently overwrite gcMin/gcMax with the
    // profile defaults, which is the same silent data change the alias path
    // avoids.
    useAppStore.setState({
      selectedPolymerase: "KOD",
      gcMin: 30,
      gcMax: 70,
      overlapMode: "partial",
    });

    await useAppStore.getState().loadPolymerases();

    expect(useAppStore.getState().selectedPolymerase).toBe("KOD");
    expect(useAppStore.getState().gcMin).toBe(30);
    expect(useAppStore.getState().gcMax).toBe(70);
  });
});
