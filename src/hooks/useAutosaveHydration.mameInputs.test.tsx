/**
 * MAME inputs a reopened project has to come back with.
 *
 * Item 3: the variant list's sheet and column were not in the autosave, and the
 * restore never asked the sidecar about the workbook again, so the mapping
 * panel stayed hidden and a hand-picked column silently reverted.
 * Item 4: the restored CDS bounds were overwritten by the longest ORF when the
 * reference parse answered after the restore.
 * Item 7: a KURO Export All writes `<prefix>_platemap.xlsx` (registered as
 * `kuro_platemap_xlsx`), while the restore only looked for `sdm_primer_xlsx`,
 * which the current UI no longer writes.
 */
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { buildMameSnapshot } from "@/lib/mame/autosaveSnapshot";
import { useRoundStore } from "@/store/round/roundSlice";
import { useAutosaveHydration } from "./useAutosaveHydration";

const hooks = vi.hoisted(() => ({
  readAutosave: vi.fn(),
  readScratchAutosave: vi.fn(),
  readMameResultSnapshot: vi.fn(),
  sendMameRequest: vi.fn(),
  detectProjectFiles: vi.fn(),
  detectFromInputDir: vi.fn(),
  openWorkspace: vi.fn(),
  getLatestArtifact: vi.fn(),
  exists: vi.fn(async (_path: string) => true),
}));

vi.mock("@tauri-apps/plugin-fs", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@tauri-apps/plugin-fs");
  return { ...actual, exists: hooks.exists };
});

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
}));

vi.mock("@/lib/autosave", () => ({
  readAutosave: hooks.readAutosave,
  readScratchAutosave: hooks.readScratchAutosave,
  deleteScratchAutosave: vi.fn(),
  blockAutosaveWrites: vi.fn(),
  clearAutosaveBlock: vi.fn(),
  beginHydration: vi.fn(),
  endHydration: vi.fn(),
  ensureAutosaveDir: vi.fn(),
  autosavePath: vi.fn(),
  atomicWriteJson: vi.fn(),
}));

vi.mock("@/lib/mame/resultSnapshot", () => ({
  readMameResultSnapshot: hooks.readMameResultSnapshot,
}));

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: hooks.sendMameRequest,
  isSidecarRunning: () => false,
}));

vi.mock("@/lib/mame/detectProjectFiles", () => ({
  detectProjectFiles: hooks.detectProjectFiles,
  detectFromInputDir: hooks.detectFromInputDir,
}));

vi.mock("@/lib/workspace", () => ({
  openWorkspace: hooks.openWorkspace,
  getLatestArtifact: hooks.getLatestArtifact,
  getActiveWorkspace: vi.fn(() => null),
  clearWorkspace: vi.fn(),
}));

const PLAIN_LIST_INFO = {
  is_kuro_export: false,
  sheets: ["Sheet1", "Round2"],
  headers: { Sheet1: ["mutation"], Round2: ["id", "variant"] },
  suggested_column: "mutation",
};

const PARSED_REFERENCE = {
  cds_candidates: [
    { start: 0, end: 900, source: "orf", aa_length: 299 },
    { start: 300, end: 600, source: "orf", aa_length: 99 },
  ],
  sequence_length: 1200,
  format: "fasta",
};

function Harness() {
  useAutosaveHydration(() => {});
  return null;
}

function renderHydration(): void {
  render(
    <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
      <Harness />
    </ProjectProvider>,
  );
}

function serveMameSnapshot(snapshot: unknown): void {
  hooks.readAutosave.mockImplementation((_path: string, kind: string) =>
    Promise.resolve(kind === "mame" ? { status: "ok", snapshot } : { status: "missing" }),
  );
}

