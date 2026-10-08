/**
 * DesignSummaryCard.test.tsx — Phase B6 (#1, #15)
 *
 * [source: spec §0.1 #1 #15 — design.submit 상단 summary 카드]
 *
 * 시나리오:
 *  (a) sequence 없음 → "Not loaded"
 *  (b) pipelineMode=true, mode=single → "Pipeline (failover)"
 *  (d) variants = the count the design run is sent (prepareDesignInput), and in
 *      EVOLVEpro mode that count over the CSV candidate count
 *  (e) polymerase row: selectedPolymerase + tmFwdTarget + maxPrimers (no codon strategy)
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
  evolveproSelectedVariants: [],
  evolveproRankedCandidates: [],
  mutationText: "",
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

  it("(d) EVOLVEpro shows the variants the design is sent over the CSV candidates", () => {
    // The saved project that reported this: 95 selected, 200 in the CSV.
    const selected = Array.from({ length: 95 }, (_, i) => `M${i + 1}A`);
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      maxPrimers: 95,
      evolveproTotalCount: 200,
      evolveproSelectedVariants: selected,
      mutationText: selected.join("\n"),
    } as never);
    const { getByTestId } = render(<DesignSummaryCard />);
    expect(getByTestId("design-summary-variants").textContent).toBe("95 / 200 candidates");
  });

  it("(d) the design count caps the EVOLVEpro selection it reports", () => {
    const selected = Array.from({ length: 120 }, (_, i) => `M${i + 1}A`);
    useAppStore.setState({
      mutationInputMode: "evolvepro",
      maxPrimers: 100,
      evolveproTotalCount: 200,
      evolveproSelectedVariants: selected,
    } as never);
    const { getByTestId } = render(<DesignSummaryCard />);
    expect(getByTestId("design-summary-variants").textContent).toBe("100 / 200 candidates");
  });

  it("(d) typed mutations count the lines the design is sent, not 0", () => {
    useAppStore.setState({
      mutationInputMode: "text",
      maxPrimers: 10,
      evolveproTotalCount: 0,
      mutationText: "A1G\n# comment\n\nK2R\nL3P\n",
    } as never);
    const { getByTestId } = render(<DesignSummaryCard />);
    expect(getByTestId("design-summary-variants").textContent).toBe("3");
  });

  it("(e) polymerase row includes selectedPolymerase, Tm, maxPrimers and omits codon strategy", () => {
    useAppStore.setState({
      selectedPolymerase: "PrimeSTAR",
      // Still in the store for old projects, but the operator can no longer set
      // it, so the summary must not report it.
      codonStrategy: "optimal",
      tmFwdTarget: 65,
      maxPrimers: 24,
    } as never);
    const { getByTestId } = render(<DesignSummaryCard />);
    const cell = getByTestId("design-summary-polymerase").textContent || "";
    expect(cell).toContain("PrimeSTAR");
    expect(cell).not.toContain("optimal");
    expect(cell).toContain("65");
    expect(cell).toContain("24");
  });
});
