/**
 * Both entry points (verdict table variant id, plate map well) must open the
 * same detail panel with the same content, so these tests drive the real
 * mameAppStore instead of a mock and render the table, the plate and the
 * inspector together.
 */
import { render, screen, fireEvent, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import enLocale from "@/locales/en.json";
import { VerdictDetailInspector } from "./VerdictDetailInspector";
import { VerdictTable } from "@/components/mame/widgets/VerdictTable";
import { PlateView } from "@/components/mame/widgets/PlateView";
import { useMameAppStore, type AppState } from "@/store/mame/mameAppStore";
import type {
  CompareParams,
  ReplicateResult,
  VerdictRecord,
  WellEntry,
} from "@/types/mame/models";

function makeVerdict(overrides: Partial<VerdictRecord> = {}): VerdictRecord {
  return {
    native_barcode: "sort_barcode01",
    custom_barcode: "1_1",
    file_size_kb: 120,
    read_count: 1500,
    n_mixed_positions: 0,
    max_minor_allele_fraction: 0.02,
    n_low_depth_positions: 0,
    consensus_n_fraction: 0,
    n_low_quality_bases: 3,
    n_input_reads: 1800,
    n_aligned_reads: 1700,
    n_mapq_failed: 12,
    n_span_failed: 8,
    source_path: "/out/consensus/1_1.fasta",
    aa_sequence: "MKLVF",
    observed_nt_changes: ["T265G"],
    observed_aa_changes: ["F89W"],
    n_no_call_aa: 0,
    expected_mutations: ["F89W"],
    mutant_id: "F89W",
    verdict: "PASS",
    verdict_notes: "clean call",
    ...overrides,
  };
}

/** Winner (NB01) plus a rejected replicate copy (NB02) of the same variant. */
const selectedVerdict = makeVerdict();
const rejectedVerdict = makeVerdict({
  native_barcode: "sort_barcode02",
  custom_barcode: "1_2",
  verdict: "NO_CALL",
  observed_aa_changes: [],
  observed_nt_changes: [],
  verdict_notes: "",
  read_count: null,
  n_input_reads: null,
  n_aligned_reads: null,
  source_path: "",
  aa_sequence: "",
});

const replicate: ReplicateResult = {
  mutant_id: "F89W",
  selected_plate: "sort_barcode01",
  selection_reason: "highest read count",
  failed: false,
  plate_keys: ["sort_barcode01", "sort_barcode02"],
  plate_verdicts: {
    sort_barcode01: selectedVerdict,
    sort_barcode02: rejectedVerdict,
  },
  is_fallback: false,
  fallback_reason: null,
};

const wells: WellEntry[] = [
  {
    well: "A1",
    barcode: "1_1",
    native_barcode: "sort_barcode01",
    verdict: "PASS",
    mutant_id: "F89W",
    selected: true,
    notes: "clean call",
    is_fallback: false,
    fallback_reason: null,
  },
  {
    well: "B2",
    barcode: "1_2",
    native_barcode: "sort_barcode02",
    verdict: "NO_CALL",
    mutant_id: "F89W",
    selected: false,
    notes: "",
    is_fallback: false,
    fallback_reason: null,
  },
];

/**
 * Thresholds deliberately unlike every backend default (30 reads / 50 KB /
 * 0.0 N / cutoff 5): a popup that printed a literal instead of reading the
 * run's own reported values would still show the default and pass.
 */
const compareParams: CompareParams = {
  min_file_size_kb: 77,
  min_read_count: 42,
  max_consensus_n_fraction: 0.05,
  many_mutation_cutoff: 7,
  mixed_confident_depth_factor: 3,
  mixed_confident_read_count: 126,
};

function seedStore(overrides: Partial<AppState> = {}) {
  useMameAppStore.setState({
    verdicts: [selectedVerdict, rejectedVerdict],
    replicates: [replicate],
    wells,
    selectedWell: null,
    plateFilter: "FINAL",
    searchQuery: "",
    sorting: [],
    // Explicit so a test that leaves thresholds behind cannot make the next
    // one pass: the store is the real one and setState merges.
    compareParams,
    ...overrides,
  });
}

describe("VerdictDetailInspector", () => {
  beforeEach(() => {
    seedStore();
  });

  it("defaults the verdict table filter to FINAL in the store", () => {
    // Store default, independent of the seeding above.
    useMameAppStore.getState().resetAnalysis();
    expect(useMameAppStore.getState().plateFilter).toBe("FINAL");
  });

  it("opens from the verdict table with the expected/observed evidence", () => {
    render(
      <>
        <VerdictTable />
        <VerdictDetailInspector />
      </>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Show details for F89W (well 1_1)" }),
    );

    const panel = screen.getByTestId("verdict-detail");
    expect(within(panel).getByText("Verdict evidence")).toBeInTheDocument();
    const expectedBlock = within(panel).getByText("Expected").parentElement!;
    expect(within(expectedBlock).getByText("F89W")).toBeInTheDocument();
    const observedBlock = within(panel).getByText("Observed").parentElement!;
    expect(within(observedBlock).getByText("F89W")).toBeInTheDocument();
    // Replicate comparison shows both plate copies and marks the selected one.
    expect(within(panel).getByText("Replicate comparison")).toBeInTheDocument();
    expect(within(panel).getAllByTestId("replicate-row")).toHaveLength(2);
    expect(within(panel).getByText("highest read count")).toBeInTheDocument();
  });

  it("shows the same detail whether opened from the plate map or the table", () => {
    const fromTable = render(
      <>
        <VerdictTable />
        <VerdictDetailInspector />
      </>,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Show details for F89W (well 1_1)" }),
    );
    const tableText = screen.getByTestId("verdict-detail").textContent;
    fromTable.unmount();

    seedStore();
    render(
      <>
        <PlateView />
        <VerdictDetailInspector />
      </>,
    );
    fireEvent.click(
      screen
        .getByRole("gridcell", { name: "Well A1: PASS" })
        .querySelector("button")!,
    );
    const plateText = screen.getByTestId("verdict-detail").textContent;

    expect(plateText).toBe(tableText);
  });

  it("opens a non-selected replicate well and still marks the selected plate", () => {
    render(
      <>
        <PlateView />
        <VerdictDetailInspector />
      </>,
    );

    fireEvent.click(
      screen
        .getByRole("gridcell", { name: "Well B2: NO_CALL" })
        .querySelector("button")!,
    );

    const panel = screen.getByTestId("verdict-detail");
    // The clicked (rejected) copy is what the panel describes...
    expect(within(panel).getByText("No change observed")).toBeInTheDocument();
    // ...and the comparison still tells which copy won.
    const rows = within(panel).getAllByTestId("replicate-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText("Selected")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("NB01")).toBeInTheDocument();
    expect(within(rows[1]!).queryByText("Selected")).toBeNull();
  });

  it("omits fields the backend did not report instead of showing 0", () => {
    useMameAppStore.setState({ selectedWell: wells[1]! });
    render(<VerdictDetailInspector />);

    // read_count / n_input_reads / n_aligned_reads are null on this well.
    expect(screen.queryByText("Reads (filtered)")).toBeNull();
    expect(screen.queryByText("Input reads")).toBeNull();
    expect(screen.queryByText("Aligned reads")).toBeNull();
    // Empty strings drop their rows too.
    expect(screen.queryByText("Notes")).toBeNull();
    expect(screen.queryByText("Source")).toBeNull();
    // Reported counters are still rendered, including a real zero.
    expect(screen.getByText("MAPQ drops")).toBeInTheDocument();
    expect(screen.getByText("Mixed positions")).toBeInTheDocument();
    // Nucleotide section is skipped when there is no change to show.
    expect(screen.queryByText("Nucleotide changes")).toBeNull();
  });

  it("keeps the aa_sequence behind a copy button rather than printing it", () => {
    useMameAppStore.setState({ selectedWell: wells[0]! });
    render(<VerdictDetailInspector />);

    expect(screen.queryByText("MKLVF")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Copy amino acid sequence" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Copy consensus FASTA path" }),
    ).toBeInTheDocument();
  });
});

