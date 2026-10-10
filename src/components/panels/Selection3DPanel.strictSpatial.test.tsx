import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ addModel: vi.fn(), addStyle: vi.fn(), setStyle: vi.fn(), setHoverable: vi.fn(), addLabel: vi.fn(), zoomTo: vi.fn() }));
vi.mock("3dmol", () => ({ createViewer: () => ({
  addModel: mocks.addModel, setStyle: mocks.setStyle, addStyle: mocks.addStyle,
  setHoverable: mocks.setHoverable, addLabel: mocks.addLabel, spin: vi.fn(), render: vi.fn(), setBackgroundColor: vi.fn(), clear: vi.fn(),
  zoomTo: mocks.zoomTo,
}), SurfaceType: { VDW: 1 } }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
import { useAppStore } from "@/store/appStore";
import { distinctSpatial95Fixture, strictSpatialFixture } from "@/test-utils/strictSpatialFixture";
import { strictSpatialContextKey } from "@/lib/strictSpatial";
import { importedSpatialFixture, predictionBundleInventory } from "@/test-utils/predictionBundleFixture";
import { Selection3DPanel } from "./Selection3DPanel";

beforeEach(() => {
  vi.clearAllMocks();
  useAppStore.setState({
    strictSpatialEnabled: true, structuralDiversityEnabled: true,
    strictStructureSource: "accession", predictionBundleRevision: 0,
    strictSpatialBudgetMode: "unique_sites", strictSpatialSiteCap: null,
    evolveproMode: "pipeline", mutationInputMode: "evolvepro", maxPrimers: 2,
    structureAccession: "P12345", uniprotAccession: "P12345", selectedGene: "0",
    seqInfo: { header: "fixture", seq_length: 15, genes: [{ gene: "fixture", product: "fixture", cds_start: 0, cds_end: 15, aa_length: 5, translation: "MAAAA" }] },
    evolveproSelectedVariants: ["A2G", "A4V"],
    evolveproRankedCandidates: ["A2G", "A4V", "A5G"].map((variant, i) => ({ variant, aa_position: [2, 4, 5][i], y_pred: 2 - i })),
    yPredMap: { A2G: 2, A4V: 1, A5G: 0 }, domains: [{ id: "D1", db: "test", name: "unverified domain", start: 1, end: 30 }],
    fetchPdbText: vi.fn(async () => null), computeDispersion: vi.fn(async () => null),
    predictStructureEsmfold: vi.fn(async () => null),
    fetchActiveSite: vi.fn(async () => ({ accession: "P12345", source: "uniprot", has_annotation: true,
      active_site_positions: [12], binding_positions: [14], annotation_status: "present" as const, projection_status: "unverified" as const,
      features: [{ type: "Active site", source_accession: "OTHER", coordinate_frame: "accession",
        location: { start: { value: 12, modifier: "UNCERTAIN" }, end: { value: 14 } },
        evidences: [{ evidenceCode: "ECO:0000269", source: "PubMed", id: "123" }], ligand: { name: "Metal" } }],
    })),
  });
  useAppStore.setState({ strictSpatialSelection: { result: strictSpatialFixture(), contextKey: strictSpatialContextKey(useAppStore.getState()) } });
});

describe("imported prediction viewer", () => {
  function setImported() {
    const report = importedSpatialFixture();
    report.mapping[0] = { ...report.mapping[0], structure_position: -3, insertion_code: "A" };
    useAppStore.setState({ strictStructureSource: "prediction_bundle", predictionBundlePath: "/tmp/prediction.zip",
      predictionBundleInventory: predictionBundleInventory(), predictionBundleModelId: report.prediction_bundle.model_id,
      predictionBundleChainId: report.prediction_bundle.chain_id });
    useAppStore.setState({ strictSpatialSelection: { result: report, contextKey: strictSpatialContextKey(useAppStore.getState()) } });
    return report;
  }

  it("renders only the certified local structure using display identities and keeps original residue evidence", async () => {
    const report = setImported();
    render(<Selection3DPanel defaultOpen />);
    const rows = await screen.findAllByTestId("position-row");
    // Ready-state rows commit before the separate passive styling effect.
    // Wait for the viewer contract itself, not only its surrounding DOM.
    await waitFor(() => {
      expect(mocks.addModel).toHaveBeenCalledWith(report.pdb_text, "pdb");
      expect(mocks.setStyle).toHaveBeenCalledWith({}, { cartoon: { color: "gray", style: "trace" } });
      expect(mocks.addStyle).toHaveBeenCalledWith({ resi: 2, chain: "A" }, expect.any(Object));
    });
    expect(within(rows[0]).getAllByRole("cell")[2]).toHaveTextContent("-3A");
    expect(within(rows[0]).getAllByRole("cell")[2]).toHaveAttribute("title", "Original chain X, residue -3A → viewer residue 2");
    expect(mocks.addStyle.mock.calls.some(([selection]) => selection.resi === -3)).toBe(false);
    fireEvent.click(rows[0]);
    expect(mocks.zoomTo).toHaveBeenCalledWith({ resi: 2, chain: "A" }, 500);
    expect(screen.getByText(/only the selected protein chain’s Cα atoms/)).toBeInTheDocument();
    for (const method of ["fetchPdbText", "fetchActiveSite", "computeDispersion", "predictStructureEsmfold"] as const) {
      expect(useAppStore.getState()[method]).not.toHaveBeenCalled();
    }
    expect(screen.queryByRole("button", { name: "Surface" })).not.toBeInTheDocument();
  });

  it("reads selected-site pLDDT from paired reference evidence and retains unknown confidence", async () => {
    setImported();
    render(<Selection3DPanel defaultOpen />);
    const rows = await screen.findAllByTestId("position-row");
    // Display PDB B fields do not define imported confidence, even when nonzero.
    expect(rows.map((row) => within(row).getAllByRole("cell")[6].textContent)).toEqual(["20.0", "–"]);
    expect(screen.getByText(/pLDDT available for 3 of 5 residues/)).toBeInTheDocument();
    expect(screen.getByText(/Low pLDDT does not establish a nonfunctional region/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "pLDDT" }));
    await waitFor(() => expect(mocks.setStyle).toHaveBeenCalledWith(
      { resi: 2, chain: "A" }, { cartoon: { style: "trace", color: expect.any(String) } }));
    expect(mocks.setStyle.mock.calls.some(([selection]) => selection.resi === 4)).toBe(false);
  });

  it("does not infer zero PAE or show prediction fallback labels when accession is absent", async () => {
    const report = setImported();
    report.prediction_bundle = { ...report.prediction_bundle, pae: { status: "unavailable", source: null,
      dimension: 5, mean: null, max: null, scope: "selected-chain-polymer", directional: true } };
    useAppStore.setState({ uniprotAccession: "", structureAccession: "",
      strictSpatialSelection: { result: report, contextKey: strictSpatialContextKey(useAppStore.getState()) } });
    render(<Selection3DPanel defaultOpen />);
    await screen.findAllByTestId("position-row");
    expect(screen.getByText(/PAE: Unknown \/ unavailable/)).toBeInTheDocument();
    expect(screen.queryByTestId("esmfold-no-accession-note")).not.toBeInTheDocument();
    expect(useAppStore.getState().predictStructureEsmfold).not.toHaveBeenCalled();
  });
});

describe("verified strict spatial viewer", () => {
  it("keeps all 95 variant rows across five sites and lists repeated substitutions on hover", async () => {
    const report = distinctSpatial95Fixture();
    useAppStore.setState({ maxPrimers: 95, strictSpatialBudgetMode: "distinct_variants",
      evolveproSelectedVariants: report.selected_variants, yPredMap: Object.fromEntries(report.selected_variants.map((variant, i) => [variant, 95 - i])) });
    useAppStore.setState({ strictSpatialSelection: { result: report, contextKey: strictSpatialContextKey(useAppStore.getState()) } });
    render(<Selection3DPanel defaultOpen />);
    const rows = await screen.findAllByTestId("position-row");
    expect(rows).toHaveLength(95);
    expect(screen.getByTestId("strict-selection-counts")).toHaveTextContent("95 selected variants across 5 unique sites");
    expect(rows.map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(report.selected_variants);
    expect(new Set(rows.map((row) => within(row).getAllByRole("cell")[1].textContent)).size).toBe(5);
    await waitFor(() => expect(mocks.setHoverable.mock.calls.at(-1)?.[2]).toBeTypeOf("function"));
    const hover = mocks.setHoverable.mock.calls.at(-1)?.[2];
    act(() => hover({ resi: 12, chain: "A", resn: "ALA" }));
    const hoverLabel = mocks.addLabel.mock.calls.at(-1)?.[0];
    for (const variant of report.selected_variants.slice(0, 19)) expect(hoverLabel).toContain(variant);
  });

  it("draws the certificate PDB and selected IDs using its mapping", async () => {
    // The certificate, not independently parsed/ranked positions, owns mapping.
    useAppStore.setState({ evolveproRankedCandidates: [{ variant: "A2G", aa_position: 999, y_pred: 2 }] });
    render(<Selection3DPanel defaultOpen />);
    const rows = await screen.findAllByTestId("position-row");
    expect(rows.map((row) => within(row).getAllByRole("cell").slice(0, 3).map((cell) => cell.textContent)))
      .toEqual([["A2G", "2", "12"], ["A4V", "4", "14"]]);
    await waitFor(() => {
      expect(mocks.addModel).toHaveBeenCalledWith(strictSpatialFixture().pdb_text, "pdb");
      expect(mocks.addStyle).toHaveBeenCalledWith({ resi: 12, chain: "A" }, expect.objectContaining({ sphere: expect.any(Object) }));
    });
    expect(useAppStore.getState().fetchPdbText).not.toHaveBeenCalled();
    expect(useAppStore.getState().computeDispersion).not.toHaveBeenCalled();
    expect(screen.queryByTestId("upload-input")).not.toBeInTheDocument();
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
