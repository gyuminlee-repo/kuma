/**
 * Both entry points (verdict table variant id, plate map well) must open the
 * same detail panel with the same content, so these tests drive the real
 * mameAppStore instead of a mock and render the table, the plate and the
 * inspector together.
 */
import { render, screen, fireEvent, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { VerdictDetailInspector } from "./VerdictDetailInspector";
import { VerdictTable } from "@/components/mame/widgets/VerdictTable";
import { PlateView } from "@/components/mame/widgets/PlateView";
import { useMameAppStore, type AppState } from "@/store/mame/mameAppStore";
import type {
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

function seedStore(overrides: Partial<AppState> = {}) {
  useMameAppStore.setState({
    verdicts: [selectedVerdict, rejectedVerdict],
    replicates: [replicate],
    wells,
    selectedWell: null,
    plateFilter: "FINAL",
    searchQuery: "",
    sorting: [],
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