// ── Replicate rows select their plate copy ─────────────────────────────────
//
// The comparison list is the third entry point into `selectedWell`, next to the
// plate map well and the verdict table row, and it must land on the same state
// as either of those. What separates a real selection from a redraw is which
// WellEntry ends up in the store, so these assert the store rather than the DOM.

describe("VerdictDetailInspector replicate rows", () => {
  beforeEach(() => {
    seedStore();
  });

  it("selects the plate copy using the store well entry when one exists", () => {
    useMameAppStore.setState({ selectedWell: wells[0]! });
    render(<VerdictDetailInspector />);

    const rows = screen.getAllByTestId("replicate-row");
    // Sorted by native barcode, so NB01 then NB02.
    fireEvent.click(within(rows[1]!).getByRole("button"));

    const selected = useMameAppStore.getState().selectedWell;
    expect(selected).toEqual(wells[1]!);
    // The discriminator: only the plate-map entry carries the plate position
    // ("B2"). A rebuilt literal would put the custom barcode ("1_2") there and
    // the header would name a well that is not where the sample sits.
    expect(selected?.well).toBe("B2");
  });

  it("builds the entry from the verdict record when plate data never loaded", () => {
    // Reachable, not defensive padding: `loadPlateData` clears `wells` to []
    // whenever `get_plate_data` fails (analysisSlice.ts), while the verdict
    // table still opens this panel from the record alone (VerdictTable
    // `openWellDetail`). The comparison rows are live in exactly that state.
    seedStore({ wells: [] });
    render(
      <>
        <VerdictTable />
        <VerdictDetailInspector />
      </>,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Show details for F89W (well 1_1)" }),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Show plate NB02, well 1_2" }),
    );

    expect(useMameAppStore.getState().selectedWell).toEqual({
      well: "1_2",
      barcode: "1_2",
      native_barcode: "sort_barcode02",
      verdict: "NO_CALL",
      mutant_id: "F89W",
      selected: false,
      notes: "",
      is_fallback: false,
      fallback_reason: null,
    });

    // `selected` is the plate map's own rule (selected plate, replicate not
    // failed) narrowed to this one copy, so the winner comes back marked.
    fireEvent.click(
      screen.getByRole("button", { name: "Show plate NB01, well 1_1" }),
    );
    expect(useMameAppStore.getState().selectedWell?.selected).toBe(true);
  });

  it("marks the row for the well on screen and re-clicking it is a no-op", () => {
    useMameAppStore.setState({ selectedWell: wells[0]! });
    render(<VerdictDetailInspector />);

    const rows = screen.getAllByTestId("replicate-row");
    const current = within(rows[0]!).getByRole("button");
    expect(current).toHaveAttribute("aria-current", "true");
    expect(within(rows[1]!).getByRole("button")).not.toHaveAttribute("aria-current");
    // Enabled on purpose: a disabled row would drop out of the tab order
    // mid-list, so `aria-current` is what marks it instead.
    expect(current).toBeEnabled();

    fireEvent.click(current);

    expect(useMameAppStore.getState().selectedWell).toEqual(wells[0]!);
    expect(screen.getAllByTestId("replicate-row")).toHaveLength(2);
    expect(within(rows[0]!).getByRole("button")).toHaveAttribute(
      "aria-current",
      "true",
    );
  });
});

