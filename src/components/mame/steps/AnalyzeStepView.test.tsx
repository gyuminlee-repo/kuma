/**
 * AnalyzeStepView.test.tsx — analyze sub-step 마운트 어설션 (D2.4, Phase G #18)
 *
 * Phase G #18: analyze.health 폐지 — RunHealthPanel이 verdict/plate에 분산 흡수됨.
 */

import { act, render, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/ipc", () => ({
  rpc: vi.fn(),
}));
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

vi.mock("@/components/ui/Panel", () => ({
  DataPanel: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="data-panel">{children}</div>
  ),
}));
vi.mock("@/components/mame/widgets/SummaryRow", () => ({
  SummaryRow: () => <div data-testid="summary-row" />,
}));
vi.mock("@/components/mame/widgets/VerdictTable", () => ({
  VerdictTable: () => <div data-testid="verdict-table" />,
}));
vi.mock("@/components/mame/widgets/PlateView", () => ({
  PlateView: () => <div data-testid="plate-view" />,
}));
vi.mock("@/components/mame/widgets/RunHealthPanel", () => ({
  RunHealthPanel: () => <div data-testid="run-health-panel" />,
}));
vi.mock("@/components/mame/panels/InputPanel", () => ({
  InputPanel: () => <div data-testid="input-panel" />,
}));
vi.mock("@/components/mame/panels/ParameterPanel", () => ({
  ParameterPanel: () => <div data-testid="parameter-panel" />,
}));

// react-resizable-panels: PanelGroup/Panel/PanelResizeHandle are passthrough wrappers
vi.mock("react-resizable-panels", () => ({
  PanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PanelResizeHandle: () => <div data-testid="resize-handle" />,
}));

import { AnalyzeStepView } from "./AnalyzeStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { RunHealthData, VerdictRecord } from "@/types/mame/models";

const fakeHealth: RunHealthData = {
  per_plate_summary: {},
  file_size_distribution: {},
  suggested_cutoff_kb: 0,
  bimodal: false,
  suggested_method: "median_minus_2sigma",
  pore_yield_pct: null,
  throughput_timeline: null,
  barcode_distribution: null,
  cross_talk_candidates: [],
};

const fakeVerdict: VerdictRecord = {
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
  n_no_call_aa: 0,
  n_span_failed: 8,
  source_path: "/data/NB01/barcode01.fastq",
  aa_sequence: "MKLVF89W",
  observed_nt_changes: ["T265G"],
  observed_aa_changes: ["F89W"],
  expected_mutations: ["F89W"],
  mutant_id: "F89W",
  verdict: "PASS",
  verdict_notes: "",
};

describe("AnalyzeStepView (Task #12 — analyze.review)", () => {
  beforeEach(() => {
    useMameAppStore.setState({ currentMameSubStep: "analyze.review" });
  });

  it("analyze.review mounts SummaryRow + VerdictTable + PlateView (unified split)", () => {
    const { getByTestId } = render(<AnalyzeStepView />);
    expect(getByTestId("summary-row")).toBeTruthy();
    expect(getByTestId("verdict-table")).toBeTruthy();
    expect(getByTestId("plate-view")).toBeTruthy();
  });

  it("analyze.review with runHealth mounts RunHealthPanel (per-plate verdict chart)", () => {
    const { getByTestId } = render(<AnalyzeStepView runHealth={fakeHealth} />);
    expect(getByTestId("run-health-panel")).toBeTruthy();
  });

  it("analyze.review without runHealth does not mount RunHealthPanel", () => {
    const { queryByTestId } = render(<AnalyzeStepView />);
    expect(queryByTestId("run-health-panel")).toBeNull();
  });

  it("moves from analyze.inputs to analyze.review after analysis succeeds", async () => {
    useMameAppStore.setState({
      currentMameSubStep: "analyze.inputs",
      isAnalyzing: true,
      validationErrors: [],
      verdicts: [],
    });
    render(<AnalyzeStepView />);

    act(() => {
      useMameAppStore.setState({
        isAnalyzing: false,
        validationErrors: [],
        verdicts: [fakeVerdict],
      });
    });

    await waitFor(() => {
      expect(useMameAppStore.getState().currentMameSubStep).toBe("analyze.review");
    });
  });
});
