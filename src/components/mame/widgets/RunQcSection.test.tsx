import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import en from "@/locales/en.json";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { DemuxAndFilterResult, RunHealthData } from "@/types/mame/models";
import type { PositionRecurrence, ReadLengthQC, RunQuality } from "@/types/mame/run_quality";
import { RunQcSection } from "./RunQcSection";

function makeHealth(overrides: Partial<RunHealthData> = {}): RunHealthData {
  return {
    per_plate_summary: {},
    file_size_distribution: { min: 10, p05: 12, p25: 20, median: 40, p75: 60, p95: 80, max: 90 },
    suggested_cutoff_kb: 50,
    bimodal: false,
    suggested_method: "p05",
    pore_yield_pct: null,
    throughput_timeline: null,
    barcode_distribution: null,
    cross_talk_candidates: [],
    recovered_mutants: 0,
    total_mutants: 0,
    recovery_rate: 0,
    ...overrides,
  };
}

function makeDemux(overrides: Partial<DemuxAndFilterResult> = {}): DemuxAndFilterResult {
  return {
    output_dir: "/tmp/out",
    n_input_reads: 1000,
    n_assigned: 900,
    n_unassigned: 100,
    per_well_counts: {},
    filter_stats: null,
    backend: "python",
    amplicon_length_estimate: null,
    length_filter_mode: "none",
    ...overrides,
  };
}

function makeRunQuality(overrides: Partial<RunQuality> = {}): RunQuality {
  return {
    severity: null,
    median_well_reads: 500,
    min_read_count: 100,
    depth_ok: true,
    wells_under_floor: 0,
    wells_total: 96,
    recommended_reads: 1000,
    flow_cell_id: null,
    pore_start: null,
    pore_end: null,
    pore_warranty_min: 800,
    reused_from: null,
    thresholds: {},
    findings: [],
    ...overrides,
  };
}

const recurrence: PositionRecurrence = {
  lower_bound: true,
  wells_contributing: 40,
  wells_truncated: 40,
  positions_seen: 130,
  positions_single_well: 90,
  positions: [
    {
      position: 512,
      wells: 31,
      median_weak_strand_share: 0.32,
      min_weak_strand_share: 0.11,
      max_weak_strand_share: 0.48,
      shares_known: 31,
      shares_unknown: 0,
    },
    {
      // Every share unknown. Rendering these as 0.0% would state the opposite
      // finding: 0 is "the minor allele came off one strand only".
      position: 900,
      wells: 4,
      median_weak_strand_share: null,
      min_weak_strand_share: null,
      max_weak_strand_share: null,
      shares_known: 0,
      shares_unknown: 4,
    },
  ],
};

const readLength: ReadLengthQC = {
  reference_length_bp: 1715,
  near_reference_tolerance: 0.2,
  concatemer_multiple: 2,
  histograms: [
    {
      read_length_type: "EstimatedBases",
      bucket_value_type: "ReadLengths",
      n50: 3257,
      plot: null,
      outliers: null,
      n50_over_reference: 1.9,
      near_reference_bases_fraction: 0.21,
      over_2x_reference_bases_fraction: 0.4,
    },
    {
      read_length_type: null,
      bucket_value_type: null,
      n50: 5053,
      plot: null,
      outliers: null,
      n50_over_reference: null,
      near_reference_bases_fraction: null,
      over_2x_reference_bases_fraction: null,
    },
  ],
  qscore_histograms: null,
  provenance: {},
};

/** The disclosure renders its children only while open, so open it first. */
function open() {
  fireEvent.click(screen.getByRole("button", { name: en.mame.runHealth.qcSectionAriaLabel }));
}

beforeEach(() => {
  useMameAppStore.setState({ demuxResult: null, runQuality: null });
});

