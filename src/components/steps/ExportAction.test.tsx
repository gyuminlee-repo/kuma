import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SdmPrimerResult } from "@/types/models";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn(),
}));
vi.mock("@/state/projectContext", () => ({
  useKumaProject: () => ({ project_id: "project", path: "/project" }),
}));
vi.mock("@/components/layout/export-handlers", () => ({ handleExportAll: vi.fn() }));
const { toastWarning, toastError } = vi.hoisted(() => ({ toastWarning: vi.fn(), toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { warning: toastWarning, error: toastError } }));

import { handleExportAll } from "@/components/layout/export-handlers";
import { useAppStore } from "@/store/appStore";
import { ExportAction } from "./ExportAction";
import { wellName } from "@/lib/plate-utils";

const exportAll = vi.mocked(handleExportAll);
function seed(count = 1) {
  const results: SdmPrimerResult[] = Array.from({ length: count }, (_, i) => ({
    mutation: `M${i + 1}A`, aa_position: i + 1, codon_pos: 0,
    forward_seq: `F${i}`, reverse_seq: `R${i}`, fwd_len: 20, rev_len: 20, overlap_len: 18,
    tm_no_fwd: 62, tm_no_rev: 58, tm_overlap: 42, tm_condition_met: true,
    tolerance_used: 1, has_offtarget: false, penalty: 0, gc_fwd: 50, gc_rev: 50,
    wt_codon: "ATG", mt_codon: "GCG", overlap_seq: "ATGC", warnings: [],
  }));
  useAppStore.setState({
    designResults: results,
    plateMappings: results.map((r, i) => ({
      well: wellName(i), primer_name: `${r.mutation}_F`, sequence: r.forward_seq,
      mutation: r.mutation, primer_type: "forward",
    })),
    dedupInfo: {}, tableSorting: [], yPredMap: {}, customCandidates: {},
    exportName: "Test", exportPlateNames: {
      single: { fwd: "FWD", rvs: "REV" }, R1: { fwd: "F1", rvs: "R1" }, R2: { fwd: "F2", rvs: "R2" },
    },
    exportAmount: "0.2", exportVectormaps: true,
    echoTransferVol: 50, janusTransferVol: 2,
    echoQuadrant: null, echoUsedQuadrants: [],
    echoRoundPicks: [{ plate: 1, quadrant: "A1" }, { plate: 1, quadrant: "A2" }],
  });
}
function pendingExport() {
  let finish: (value: null) => void = () => {};
  const promise = new Promise<null>((resolve) => { finish = resolve; });
  exportAll.mockReturnValueOnce(promise);
  return () => finish(null);
}

beforeEach(() => {
  seed();
  exportAll.mockReset().mockResolvedValue(null);
  toastWarning.mockClear();
  toastError.mockClear();
});

describe("ExportAction", () => {
  it("invokes the existing export handler with the current persisted options", async () => {
    render(<ExportAction />);
    fireEvent.click(screen.getByRole("button", { name: /^export$/i }));
    await waitFor(() => expect(exportAll).toHaveBeenCalledOnce());
    expect(exportAll).toHaveBeenCalledWith({
      projectId: "project", projectPath: "/project", projectName: "Test",
      fwdPlateName: "FWD", rvsPlateName: "REV", amount: "0.2", vectormaps: true,
      echoTransferVol: 50, janusTransferVol: 2, quadrant: null, usedQuadrants: [], bom: false,
    });
  });

  it("blocks repeated clicks until the destination/export promise settles, then permits retry after cancel", async () => {
    const finish = pendingExport();
    render(<ExportAction />);
    const button = screen.getByRole("button");
    act(() => { button.click(); button.click(); });
    expect(exportAll).toHaveBeenCalledOnce();
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(exportAll).toHaveBeenCalledOnce();
    await act(async () => { finish(); });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(exportAll).toHaveBeenCalledTimes(2));
  });

  it("reports a rejected destination/export promise and releases the pending guard for retry", async () => {
    exportAll.mockRejectedValueOnce(new Error("Destination unavailable"));
    render(<ExportAction />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(toastError).toHaveBeenCalledWith("Export failed", {
      description: "Destination unavailable", duration: 8000,
    }));
    expect(screen.getByRole("button")).toBeEnabled();
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(exportAll).toHaveBeenCalledTimes(2));
  });

  it("preserves click-time validation for missing names and empty results", () => {
    useAppStore.setState({ exportPlateNames: {}, designResults: [] });
    render(<ExportAction />);
    const button = screen.getByRole("button");
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(toastWarning).toHaveBeenCalledOnce();
    expect(exportAll).not.toHaveBeenCalled();
  });

  it("keeps an invalid export name disabled", () => {
    useAppStore.setState({ exportName: "bad/name" });
    render(<ExportAction />);
    expect(screen.getByRole("button")).toBeDisabled();
    fireEvent.click(screen.getByRole("button"));
    expect(exportAll).not.toHaveBeenCalled();
  });

  it("keeps placement warnings and does not invoke export for spent columns", () => {
    useAppStore.setState({ echoQuadrant: "A1", echoUsedQuadrants: ["A1"] });
    render(<ExportAction />);
    fireEvent.click(screen.getByRole("button"));
    expect(toastWarning).toHaveBeenCalledOnce();
    expect(exportAll).not.toHaveBeenCalled();
  });

  it("disables every round while one exports, retaining that round's exact payload", async () => {
    seed(97);
    const finish = pendingExport();
    render(<ExportAction />);
    const first = screen.getByRole("button", { name: "Export round 1" });
    const second = screen.getByRole("button", { name: "Export round 2" });
    act(() => { second.click(); first.click(); });
    expect(exportAll).toHaveBeenCalledOnce();
    for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
    expect(exportAll).toHaveBeenCalledWith(expect.objectContaining({
      fwdPlateName: "F2", rvsPlateName: "R2", quadrant: "A2", usedQuadrants: ["A1"],
      round: expect.objectContaining({ label: "R2", sourcePlate: 1, mappings: [expect.objectContaining({ mutation: "M97A", well: "A1" })] }),
    }));
    await act(async () => { finish(); });
    expect(screen.getByRole("button", { name: "Export round 1" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export round 2" })).toBeEnabled();
  });
});