// ── Confidence metric popups ───────────────────────────────────────────────
//
// Every threshold in these panels has a backend default that applies when the
// caller omits it (`min_read_count` is omitted on every run), so a literal in
// the TSX would read as correct until the engine moved. These pin that the text
// tracks `compareParams` and says "unknown" when the run reported nothing.

describe("VerdictDetailInspector confidence metric popups", () => {
  beforeEach(() => {
    seedStore({ selectedWell: wells[0]! });
  });

  it("opens a metric panel from the keyboard and closes it on Escape", () => {
    render(<VerdictDetailInspector />);

    const trigger = screen.getByTestId("metric-info-readCount-trigger");
    expect(trigger.tagName).toBe("BUTTON");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    // A native button is in the tab order, so the explanation is reachable
    // without a pointer.
    trigger.focus();
    expect(document.activeElement).toBe(trigger);
    expect(screen.queryByTestId("metric-info-readCount")).toBeNull();

    fireEvent.click(trigger);
    expect(screen.getByTestId("metric-info-readCount")).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("metric-info-readCount")).toBeNull();
    // Focus comes back to where the reader left it, not to the document body.
    expect(document.activeElement).toBe(trigger);
  });

  it("closes on Escape pressed while the trigger itself holds focus", () => {
    // Separate from the test above on purpose, and it is the case that
    // actually happens. A keystroke that starts on the trigger never reaches
    // the panel's document-level listener: the trigger's own onKeyDown calls
    // stopPropagation, React 19 dispatches from the root container, and its
    // synthetic stopPropagation also stops the native event there (measured
    // against react-dom 19 + jsdom, 0 document calls). The trigger is exactly
    // where focus sits after opening the panel from the keyboard, and where
    // closing it puts focus back, so firing Escape at `document` alone would
    // pass while the reader who needs Escape cannot use it.
    render(<VerdictDetailInspector />);

    const trigger = screen.getByTestId("metric-info-readCount-trigger");
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByTestId("metric-info-readCount")).toBeInTheDocument();

    fireEvent.keyDown(trigger, { key: "Escape" });

    expect(screen.queryByTestId("metric-info-readCount")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("closes a metric panel on an outside click but not on a click inside it", () => {
    render(<VerdictDetailInspector />);

    const trigger = screen.getByTestId("metric-info-readCount-trigger");
    fireEvent.click(trigger);
    const panel = screen.getByTestId("metric-info-readCount");

    // A click inside is a reader selecting text, not a dismissal.
    fireEvent.mouseDown(panel);
    expect(screen.getByTestId("metric-info-readCount")).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId("metric-info-readCount")).toBeNull();
  });

  it("states the gated thresholds this run reported, and none for a diagnostic metric", () => {
    render(<VerdictDetailInspector />);

    fireEvent.click(screen.getByTestId("metric-info-readCount-trigger"));
    const gated = screen.getByTestId("metric-info-readCount").textContent ?? "";
    expect(gated).toContain("Judged against");
    expect(gated).toContain("LOWDEPTH below 42 reads.");
    expect(gated).toContain(
      "A confident MIXED call needs 126 reads or more (the depth floor times 3).",
    );
    expect(gated).toContain(
      "Wells that carry no depth header at all fall back to a consensus file size of 77 KB.",
    );
    fireEvent.keyDown(document, { key: "Escape" });

    // 7 of the 10 metrics gate nothing, and the panel says so rather than
    // leaving the reader to assume a silent threshold.
    fireEvent.click(screen.getByTestId("metric-info-mapqFailed-trigger"));
    const diagnostic = screen.getByTestId("metric-info-mapqFailed").textContent ?? "";
    expect(diagnostic).toContain("Diagnostic only. No gate reads this number.");
    expect(diagnostic).not.toContain("Judged against");
  });

  it("says the thresholds are unknown rather than printing a default", () => {
    // A result restored from a snapshot written before the sidecar reported its
    // thresholds. The engine default (30 reads) must not appear here.
    seedStore({ selectedWell: wells[0]!, compareParams: null });
    render(<VerdictDetailInspector />);

    fireEvent.click(screen.getByTestId("metric-info-readCount-trigger"));
    const panel = screen.getByTestId("metric-info-readCount").textContent ?? "";
    expect(panel).toContain("did not report its thresholds");
    expect(panel).not.toContain("LOWDEPTH below");
  });

  it("says the N-fraction gate was skipped instead of showing a clean 0.0%", () => {
    useMameAppStore.setState({
      verdicts: [makeVerdict({ consensus_n_fraction_evaluable: false })],
      selectedWell: wells[0]!,
    });
    render(<VerdictDetailInspector />);

    // The row still shows the substituted number, because that is what the
    // record holds; the panel is where it is told not to be trusted.
    const detail = screen.getByTestId("verdict-detail");
    expect(within(detail).getByText("0.0%")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("metric-info-consensusN-trigger"));
    const panel = screen.getByTestId("metric-info-consensusN").textContent ?? "";
    expect(panel).toContain("the value shown is a substituted 0.0");
    expect(panel).toContain("the NO_CALL gate was skipped");
    // The threshold is still reported: the ceiling existed, the well just
    // could not be measured against it.
    expect(panel).toContain("NO_CALL above 5.0%.");
  });

  it("keeps an unreported evaluability flag distinct from a false one", () => {
    // Saved before the flag existed: whether the gate ran is unknown, which is
    // not the same claim as "the gate was skipped".
    useMameAppStore.setState({
      verdicts: [makeVerdict()],
      selectedWell: wells[0]!,
    });
    render(<VerdictDetailInspector />);

    fireEvent.click(screen.getByTestId("metric-info-consensusN-trigger"));
    const panel = screen.getByTestId("metric-info-consensusN").textContent ?? "";
    expect(panel).toContain(
      "saved before the run reported whether the N fraction could be evaluated",
    );
    expect(panel).not.toContain("the value shown is a substituted 0.0");
  });
});

