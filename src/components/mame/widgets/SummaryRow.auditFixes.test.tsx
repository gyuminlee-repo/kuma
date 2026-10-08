import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { SummaryRow } from "@/components/mame/widgets/SummaryRow";
import { useMameAppStore } from "@/store/mame/mameAppStore";

describe("audit summary readiness", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      verdicts: [], wells: [], runHealth: null, validationErrors: [],
      isAnalyzing: false, analyzeDurationMs: null,
      inputMode: "raw_run", inputDir: "/run", expectedPath: "/expected.csv",
      referencePath: "/reference.fasta", outputPath: "/output",
      rawRunParams: {
        ...useMameAppStore.getState().rawRunParams,
        customBarcodesPath: "",
      },
    });
  });

  it("does not label four of five raw inputs ready", () => {
    // Given: the raw barcode input is absent.
    expect(useMameAppStore.getState().rawRunParams.customBarcodesPath).toBe("");
    // When
    render(<SummaryRow />);
    // Then
    expect(screen.getAllByRole("status")[2]).toHaveTextContent("80%");
    expect(screen.getAllByRole("status")[3]).toHaveTextContent("Draft setup");
  });

  it("labels all five raw inputs ready", () => {
    // Given
    useMameAppStore.setState({ rawRunParams: {
      ...useMameAppStore.getState().rawRunParams,
      customBarcodesPath: "/barcodes.fasta",
    } });
    // When
    render(<SummaryRow />);
    // Then
    expect(screen.getAllByRole("status")[2]).toHaveTextContent("100%");
    expect(screen.getAllByRole("status")[3]).toHaveTextContent("Ready to run");
  });

  it("keeps the four-input consensus control ready", () => {
    // Given
    useMameAppStore.setState({ inputMode: "consensus" });
    // When
    render(<SummaryRow />);
    // Then
    expect(screen.getAllByRole("status")[2]).toHaveTextContent("100%");
    expect(screen.getAllByRole("status")[3]).toHaveTextContent("Ready to run");
  });
});
