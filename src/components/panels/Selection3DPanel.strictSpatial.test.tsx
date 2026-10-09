import { act, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ addModel: vi.fn(), addStyle: vi.fn(), setStyle: vi.fn() }));
vi.mock("3dmol", () => ({ createViewer: () => ({
  addModel: mocks.addModel, setStyle: mocks.setStyle, addStyle: mocks.addStyle,
  setHoverable: vi.fn(), spin: vi.fn(), render: vi.fn(), setBackgroundColor: vi.fn(), clear: vi.fn(),
}), SurfaceType: { VDW: 1 } }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
import { useAppStore } from "@/store/appStore";
import { strictSpatialFixture } from "@/test-utils/strictSpatialFixture";
import { strictSpatialContextKey } from "@/lib/strictSpatial";
import { Selection3DPanel } from "./Selection3DPanel";

beforeEach(() => {
  vi.clearAllMocks();
  useAppStore.setState({
    strictSpatialEnabled: true, structuralDiversityEnabled: true,
    evolveproMode: "pipeline", mutationInputMode: "evolvepro", maxPrimers: 2,
    structureAccession: "P12345", uniprotAccession: "P12345", selectedGene: "0",
    seqInfo: { header: "fixture", seq_length: 15, genes: [{ gene: "fixture", product: "fixture", cds_start: 0, cds_end: 15, aa_length: 5, translation: "MAAAA" }] },
    evolveproSelectedVariants: ["A2G", "A4V"],
    evolveproRankedCandidates: ["A2G", "A4V", "A5G"].map((variant, i) => ({ variant, aa_position: [2, 4, 5][i], y_pred: 2 - i })),
    yPredMap: { A2G: 2, A4V: 1, A5G: 0 }, domains: [{ id: "D1", db: "test", name: "unverified domain", start: 1, end: 30 }],
    fetchPdbText: vi.fn(async () => null), computeDispersion: vi.fn(async () => null),
    fetchActiveSite: vi.fn(async () => ({ accession: "P12345", source: "uniprot", has_annotation: true,
      active_site_positions: [12], binding_positions: [14], annotation_status: "present" as const, projection_status: "unverified" as const,
      features: [{ type: "Active site", source_accession: "OTHER", coordinate_frame: "accession",
        location: { start: { value: 12, modifier: "UNCERTAIN" }, end: { value: 14 } },
        evidences: [{ evidenceCode: "ECO:0000269", source: "PubMed", id: "123" }], ligand: { name: "Metal" } }],
    })),
  });
  useAppStore.setState({ strictSpatialSelection: { result: strictSpatialFixture(), contextKey: strictSpatialContextKey(useAppStore.getState()) } });
});

describe("verified strict spatial viewer", () => {
  it("draws the certificate PDB and selected IDs using its mapping", async () => {
    // The certificate, not independently parsed/ranked positions, owns mapping.
    useAppStore.setState({ evolveproRankedCandidates: [{ variant: "A2G", aa_position: 999, y_pred: 2 }] });
    render(<Selection3DPanel defaultOpen />);
    const rows = await screen.findAllByTestId("position-row");
    expect(rows.map((row) => within(row).getAllByRole("cell").slice(0, 3).map((cell) => cell.textContent)))
      .toEqual([["A2G", "2", "12"], ["A4V", "4", "14"]]);
    expect(mocks.addModel).toHaveBeenCalledWith(strictSpatialFixture().pdb_text, "pdb");
    expect(useAppStore.getState().fetchPdbText).not.toHaveBeenCalled();
    expect(useAppStore.getState().computeDispersion).not.toHaveBeenCalled();
    expect(screen.queryByTestId("upload-input")).not.toBeInTheDocument();
    expect(mocks.addStyle).toHaveBeenCalledWith({ resi: 12, chain: "A" }, expect.objectContaining({ sphere: expect.any(Object) }));
  });
  it("preserves uncertain raw evidence without asserting function on selected residues", async () => {
    render(<Selection3DPanel defaultOpen />);
    await waitFor(() => expect(screen.getByTestId("functional-annotation-evidence")).toHaveTextContent("ECO:0000269"));
    expect(screen.getByTestId("functional-annotation-evidence")).toHaveTextContent("projection onto this structure is unverified");
    for (const row of screen.getAllByTestId("position-row")) {
      expect(within(row).getAllByRole("cell").slice(4, 6).map((cell) => cell.textContent)).toEqual(["–", "–"]);
      expect(row).not.toHaveTextContent("unverified domain");
    }
    expect(mocks.addStyle.mock.calls.some(([, style]) => "stick" in style)).toBe(false);
    expect(screen.queryByTestId("domain-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("active-site-control")).not.toBeInTheDocument();
  });
  it("never replaces an empty certified selection with all ranked candidates", async () => {
    render(<Selection3DPanel defaultOpen />);
    await screen.findAllByTestId("position-row");
    act(() => useAppStore.setState({ evolveproSelectedVariants: [] }));
    await waitFor(() => expect(screen.queryByTestId("position-row")).not.toBeInTheDocument());
    expect(screen.queryByTestId("fallback-note")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Reselect a verified");
  });
  it("shows unknown scores as unavailable instead of numeric zero", async () => {
    const previous = useAppStore.getState().strictSpatialSelection;
    expect(previous).not.toBeNull();
    if (!previous) return;
    useAppStore.setState({ strictSpatialSelection: { ...previous, result: { ...previous.result, score_available: false } } });
    render(<Selection3DPanel defaultOpen />);
    const rows = await screen.findAllByTestId("position-row");
    expect(rows.map((row) => within(row).getAllByRole("cell")[3].textContent)).toEqual(["–", "–"]);
  });
});
