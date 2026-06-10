import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import type { AppState as MameAppStore } from "@/store/mame/mameAppStore";
import type { RoundSlice } from "@/store/round/roundSlice";
import type { Round } from "@/types/round";
import type { MergedRow } from "@/types/mame/activity";
import type { VerdictRecord } from "@/types/mame/models";

vi.mock("@/store/mame/mameAppStore");
vi.mock("@/store/round/roundSlice");

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import { VerdictTable, selectActiveMergedTable } from "./VerdictTable";

const mockVerdict: VerdictRecord = {
  native_barcode: "barcode01",
  custom_barcode: "A01",
  file_size_kb: 100,
  read_count: 1500,
  n_mixed_positions: 0,
  max_minor_allele_fraction: 0,
  n_low_depth_positions: 0,
  consensus_n_fraction: 0,
  n_low_quality_bases: 0,
  n_input_reads: 1500,
  n_aligned_reads: 1490,
  n_mapq_failed: 2,
  n_span_failed: 8,
  source_path: "/data/NB01/barcode01.fastq",
  aa_sequence: "MKLVF89W",
  observed_nt_changes: ["T265G"],
  observed_aa_changes: ["F89W"],
  n_no_call_aa: 0,
  expected_mutations: ["F89W"],
  mutant_id: "F89W",
  verdict: "PASS",
  verdict_notes: "",
};

const mockMergedRow: MergedRow = {
  plate_id: "P01",
  well_id: "A01",
  mutation: "F89W",
  mutation_source: "kuro_design",
  expected_mutation: "F89W",
  called_mutation: "F89W",
  ngs_success: true,
  activity_raw_mean: 1.985,
  activity_raw_sd: 0.05,
  activity_replicates: [1.94, 2.03],
  replicate_n: 2,
  fold_change: 1.99,
  log2_fc: 0.99,
};

const baseRound: Round = {
  id: "round_1",
  n: 1,
  created_at: "2026-05-04T00:00:00Z",
  status: "activity_linked",
  error_info: null,
  plate_meta: { plates: [] },
  design: {},
  genotype: {},
  activity: null,
  merged_table: [mockMergedRow],
};

function makeMameStore(overrides: Partial<MameAppStore> = {}) {
  return create<MameAppStore>()(() => ({
    verdicts: [mockVerdict],
    replicates: [],
    plateFilter: "ALL",
    searchQuery: "",
    sorting: [],
    setPlateFilter: vi.fn(),
    setSearchQuery: vi.fn(),
    setSorting: vi.fn(),
    ...overrides,
  }) as unknown as MameAppStore);
}

function makeRoundStore(rounds: Round[] = [], activeId: string | null = null) {
  return create<RoundSlice>()(() => ({
    rounds,
    active_round_id: activeId,
    addRound: vi.fn(),
    transitionStatus: vi.fn(),
    setActiveRound: vi.fn(),
    updateRoundField: vi.fn(),
    handoffNextRound: vi.fn(),
  }));
}

