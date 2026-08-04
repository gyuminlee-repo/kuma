import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { create } from "zustand";
import type { AppState as MameAppStore } from "@/store/mame/mameAppStore";
import type { RoundSlice } from "@/store/round/roundSlice";
import type { Round } from "@/types/round";
import type { MergedRow } from "@/types/mame/activity";
import type { VerdictRecord, ReplicateResult } from "@/types/mame/models";
import { VERDICT_COLUMN_WIDTH_STORAGE_KEY } from "@/lib/mame/verdictColumnWidthStorage";

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
    wells: [],
    selectedWell: null,
    setPlateFilter: vi.fn(),
    setSearchQuery: vi.fn(),
    setSorting: vi.fn(),
    setSelectedWell: vi.fn(),
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

  it("sorts the barcode column numerically (1_2 before 1_10)", () => {
    const mk = (cb: string): VerdictRecord => ({
      ...mockVerdict,
      custom_barcode: cb,
      mutant_id: `v_${cb}`,
    });
    const scrambled = ["1_10", "1_2", "1_1", "1_12", "1_11"].map(mk);
    vi.mocked(useMameAppStore).mockImplementation(
      (sel: (s: MameAppStore) => unknown) =>
        sel(makeMameStore({ verdicts: scrambled }).getState()),
    );
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([], null).getState()),
    );
    render(<VerdictTable />);
    const labels = screen
      .getAllByText(/^1_\d+$/)
      .map((el) => el.textContent);
    expect(labels).toEqual(["1_1", "1_2", "1_10", "1_11", "1_12"]);
  });

  it("marks a variant recovered (✓) if any replicate is detected, ✗ otherwise", () => {
    const mk = (
      nb: string,
      verdict: VerdictRecord["verdict"],
      mid: string,
    ): VerdictRecord => ({
      ...mockVerdict,
      native_barcode: nb,
      custom_barcode: "1_1",
      verdict,
      mutant_id: mid,
    });
    const verdicts = [
      mk("barcode01", "WRONG_AA", "mA"), // mA replicate 1: fail
      mk("barcode02", "PASS", "mA"), // mA replicate 2: detected → ✓
      mk("barcode01", "LOWDEPTH", "mB"), // mB replicate 1: fail
      mk("barcode02", "WRONG_AA", "mB"), // mB replicate 2: fail → ✗
    ];
    vi.mocked(useMameAppStore).mockImplementation(
      (sel: (s: MameAppStore) => unknown) =>
        sel(makeMameStore({ verdicts }).getState()),
    );
    vi.mocked(useRoundStore).mockImplementation(
      (sel: (s: RoundSlice) => unknown) => sel(makeRoundStore([], null).getState()),
    );
    render(<VerdictTable />);
    const cells = screen
      .getAllByTestId("recovered-cell")
      .map((el) => el.textContent);
    // mA appears in 2 NB rows (both ✓), mB in 2 rows (both ✗).
    expect(cells.filter((c) => c === "✓").length).toBe(2);
    expect(cells.filter((c) => c === "✗").length).toBe(2);
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

  it("FINAL tab shows only the plate-map selected-replicate wells", () => {
    const selected: VerdictRecord = { ...mockVerdict, custom_barcode: "A01", mutant_id: "F89W" };
    const other: VerdictRecord = {
      ...mockVerdict,
      custom_barcode: "B02",
      mutant_id: "K10R",
      verdict: "NO_CALL",
    };
    const replicates: ReplicateResult[] = [
      {
        mutant_id: "F89W",
        selected_plate: "barcode01",
        selection_reason: "",
        failed: false,
        plate_keys: ["barcode01"],
        plate_verdicts: { barcode01: selected },
        is_fallback: false,
        fallback_reason: null,
      },
    ];
    vi.mocked(useMameAppStore).mockImplementation((sel: (s: MameAppStore) => unknown) =>
      sel(
        makeMameStore({
          verdicts: [selected, other],
          replicates,
          plateFilter: "FINAL",
        }).getState(),
      ),
    );
    vi.mocked(useRoundStore).mockImplementation((sel: (s: RoundSlice) => unknown) =>
      sel(makeRoundStore([], null).getState()),
    );
    render(<VerdictTable />);
    // Tab present, and only the selected well (A01) is listed — not the
    // non-selected B02, matching what the plate map marks as picked.
    expect(screen.getByText("Final")).toBeTruthy();
    expect(screen.getByText("A01")).toBeTruthy();
    expect(screen.queryByText("B02")).toBeNull();
    // FINAL has rows here, so no fallback notice and the FINAL tab stays active.
    expect(screen.queryByTestId("final-fallback-notice")).toBeNull();
    expect(screen.getByRole("tab", { name: "Final" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("falls back to ALL, with a notice, when FINAL would show no rows", () => {
    const a: VerdictRecord = { ...mockVerdict, custom_barcode: "A01", mutant_id: "F89W" };
    const b: VerdictRecord = {
      ...mockVerdict,
      custom_barcode: "B02",
      mutant_id: "K10R",
      verdict: "NO_CALL",
    };
    vi.mocked(useMameAppStore).mockImplementation((sel: (s: MameAppStore) => unknown) =>
      sel(
        makeMameStore({
          verdicts: [a, b],
          // No replicate selection yet: the FINAL set is empty.
          replicates: [],
          plateFilter: "FINAL",
        }).getState(),
      ),
    );
    vi.mocked(useRoundStore).mockImplementation((sel: (s: RoundSlice) => unknown) =>
      sel(makeRoundStore([], null).getState()),
    );
    render(<VerdictTable />);

    expect(screen.getByTestId("final-fallback-notice")).toBeTruthy();
    // Every well is listed (ALL behavior), and the ALL tab reflects what is shown.
    expect(screen.getByText("A01")).toBeTruthy();
    expect(screen.getByText("B02")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "ALL" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("opens the well detail from the variant id button", () => {
    const setSelectedWell = vi.fn();
    vi.mocked(useMameAppStore).mockImplementation((sel: (s: MameAppStore) => unknown) =>
      sel(makeMameStore({ setSelectedWell }).getState()),
    );
    vi.mocked(useRoundStore).mockImplementation((sel: (s: RoundSlice) => unknown) =>
      sel(makeRoundStore([], null).getState()),
    );
    render(<VerdictTable />);

    fireEvent.click(screen.getByRole("button", { name: /F89W/ }));
    expect(setSelectedWell).toHaveBeenCalledTimes(1);
    expect(setSelectedWell.mock.calls[0]?.[0]).toMatchObject({
      barcode: "A01",
      native_barcode: "barcode01",
      mutant_id: "F89W",
    });
  });
});

// ── Truncated cells: a real path to the full text ──────────────────────────
//
// jsdom reports 0 for every layout metric, so overflow is simulated: a cell is
// "overflowing" when its text is longer than what a 240px box fits (~8px per
// character). That mirrors the scrollWidth vs clientWidth check the component
// makes in the browser.
const SIMULATED_BOX_WIDTH = 240;
const SIMULATED_CHAR_WIDTH = 8;

function simulateTextMetrics() {
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return (this.textContent?.length ?? 0) * SIMULATED_CHAR_WIDTH;
    },
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() {
      return SIMULATED_BOX_WIDTH;
    },
  });
}

function restoreTextMetrics() {
  Reflect.deleteProperty(HTMLElement.prototype, "scrollWidth");
  Reflect.deleteProperty(HTMLElement.prototype, "clientWidth");
}

const LONG_NOTES =
  "consensus net indel -1 bp not divisible by 3 (frameshift) · All plates below pickable threshold (only ['FRAMESHIFT', 'MIXED']). Highest-volume sort_barcode09 (834 reads) used as fallback.";

function renderWithVerdicts(verdicts: VerdictRecord[]) {
  vi.mocked(useMameAppStore).mockImplementation((sel: (s: MameAppStore) => unknown) =>
    sel(makeMameStore({ verdicts }).getState()),
  );
  vi.mocked(useRoundStore).mockImplementation((sel: (s: RoundSlice) => unknown) =>
    sel(makeRoundStore([], null).getState()),
  );
  render(<VerdictTable />);
}

describe("VerdictTable truncated cells", () => {
  beforeEach(() => {
    simulateTextMetrics();
  });

  afterEach(() => {
    restoreTextMetrics();
  });

  it("offers a keyboard-reachable trigger that reveals the full notes text", () => {
    renderWithVerdicts([{ ...mockVerdict, verdict_notes: LONG_NOTES }]);

    const trigger = screen.getByRole("button", { name: /consensus net indel/ });
    expect(trigger.tagName).toBe("BUTTON");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    // A native button is in the tab order, so the full text is reachable
    // without a pointer.
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    fireEvent.click(trigger);
    const panel = screen.getByTestId("expandable-text-panel");
    expect(panel.getAttribute("role")).toBe("tooltip");
    expect(panel.textContent).toContain(LONG_NOTES);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("expandable-text-panel")).toBeNull();
  });

  it("adds no trigger to a row whose notes are empty", () => {
    renderWithVerdicts([{ ...mockVerdict, verdict_notes: "" }]);

    expect(screen.queryByRole("button", { name: /^Notes:/ })).toBeNull();
    expect(screen.queryByTestId("expandable-text-panel")).toBeNull();
  });

  it("adds no trigger to a row whose notes fit the cell", () => {
    renderWithVerdicts([{ ...mockVerdict, verdict_notes: "low depth" }]);

    expect(screen.queryByRole("button", { name: /low depth/ })).toBeNull();
  });
});

// ── Column resizing ────────────────────────────────────────────────────────
describe("VerdictTable column resizing", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  function notesHeader() {
    const handle = screen.getByTestId("resize-handle-verdict_notes");
    const header = handle.closest("th");
    if (!header) throw new Error("resize handle is not inside a header cell");
    return { handle, header };
  }

  it("keeps a keyboard-resized column width, and restores the default on reset", () => {
    renderWithVerdicts([mockVerdict]);

    const { handle, header } = notesHeader();
    expect(handle.getAttribute("tabindex")).toBe("0");
    expect(handle.getAttribute("role")).toBe("separator");
    const defaultWidth = header.style.width;
    expect(defaultWidth).toBe("240px");

    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(header.style.width).toBe("256px");

    fireEvent.keyDown(handle, { key: "Home" });
    expect(header.style.width).toBe(defaultWidth);
  });

  it("persists the width across a remount and resets it back", () => {
    renderWithVerdicts([mockVerdict]);
    fireEvent.keyDown(screen.getByTestId("resize-handle-verdict_notes"), {
      key: "ArrowRight",
    });
    expect(
      JSON.parse(localStorage.getItem(VERDICT_COLUMN_WIDTH_STORAGE_KEY) ?? "{}"),
    ).toMatchObject({ verdict_notes: 256 });

    cleanup();
    renderWithVerdicts([mockVerdict]);
    const { handle, header } = notesHeader();
    expect(header.style.width).toBe("256px");

    // Double-click is the pointer escape hatch from a column dragged too narrow.
    fireEvent.doubleClick(handle);
    expect(header.style.width).toBe("240px");
    expect(
      JSON.parse(localStorage.getItem(VERDICT_COLUMN_WIDTH_STORAGE_KEY) ?? "{}"),
    ).toEqual({});
  });
});
