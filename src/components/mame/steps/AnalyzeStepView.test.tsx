/**
 * AnalyzeStepView.test.tsx — analyze sub-step 마운트 어설션 (D2.4, Phase G #18)
 *
 * Phase G #18: analyze.health 폐지 — RunHealthPanel이 verdict/plate에 분산 흡수됨.
 */

import { render } from "@testing-library/react";
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

// react-resizable-panels: PanelGroup/Panel/PanelResizeHandle are passthrough wrappers
vi.mock("react-resizable-panels", () => ({
  PanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PanelResizeHandle: () => <div data-testid="resize-handle" />,
}));

import { AnalyzeStepView } from "./AnalyzeStepView";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { RunHealthData } from "@/types/mame/models";

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
});
