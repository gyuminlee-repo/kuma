import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { MameInspectorContent } from "./MameInspectorContent";
import { useMameAppStore } from "@/store/mame/mameAppStore";

describe("MameInspectorContent", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      currentMameSubStep: "setup.files",
      inputDir: "",
      expectedPath: "",
      verdicts: [],
      selectedWell: null,
    });
  });

  it("shows the selected run folder without fabricated device or kit values", () => {
    useMameAppStore.setState({
      currentMameSubStep: "setup.files",
      inputDir: "/runs/run42",
    });

    render(<MameInspectorContent />);

    expect(screen.getByText("run42")).toBeInTheDocument();
    expect(screen.queryByText("Oxford Nanopore")).not.toBeInTheDocument();
    expect(screen.queryByText("SQK-NBD114-24")).not.toBeInTheDocument();
  });

  it("shows the selected expected mutation file without barcode placeholders", () => {
    useMameAppStore.setState({
      currentMameSubStep: "setup.design",
      expectedPath: "/runs/expected.xlsx",
    });

    render(<MameInspectorContent />);

    expect(screen.getByText("expected.xlsx")).toBeInTheDocument();
    expect(screen.queryByText("BC01")).not.toBeInTheDocument();
    expect(screen.queryByText("~500")).not.toBeInTheDocument();
  });

  it("summarizes merge readiness from verdicts without fabricated variant or status values", () => {
    useMameAppStore.setState({
      currentMameSubStep: "activity.signals",
      verdicts: [
        {
          native_barcode: "NB01",
          custom_barcode: "",
          verdict: "PASS",
          read_count: 1200,
          verdict_notes: "",
          file_size_kb: 30,
          n_mixed_positions: 0,
          max_minor_allele_fraction: 0,
          n_low_depth_positions: 0,
          consensus_n_fraction: 0,
          n_low_quality_bases: 0,
          n_input_reads: 1200,
          n_aligned_reads: 1190,
          n_mapq_failed: 0,
          n_span_failed: 0,
          source_path: "",
          aa_sequence: "",
          observed_nt_changes: [],
          observed_aa_changes: ["A1V"],
          n_no_call_aa: 0,
          expected_mutations: ["A1V"],
          mutant_id: "A1V",
        },
        {
          native_barcode: "NB02",
          custom_barcode: "",
          verdict: "NO_CALL",
          read_count: 200,
          verdict_notes: "",
          file_size_kb: 12,
          n_mixed_positions: 0,
          max_minor_allele_fraction: 0,
          n_low_depth_positions: 0,
          consensus_n_fraction: 0,
          n_low_quality_bases: 0,
          n_input_reads: 200,
          n_aligned_reads: 180,
          n_mapq_failed: 0,
          n_span_failed: 0,
          source_path: "",
          aa_sequence: "",
          observed_nt_changes: [],
          observed_aa_changes: [],
          n_no_call_aa: 1,
          expected_mutations: [],
          mutant_id: "",
        },
      ],
    });

    render(<MameInspectorContent />);

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.queryByText("R585A")).not.toBeInTheDocument();
    expect(screen.queryByText("Ready")).not.toBeInTheDocument();
  });
});
