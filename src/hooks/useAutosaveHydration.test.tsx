import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { AnalyzeResult, ReplicateResult, VerdictRecord } from "@/types/mame/models";
import { useAutosaveHydration } from "./useAutosaveHydration";

// ── Mocks ────────────────────────────────────────────────────────────────

const hooks = vi.hoisted(() => ({
  readAutosave: vi.fn(),
  readScratchAutosave: vi.fn(),
  readMameResultSnapshot: vi.fn(),
  sendMameRequest: vi.fn(),
  detectProjectFiles: vi.fn(),
  detectFromInputDir: vi.fn(),
}));

vi.mock("@/lib/autosave", () => ({
  readAutosave: hooks.readAutosave,
  readScratchAutosave: hooks.readScratchAutosave,
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

// ── Fixtures ─────────────────────────────────────────────────────────────

const VERDICT: VerdictRecord = {
  native_barcode: "barcode1",
  custom_barcode: "1_1",
  file_size_kb: 120,
  read_count: 160,
  n_mixed_positions: 0,
  max_minor_allele_fraction: 0,
  n_low_depth_positions: 0,
  consensus_n_fraction: 0,
  n_low_quality_bases: 0,
  n_input_reads: 160,
  n_aligned_reads: 155,
  n_mapq_failed: 0,
  n_span_failed: 0,
  source_path: "/mock/NB01/1_1.fasta",
  aa_sequence: "MSTTS",
  observed_nt_changes: [],
  n_no_call_aa: 0,
  observed_aa_changes: ["V5F"],
  expected_mutations: ["V5F"],
  mutant_id: "V5F",
  verdict: "PASS",
  verdict_notes: "",
};

const REPLICATE: ReplicateResult = {
  mutant_id: "V5F",
  selected_plate: "barcode1",
  selection_reason: "only_pass",
  failed: false,
  plate_keys: ["barcode1"],
  // Critical: lossless per-plate verdict carried through AS-IS.
  plate_verdicts: { barcode1: VERDICT },
  is_fallback: false,
  fallback_reason: null,
};

const ANALYZE_RESULT: AnalyzeResult = {
  verdicts: [VERDICT],
  replicates: [REPLICATE],
  output_path: "/proj/out/mame_result.xlsx",
  summary: { total: 1, pass_count: 1, ambiguous_count: 0, fail_count: 0 },
  distribution_stats: {
    n_files: 1,
    file_size_kb: { min: 120, p05: 120, p25: 120, median: 120, p75: 120, p95: 120, max: 120, mean: 120, std: 0 },
    suggested_cutoff_kb: 50,
    suggested_method: "fixed_50",
    bimodal: false,
  },
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

describe("useAutosaveHydration: analyze-result restore", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMameAppStore.getState().resetInput();
    useMameAppStore.getState().resetAnalysis();
    useMameAppStore.getState().setMameSubStep("setup.files");

    // kuro: nothing to restore. mame input snapshot: nothing either.
    hooks.readAutosave.mockResolvedValue({ status: "missing" });
    hooks.readScratchAutosave.mockResolvedValue({ status: "missing" });
    // detection finds nothing (avoid touching the store further).
    hooks.detectProjectFiles.mockResolvedValue({});
    hooks.detectFromInputDir.mockResolvedValue({});
    // sidecar RPCs: load_analyze_result ack, then get_plate_data empty grid.
    hooks.sendMameRequest.mockImplementation((method: string) => {
      if (method === "load_analyze_result") {
        return Promise.resolve({ restored: true, verdict_count: 1, replicate_count: 1 });
      }
      if (method === "get_plate_data") {
        return Promise.resolve({ wells: [] });
      }
      return Promise.resolve({});
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("replays the persisted result into the sidecar and lands on analyze.review", async () => {
    hooks.readMameResultSnapshot.mockResolvedValue({
      status: "ok",
      snapshot: {
        schema: 1,
        saved_at: new Date().toISOString(),
        kuma_version: "0.0.0-test",
        result: ANALYZE_RESULT,
      },
    });

    renderHydration();

    // load_analyze_result called with the persisted payload AS-IS.
    await waitFor(() => {
      expect(hooks.sendMameRequest).toHaveBeenCalledWith(
        "load_analyze_result",
        expect.objectContaining({ output_path: "/proj/out/mame_result.xlsx" }),
      );
    });

    const [, params] = hooks.sendMameRequest.mock.calls.find(
      (c) => c[0] === "load_analyze_result",
    ) as [string, { replicates: ReplicateResult[]; output_path: string }];
    // plate_verdicts carried through AS-IS (lossless plate-accent source).
    expect(params.replicates[0].plate_verdicts).toEqual({ barcode1: VERDICT });

    // get_plate_data called AFTER load_analyze_result (sidecar repopulated first).
    await waitFor(() => {
      expect(hooks.sendMameRequest).toHaveBeenCalledWith("get_plate_data", {});
    });

    // store repopulated + landed on the 2.2 review view.
    await waitFor(() => {
      expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.review");
    });
    const st = useMameAppStore.getState();
    expect(st.verdicts).toEqual([VERDICT]);
    expect(st.replicates).toEqual([REPLICATE]);
    expect(st.summary).toEqual(ANALYZE_RESULT.summary);
    expect(st.distributionStats).toEqual(ANALYZE_RESULT.distribution_stats);
  });

  it("skips restore silently when no result file exists", async () => {
    hooks.readMameResultSnapshot.mockResolvedValue({ status: "missing" });

    renderHydration();

    // give the hydration IIFE time to settle (detect runs last).
    await waitFor(() => {
      expect(hooks.detectProjectFiles).toHaveBeenCalled();
    });

    expect(
      hooks.sendMameRequest.mock.calls.some((c) => c[0] === "load_analyze_result"),
    ).toBe(false);
    // Project entry resets the MAME phase, so the substep returns to the
    // default analyze.inputs (never silently advanced to analyze.review).
    expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.inputs");
    expect(useMameAppStore.getState().verdicts).toEqual([]);
  });
});
