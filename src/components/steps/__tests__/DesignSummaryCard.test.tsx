/**
 * DesignSummaryCard.test.tsx — Phase B6 (#1, #15)
 *
 * [source: spec §0.1 #1 #15 — design.submit 상단 summary 카드]
 *
 * 시나리오:
 *  (a) sequence 없음 → "Not loaded"
 *  (b) pipelineMode=true, mode=single → "Pipeline (failover)"
 *  (c) mutationInputMode=multi-evolve → "All combinations"
 *  (d) variants count = mode=single이면 parsedMutations.length, 아니면 evolveproTotalCount
 *  (e) polymerase row: selectedPolymerase + codonStrategy + tmFwdTarget + maxPrimers
 */

import { render } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { DesignSummaryCard } from "../DesignSummaryCard";
import { useAppStore } from "@/store/appStore";

const baseState = {
  seqInfo: null,
  mutationInputMode: "text" as const,
  pipelineMode: false,
  evolveproTotalCount: 0,
  parsedMutations: [],
  selectedPolymerase: "Q5",
  codonStrategy: "closest" as const,
  tmFwdTarget: 60,
  maxPrimers: 10,
};

describe("DesignSummaryCard (Phase B6)", () => {
  beforeEach(() => {
    useAppStore.setState(baseState as never);
  });

  it("(a) renders 'Not loaded' when seqInfo is null", () => {
    const { getByText } = render(<DesignSummaryCard />);
    expect(getByText("Not loaded")).toBeTruthy();
  });

  it("(a) renders sequence header + length when seqInfo present", () => {
    useAppStore.setState({
      seqInfo: { header: "MyGene", seq_length: 1200, genes: [] },
    } as never);
    const { getByText } = render(<DesignSummaryCard />);
    expect(getByText(/MyGene/)).toBeTruthy();
    expect(getByText(/1200 nt/)).toBeTruthy();
  });

  it("(b) selection mode reads 'Pipeline (failover)' when pipelineMode=true and mode!=multi-evolve", () => {
    useAppStore.setState({
      pipelineMode: true,
      mutationInputMode: "text",
    } as never);
    const { getByText } = render(<DesignSummaryCard />);
    expect(getByText("Pipeline (failover)")).toBeTruthy();
  });

  it("(b) selection mode reads 'Top-N only' when pipelineMode=false and mode!=multi-evolve", () => {
    useAppStore.setState({
      pipelineMode: false,
      mutationInputMode: "evolvepro",
    } as never);
    const { getByText } = render(<DesignSummaryCard />);
    expect(getByText("Top-N only")).toBeTruthy();
  });

  it("(c) selection mode = 'All combinations' when mode=multi-evolve (regardless of pipelineMode)", () => {
    useAppStore.setState({
      pipelineMode: true,
      mutationInputMode: "multi-evolve",
    } as never);
    const { getByText } = render(<DesignSummaryCard />);
    expect(getByText("All combinations")).toBeTruthy();
  });

  it("(d) variant count uses parsedMutations.length in 'single' mode", () => {
    useAppStore.setState({
      mutationInputMode: "text",
      parsedMutations: [
        { raw: "A1V", wt_aa: "A", position: 1, mt_aa: "V" },
        { raw: "L2P", wt_aa: "L", position: 2, mt_aa: "P" },
        { raw: "K3R", wt_aa: "K", position: 3, mt_aa: "R" },
      ],
      evolveproTotalCount: 999,
    } as never);
    const { getByTestId } = render(<DesignSummaryCard />);
    expect(getByTestId("design-summary-variants").textContent).toBe("3");
  });

  it("(d) variant count uses evolveproTotalCount in non-single modes", () => {
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      parsedMutations: [],
      evolveproTotalCount: 42,
    } as never);
    const { getByTestId } = render(<DesignSummaryCard />);
    expect(getByTestId("design-summary-variants").textContent).toBe("42");
  });

  it("(e) polymerase row includes selectedPolymerase, codonStrategy, Tm, maxPrimers", () => {
    useAppStore.setState({
      selectedPolymerase: "PrimeSTAR",
      codonStrategy: "optimal",
      tmFwdTarget: 65,
      maxPrimers: 24,
    } as never);
    const { getByTestId } = render(<DesignSummaryCard />);
    const cell = getByTestId("design-summary-polymerase").textContent || "";
    expect(cell).toContain("PrimeSTAR");
    expect(cell).toContain("optimal");
    expect(cell).toContain("65");
    expect(cell).toContain("24");
  });
});