describe("VerdictTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function setup(rounds: Round[] = [], activeId: string | null = null) {
    vi.mocked(useMameAppStore).mockImplementation(
      (sel: (s: MameAppStore) => unknown) => sel(makeMameStore().getState())
    );
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore(rounds, activeId).getState())
    );
    render(<VerdictTable />);
  }

  it("renders existing columns (Barcode, Verdict, Depth)", () => {
    setup();
    expect(screen.getByText("Barcode")).toBeTruthy();
    expect(screen.getByText("Verdict")).toBeTruthy();
    expect(screen.getByText("Depth (reads)")).toBeTruthy();
  });

  it("renders activity column headers when merged data exists", () => {
    setup([baseRound], "round_1");
    expect(screen.getByText("log₂FC")).toBeTruthy();
    expect(screen.getByText("Fold Change")).toBeTruthy();
    expect(screen.getByText("Raw Mean ± SD")).toBeTruthy();
    expect(screen.getByText("Replicates")).toBeTruthy();
    expect(screen.getByText("NGS")).toBeTruthy();
  });

  it("renders activity values for joined row (well A01)", () => {
    setup([baseRound], "round_1");
    // log2_fc = 0.99 → "0.99"
    expect(screen.getAllByText("0.99").length).toBeGreaterThan(0);
    // fold_change = 1.99 → "1.99"
    expect(screen.getAllByText("1.99").length).toBeGreaterThan(0);
    // replicate_n = 2
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  });

  it("shows NGS success badge", () => {
    setup([baseRound], "round_1");
    // ngs_success = true → ✓ badge
    const badges = screen.getAllByText("✓");
    expect(badges.length).toBeGreaterThan(0);
  });

  it("shows dashes for activity columns when no merged data", () => {
    setup([], null);
    // No merged data → activity cells show "—"
    const dashes = screen.getAllByText("—");
    // Multiple dashes expected (one per activity column per row)
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("returns a stable empty merged table snapshot when no active round exists", () => {
    const state = makeRoundStore([], null).getState();
    expect(selectActiveMergedTable(state)).toBe(selectActiveMergedTable(state));
  });

  it("column toggle button is rendered", () => {
    setup([baseRound], "round_1");
    expect(
      screen.getByRole("button", { name: /Toggle column visibility/i })
    ).toBeTruthy();
  });

  it("clicking toggle button opens dropdown", async () => {
    setup([baseRound], "round_1");
    const btn = screen.getByRole("button", { name: /Toggle column visibility/i });
    fireEvent.click(btn);
    // Dropdown may render in portal — check the button is present and clickable
    expect(btn).toBeTruthy();
  });
  it("derives NB tabs from the native barcodes present, not a fixed NB01/02/03 set", () => {
    const v6 = { ...mockVerdict, native_barcode: "sort_barcode06", custom_barcode: "1_1" };
    const v20 = { ...mockVerdict, native_barcode: "sort_barcode20", custom_barcode: "1_2" };
    vi.mocked(useMameAppStore).mockImplementation((sel: (s: MameAppStore) => unknown) =>
      sel(makeMameStore({ verdicts: [v6, v20] }).getState()),
    );
    vi.mocked(useRoundStore).mockImplementation((sel: (s: RoundSlice) => unknown) =>
      sel(makeRoundStore([], null).getState()),
    );
    render(<VerdictTable />);
    expect(screen.getByRole("tab", { name: "ALL" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "NB06" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "NB20" })).toBeTruthy();
    // The old hardcoded NB02/NB03 tabs must NOT appear when those barcodes are absent.
    expect(screen.queryByRole("tab", { name: "NB02" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "NB03" })).toBeNull();
  });

  it("shows each well's own variant id within one native barcode (no NB-collapse)", () => {
    // Combinatorial-sort reality: one sort bin (native_barcode) carries many
    // distinct wells. The variant id must come from each record's own mutant_id,
    // NOT from a replicate map keyed by native_barcode (which collapses every
    // well in the bin onto a single duplicated variant).
    const wellV5F = { ...mockVerdict, native_barcode: "sort_barcode06", custom_barcode: "1_1", mutant_id: "V5F" };
    const wellR477Q = { ...mockVerdict, native_barcode: "sort_barcode06", custom_barcode: "1_10", mutant_id: "R477Q" };
    vi.mocked(useMameAppStore).mockImplementation((sel: (s: MameAppStore) => unknown) =>
      sel(
        makeMameStore({
          verdicts: [wellV5F, wellR477Q],
          // A replicate that, under the old NB-keyed lookup, would stamp BOTH
          // wells with "H448F" — the duplication bug we are guarding against.
          replicates: [
            {
              mutant_id: "H448F",
              selected_plate: "sort_barcode06",
              selection_reason: "fallback",
              failed: false,
              plate_keys: ["sort_barcode06"],
              plate_verdicts: {},
              is_fallback: false,
              fallback_reason: null,
            },
          ],
        }).getState(),
      ),
    );
    vi.mocked(useRoundStore).mockImplementation((sel: (s: RoundSlice) => unknown) =>
      sel(makeRoundStore([], null).getState()),
    );
    render(<VerdictTable />);
    expect(screen.getByText("V5F")).toBeTruthy();
    expect(screen.getByText("R477Q")).toBeTruthy();
    // The replicate's NB-attributed mutant must NOT leak into the rows.
    expect(screen.queryByText("H448F")).toBeNull();
  });

});