describe("RunQcSection, the disclosure itself", () => {
  it("starts collapsed so the verdict table keeps the screen", () => {
    render(<RunQcSection runHealth={makeHealth()} />);

    expect(
      screen.getByRole("button", { name: en.mame.runHealth.qcSectionAriaLabel }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("run-qc-section")).not.toBeInTheDocument();
  });

  it("shows the five non-verdict health sections once opened", () => {
    render(<RunQcSection runHealth={makeHealth({ pore_yield_pct: 42.5 })} />);
    open();

    expect(screen.getByTestId("run-qc-health")).toHaveAttribute("data-state", "present");
    expect(screen.getByText("42.5%")).toBeInTheDocument();
    // The verdict breakdown is not among them: it is drawn beside the plate.
    expect(screen.queryByTestId("run-health-class-counts")).not.toBeInTheDocument();
  });

  it("says why the health block is missing rather than drawing nothing", () => {
    render(<RunQcSection runHealth={null} />);
    open();

    const block = screen.getByTestId("run-qc-health");
    expect(block).toHaveAttribute("data-state", "unavailable");
    expect(block.textContent ?? "").toContain(en.mame.runHealth.qcHealthAbsent);
  });

  it("gives every block a reason when the run produced nothing at all", () => {
    render(<RunQcSection runHealth={null} />);
    open();

    // A heading over an empty box is what this replaces, so each block names
    // its own reason rather than sharing one generic line.
    const expected: [string, string][] = [
      ["run-qc-health", en.mame.runHealth.qcHealthAbsent],
      ["run-qc-filter-stats", en.mame.runHealth.filterStats.noDemux],
      ["run-qc-position-recurrence", en.mame.runQuality.positionRecurrence.noRun],
      ["run-qc-read-length", en.mame.runQuality.readLength.noRun],
    ];
    for (const [id, reason] of expected) {
      const block = screen.getByTestId(id);
      expect(block).toHaveAttribute("data-state", "unavailable");
      expect(block.textContent ?? "").toContain(reason);
    }
  });

  it("leaks no interpolation placeholder and no raw key", () => {
    useMameAppStore.setState({
      demuxResult: makeDemux({
        filter_stats: {
          n_input: 10,
          n_passed: 8,
          n_failed_qscore: 1,
          n_failed_length: 1,
          n_failed_barcode: 0,
        },
      }),
      runQuality: makeRunQuality({ position_recurrence: recurrence, read_length: readLength }),
    });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const text = screen.getByTestId("run-qc-section").textContent ?? "";
    expect(text).not.toContain("{{");
    expect(text).not.toContain("mame.");
  });
});

describe("RunQcSection, filter stats", () => {
  it("tells a run that never demultiplexed from one with no sequencing_summary", () => {
    render(<RunQcSection runHealth={makeHealth()} />);
    open();
    expect(screen.getByTestId("run-qc-filter-stats").textContent ?? "").toContain(
      en.mame.runHealth.filterStats.noDemux,
    );
  });

  it("names the missing sequencing_summary when the demux ran but kept no tally", () => {
    useMameAppStore.setState({ demuxResult: makeDemux({ filter_stats: null }) });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const block = screen.getByTestId("run-qc-filter-stats");
    expect(block).toHaveAttribute("data-state", "unavailable");
    expect(block.textContent ?? "").toContain(en.mame.runHealth.filterStats.noSummary);
    expect(block.textContent ?? "").not.toContain(en.mame.runHealth.filterStats.noDemux);
  });

  it("draws an all-zero tally as zeros, which is not the same as no tally", () => {
    useMameAppStore.setState({
      demuxResult: makeDemux({
        filter_stats: {
          n_input: 0,
          n_passed: 0,
          n_failed_qscore: 0,
          n_failed_length: 0,
          n_failed_barcode: 0,
        },
      }),
    });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const block = screen.getByTestId("run-qc-filter-stats");
    expect(block).toHaveAttribute("data-state", "present");
    for (const id of [
      "filter-stat-input",
      "filter-stat-passed",
      "filter-stat-qscore",
      "filter-stat-length",
      "filter-stat-barcode",
    ]) {
      expect(screen.getByTestId(id).textContent ?? "").toContain("0");
    }
    expect(block.textContent ?? "").not.toContain(en.mame.runHealth.qcNotMeasured);
  });

  it("reports the counts a filtered run produced", () => {
    useMameAppStore.setState({
      demuxResult: makeDemux({
        filter_stats: {
          n_input: 12000,
          n_passed: 9000,
          n_failed_qscore: 2000,
          n_failed_length: 900,
          n_failed_barcode: 100,
        },
      }),
    });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    expect(screen.getByTestId("filter-stat-input").textContent ?? "").toContain("12,000");
    expect(screen.getByTestId("filter-stat-passed").textContent ?? "").toContain("9,000");
  });

  it("draws an unrun barcode gate as not-measured while the other tallies read", () => {
    // A run handed no sequencing_summary: handlers/demux.py gates Q-score and
    // length from the FASTQ itself, but barcode_score is a summary-only column,
    // so that one tally comes back null. Printing 0 there would claim the gate
    // ran and cleared every read.
    useMameAppStore.setState({
      demuxResult: makeDemux({
        filter_stats: {
          n_input: 400,
          n_passed: 380,
          n_failed_qscore: 15,
          n_failed_length: 5,
          n_failed_barcode: null,
        },
      }),
    });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const block = screen.getByTestId("run-qc-filter-stats");
    expect(block).toHaveAttribute("data-state", "present");
    expect(screen.getByTestId("filter-stat-barcode").textContent ?? "").toContain(
      en.mame.runHealth.qcNotMeasured,
    );
    expect(screen.getByTestId("filter-stat-barcode").textContent ?? "").not.toContain("0");
    expect(screen.getByTestId("filter-stat-qscore").textContent ?? "").toContain("15");
  });
});

describe("RunQcSection, position recurrence", () => {
  it("separates a saved result that predates the tally from a run without one", () => {
    useMameAppStore.setState({ runQuality: makeRunQuality() });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const block = screen.getByTestId("run-qc-position-recurrence");
    expect(block).toHaveAttribute("data-state", "unavailable");
    expect(block.textContent ?? "").toContain(
      en.mame.runQuality.positionRecurrence.predatesBuild,
    );
    expect(block.textContent ?? "").not.toContain(en.mame.runQuality.positionRecurrence.noRun);
  });

  it("states that every count is a floor and cites the truncated wells", () => {
    useMameAppStore.setState({ runQuality: makeRunQuality({ position_recurrence: recurrence }) });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const line = screen.getByTestId("recurrence-lower-bound");
    expect(line).toHaveAttribute("data-lower-bound", "true");
    expect(line.textContent ?? "").toContain("40");
    expect(screen.getByTestId("recurrence-truncated").textContent ?? "").toContain("40");
    expect(screen.getByTestId("recurrence-seen").textContent ?? "").toContain("130");
  });

  it("renders an unknown weak strand share as unknown, never as zero", () => {
    useMameAppStore.setState({ runQuality: makeRunQuality({ position_recurrence: recurrence }) });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const known = screen.getByTestId("recurrence-row-512");
    expect(known).toHaveAttribute("data-share-known", "true");
    expect(known.textContent ?? "").toContain("32.0%");

    const unknownRow = screen.getByTestId("recurrence-row-900");
    expect(unknownRow).toHaveAttribute("data-share-known", "false");
    expect(unknownRow.textContent ?? "").toContain(en.mame.runHealth.qcNotMeasured);
    expect(unknownRow.textContent ?? "").not.toContain("0.0%");
  });
});

describe("RunQcSection, read length", () => {
  it("separates a report that was never read from a result that predates the block", () => {
    useMameAppStore.setState({
      runQuality: makeRunQuality({ read_length: { ...readLength, histograms: null } }),
    });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const block = screen.getByTestId("run-qc-read-length");
    expect(block).toHaveAttribute("data-state", "unavailable");
    expect(block.textContent ?? "").toContain(en.mame.runQuality.readLength.notRead);
    expect(block.textContent ?? "").not.toContain(en.mame.runQuality.readLength.predatesBuild);
  });

  it("carries the N50 ratio with the concatemer reading beside it", () => {
    useMameAppStore.setState({ runQuality: makeRunQuality({ read_length: readLength }) });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    expect(screen.getByTestId("read-length-ratio-0").textContent ?? "").toContain("1.90");
    expect(screen.getByTestId("read-length-n50-0").textContent ?? "").toContain("3,257");
    // Unconditional help copy, not a badge keyed on the value.
    expect(screen.getByTestId("run-qc-read-length").textContent ?? "").toContain(
      en.mame.runQuality.readLength.concatemerNote,
    );
    // The bucket axis counts bases, and saying so is the whole guard against
    // reading these fractions as read counts.
    expect(screen.getByTestId("run-qc-read-length").textContent ?? "").toContain(
      en.mame.runQuality.readLength.basesNote,
    );
  });

  it("labels the unlabelled entry and leaves its absent figures unknown", () => {
    useMameAppStore.setState({ runQuality: makeRunQuality({ read_length: readLength }) });
    render(<RunQcSection runHealth={makeHealth()} />);
    open();

    const entry = screen.getByTestId("read-length-entry-1");
    expect(entry.textContent ?? "").toContain(en.mame.runQuality.readLength.unlabelled);
    expect(screen.getByTestId("read-length-ratio-1").textContent ?? "").toContain(
      en.mame.runHealth.qcNotMeasured,
    );
    expect(screen.getByTestId("read-length-near-1").textContent ?? "").not.toContain("0.0%");
  });
});
