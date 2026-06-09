/**
 * DesignSummaryCard.test.tsx — Phase B6 (#1, #15)
 *
 * [source: spec §0.1 #1 #15 — design.submit 상단 summary 카드]
 *
 * 시나리오:
 *  (a) sequence 없음 → "Not loaded"
 *  (b) pipelineMode=true, mode=single → "Pipeline (failover)"
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
  evolveproMode: "topN" as const,
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

  it("(b) selection mode reads 'Pipeline (failover)' when evolveproMode=pipeline", () => {
    useAppStore.setState({
      evolveproMode: "pipeline",
      mutationInputMode: "text",
    } as never);
    const { getByText } = render(<DesignSummaryCard />);
    expect(getByText("Pipeline (failover)")).toBeTruthy();
  });

  it("(b) selection mode reads 'Top-N only' when evolveproMode=topN", () => {
    useAppStore.setState({
      evolveproMode: "topN",
      mutationInputMode: "evolvepro",
    } as never);
    const { getByText } = render(<DesignSummaryCard />);
    expect(getByText("Top-N only")).toBeTruthy();
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
