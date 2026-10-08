import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ComputeDispersionResult } from "@/types/models";

vi.mock("3dmol", () => ({
  createViewer: () => ({
    addModel: vi.fn(), setStyle: vi.fn(), addStyle: vi.fn(),
    setHoverable: vi.fn(), spin: vi.fn(), render: vi.fn(),
    setBackgroundColor: vi.fn(), clear: vi.fn(),
  }),
  SurfaceType: { VDW: 1 },
}));
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn(),
}));

import { Selection3DPanel } from "@/components/panels/Selection3DPanel";
import { useAppStore } from "@/store/appStore";

const compute = vi.fn<ReturnType<typeof useAppStore.getState>["computeDispersion"]>();

beforeEach(() => {
  compute.mockReset();
  compute.mockImplementation(async ({ positions }): Promise<ComputeDispersionResult> => ({
    accession: "AUDIT", mapped: positions.map(p => p + 10), dropped: [],
    n_positions: positions.length, mean_pairwise: 0, null_mean: 0,
    null_p05: 0, null_p95: 0, percentile: 50, klass: "na",
    n_trials: 1, seed: 0, null_hist: { min: 0, max: 0, counts: [] },
  }));
  useAppStore.setState({
    structureAccession: "AUDIT", uniprotAccession: "AUDIT", selectedGene: "0",
    seqInfo: { header: "audit", seq_length: 90, genes: [{
      gene: "audit", product: "audit", cds_start: 0, cds_end: 90,
      aa_length: 30, translation: "M" + "A".repeat(29),
    }] },
    evolveproSelectedVariants: ["A1G"],
    evolveproRankedCandidates: [
      { variant: "A1G", y_pred: 1, aa_position: 1 },
      { variant: "A2G", y_pred: 2, aa_position: 2 },
    ],
    yPredMap: { A1G: 1, A2G: 2 }, domains: [],
    fetchPdbText: async () => ({ success: true, accession: "AUDIT",
      source: "alphafold", pdb_text: "END\n" }),
    fetchActiveSite: async () => null,
    computeDispersion: compute,
  });
});

function rowValues() {
  return within(screen.getByTestId("position-row")).getAllByRole("cell")
    .slice(0, 3).map(cell => cell.textContent);
}

describe("audit selection mapping freshness", () => {
  it("maps the initial selection with current reference positions", async () => {
    // Given
    render(<Selection3DPanel defaultOpen />);
    // When
    await screen.findByTestId("position-row");
    // Then
    expect(rowValues()).toEqual(["A1G", "1", "11"]);
  });

  it("does not relabel the previous mapping as a newly selected variant", async () => {
    // Given
    render(<Selection3DPanel defaultOpen />);
    await screen.findByTestId("position-row");
    // When
    act(() => useAppStore.setState({ evolveproSelectedVariants: ["A2G"] }));
    // Then
    await waitFor(() => expect(rowValues()).toEqual(["A2G", "2", "12"]));
  });

  it("refreshes selection mapping after closing and reopening", async () => {
    // Given
    render(<Selection3DPanel defaultOpen />);
    await screen.findByTestId("position-row");
    act(() => useAppStore.setState({ evolveproSelectedVariants: ["A2G"] }));
    // When
    fireEvent.click(screen.getByTestId("panel-toggle"));
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await screen.findByTestId("position-row");
    // Then
    expect(rowValues()).toEqual(["A2G", "2", "12"]);
  });

  it("rejects a delayed mapping after returning to the original selection", async () => {
    render(<Selection3DPanel defaultOpen />);
    await screen.findByTestId("position-row");
    let finish: ((value: ComputeDispersionResult) => void) | undefined;
    compute.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    act(() => useAppStore.setState({ evolveproSelectedVariants: ["A2G"] }));
    expect(screen.queryByTestId("position-row")).not.toBeInTheDocument();
    act(() => useAppStore.setState({ evolveproSelectedVariants: ["A1G"] }));
    await waitFor(() => expect(rowValues()).toEqual(["A1G", "1", "11"]));
    await act(async () => finish?.({ accession: "AUDIT", mapped: [12], dropped: [], n_positions: 1,
      mean_pairwise: 0, null_mean: 0, null_p05: 0, null_p95: 0, percentile: 50,
      klass: "na", n_trials: 1, seed: 0, null_hist: { min: 0, max: 0, counts: [] } }));
    expect(rowValues()).toEqual(["A1G", "1", "11"]);
  });
});