describe("useAutosaveHydration: MAME inputs chosen on another screen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMameAppStore.getState().resetInput();
    useMameAppStore.getState().resetAnalysis();
    useRoundStore.setState({ rounds: [], active_round_id: null });
    hooks.readAutosave.mockResolvedValue({ status: "missing" });
    hooks.readScratchAutosave.mockResolvedValue({ status: "missing" });
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });
    hooks.detectProjectFiles.mockResolvedValue({});
    hooks.detectFromInputDir.mockResolvedValue({});
    hooks.exists.mockResolvedValue(true);
    hooks.openWorkspace.mockResolvedValue(undefined);
    hooks.getLatestArtifact.mockResolvedValue(null);
    hooks.sendMameRequest.mockImplementation((method: string) => {
      if (method === "inspect_variant_source") return Promise.resolve(PLAIN_LIST_INFO);
      if (method === "mame.ingest.parse_reference") return Promise.resolve(PARSED_REFERENCE);
      return Promise.resolve({});
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("restores a hand-picked sheet and column and shows the mapping panel again", async () => {
    act(() => {
      useMameAppStore.setState({
        expectedPath: "/proj/variants.xlsx",
        variantSheet: "Round2",
        variantColumn: "variant",
        variantSelectionExplicit: true,
      });
    });
    const snapshot = buildMameSnapshot(useMameAppStore.getState(), undefined, "/proj");
    useMameAppStore.getState().resetInput();
    serveMameSnapshot(snapshot);

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().variantSourceInfo).toEqual(PLAIN_LIST_INFO);
    });
    const state = useMameAppStore.getState();
    expect(state.expectedPath).toBe("/proj/variants.xlsx");
    expect(state.variantSheet).toBe("Round2");
    expect(state.variantColumn).toBe("variant");
    expect(state.variantSelectionExplicit).toBe(true);
    expect(hooks.sendMameRequest).toHaveBeenCalledWith(
      "inspect_variant_source",
      { path: "/proj/variants.xlsx" },
      expect.any(Number),
    );
  });

  it("keeps the restored CDS bounds after the reference parse answers", async () => {
    act(() => {
      useMameAppStore.setState({
        referencePath: "/proj/ref.fasta",
        cdsStart: 300,
        cdsEnd: 600,
        cdsSelectionExplicit: true,
      });
    });
    const snapshot = buildMameSnapshot(useMameAppStore.getState(), undefined, "/proj");
    useMameAppStore.getState().resetInput();
    serveMameSnapshot(snapshot);

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().analyzeCdsCandidates).toHaveLength(2);
    });
    const state = useMameAppStore.getState();
    expect(state.cdsStart).toBe(300);
    expect(state.cdsEnd).toBe(600);
    expect(state.selectedAnalyzeCdsIndex).toBe(1);
  });

  it("treats stated bounds in a snapshot written before the flag as explicit", async () => {
    act(() => {
      useMameAppStore.setState({ referencePath: "/proj/ref.fasta", cdsStart: 300, cdsEnd: 600 });
    });
    const snapshot = buildMameSnapshot(useMameAppStore.getState(), undefined, "/proj");
    const params = snapshot.parameters as Record<string, unknown>;
    delete params.cds_selection_explicit;
    delete params.selected_analyze_cds_index;
    useMameAppStore.getState().resetInput();
    serveMameSnapshot(snapshot);

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().analyzeCdsCandidates).toHaveLength(2);
    });
    expect(useMameAppStore.getState().cdsStart).toBe(300);
    expect(useMameAppStore.getState().selectedAnalyzeCdsIndex).toBe(1);
  });

  it("fills an empty expected input from the latest KURO Export All plate map", async () => {
    hooks.getLatestArtifact.mockImplementation((type: string) =>
      Promise.resolve(
        type === "kuro_platemap_xlsx"
          ? { path: "/proj/design/run_platemap.xlsx", producedAt: "2026-09-29T01:00:00.000Z" }
          : null,
      ),
    );

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().expectedPath).toBe("/proj/design/run_platemap.xlsx");
    });
  });

  it("prefers whichever KURO workbook was written last", async () => {
    hooks.getLatestArtifact.mockImplementation((type: string) =>
      Promise.resolve(
        type === "kuro_platemap_xlsx"
          ? { path: "/proj/design/old_platemap.xlsx", producedAt: "2026-09-01T00:00:00.000Z" }
          : type === "sdm_primer_xlsx"
            ? { path: "/proj/design/sdm_primers.xlsx", producedAt: "2026-09-20T00:00:00.000Z" }
            : null,
      ),
    );

    renderHydration();

    await waitFor(() => {
      expect(useMameAppStore.getState().expectedPath).toBe("/proj/design/sdm_primers.xlsx");
    });
  });
});