/**
 * The five coverage figures answer a question the read count cannot: a well
 * covered evenly at 100x and one averaging 100x with a hole report the same
 * depth. None of them gates anything, so nothing here is coloured, and
 * `consensus_identity` never appears without the N fraction beside it.
 */
describe("VerdictDetailInspector, coverage uniformity", () => {
  const en = enLocale.mame.verdictDetail.coverage;

  it("reports the five figures a measured well carries", () => {
    useMameAppStore.setState({
      verdicts: [
        makeVerdict({
          depth_cv: 0.42,
          depth_p10: 210,
          depth_min_covered: 87,
          breadth_at_mix_min_depth: 0.93,
          consensus_identity: 0.998,
        }),
      ],
      selectedWell: wells[0]!,
    });
    render(<VerdictDetailInspector />);

    const block = screen.getByTestId("verdict-coverage");
    expect(block).toHaveAttribute("data-measured", "true");
    const text = block.textContent ?? "";
    expect(text).toContain("0.42");
    expect(text).toContain("210");
    expect(text).toContain("93.0%");
    expect(text).toContain("99.8%");
    expect(text).not.toContain("{{");
    expect(text).not.toContain("mame.");
  });

  it("keeps the N fraction next to identity so a mostly-N well cannot look perfect", () => {
    useMameAppStore.setState({
      verdicts: [makeVerdict({ consensus_identity: 1, consensus_n_fraction: 0.95 })],
      selectedWell: wells[0]!,
    });
    render(<VerdictDetailInspector />);

    const text = screen.getByTestId("verdict-coverage").textContent ?? "";
    expect(text).toContain("100.0%");
    expect(text).toContain("95.0%");
    expect(text).toContain(en.identityNote);
  });

  it("prints an unmeasured figure as unknown while a measured 0 stays 0", () => {
    // The sidecar omits the five independently: a well with no reads reports a
    // real breadth of 0 with the other four absent.
    useMameAppStore.setState({
      verdicts: [makeVerdict({ breadth_at_mix_min_depth: 0 })],
      selectedWell: wells[0]!,
    });
    render(<VerdictDetailInspector />);

    const block = screen.getByTestId("verdict-coverage");
    expect(block).toHaveAttribute("data-measured", "true");
    const text = block.textContent ?? "";
    expect(text).toContain("0.0%");
    expect(text).toContain(en.notMeasured);
    expect(text).not.toContain(en.absent);
  });

  it("answers a result that predates the measurement with one reason, not five dashes", () => {
    useMameAppStore.setState({
      verdicts: [makeVerdict()],
      selectedWell: wells[0]!,
    });
    render(<VerdictDetailInspector />);

    const block = screen.getByTestId("verdict-coverage");
    expect(block).toHaveAttribute("data-measured", "false");
    expect(block.textContent ?? "").toContain(en.absent);
  });

  it("warns when the N fraction beside the identity was a substituted zero", () => {
    useMameAppStore.setState({
      verdicts: [
        makeVerdict({ consensus_identity: 0.99, consensus_n_fraction_evaluable: false }),
      ],
      selectedWell: wells[0]!,
    });
    render(<VerdictDetailInspector />);

    expect(screen.getByTestId("verdict-coverage").textContent ?? "").toContain(
      en.nNotEvaluable,
    );
  });
});
