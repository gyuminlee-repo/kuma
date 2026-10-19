/**
 * Selection3DPanel: what happens when the structure found for the accession does
 * not exactly cover the reference sequence. Network and the viewer are mocked.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockBrowseFile = vi.hoisted(() =>
  vi.fn<(filters: unknown, onPick: (path: string) => void) => Promise<void>>(),
);

vi.mock("@tauri-apps/plugin-dialog", () => ({ save: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ writeFile: vi.fn() }));
vi.mock("@/lib/file-utils", () => ({ browseFile: mockBrowseFile }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: vi.fn(), setProgressHandler: vi.fn() }));
vi.mock("3dmol", () => ({
  createViewer: vi.fn(() => ({
    addModel: vi.fn(), setStyle: vi.fn(), addStyle: vi.fn(), setHoverable: vi.fn(), render: vi.fn(),
    setBackgroundColor: vi.fn(), spin: vi.fn(), zoomTo: vi.fn(), clear: vi.fn(), getCanvas: vi.fn(),
    removeAllModels: vi.fn(), removeAllSurfaces: vi.fn(), removeAllLabels: vi.fn(), addLabel: vi.fn(),
  })),
  SurfaceType: { VDW: 1, MS: 2, SAS: 3, SES: 4 },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key.split(".").pop() ?? key }),
}));

type Outcome = "used" | "refused" | "failed" | "stale";
interface StoreShape {
  structureAccession: string;
  uniprotAccession: string;
  seqInfo: { header: string; seq_length: number; genes: Array<Record<string, unknown>> } | null;
  selectedGene: string;
  evolveproSelectedVariants: string[];
  evolveproRankedCandidates: unknown[];
  yPredMap: Record<string, number>;
  domains: unknown[];
  structure3dState: string;
  structureCoverage: { covered: number; reference_length: number } | null;
  fetchPdbText: ReturnType<typeof vi.fn>;
  fetchActiveSite: ReturnType<typeof vi.fn>;
  computeDispersion: ReturnType<typeof vi.fn>;
  predictStructureEsmfold: ReturnType<typeof vi.fn>;
  adoptReferenceEsmfold: ReturnType<typeof vi.fn<(sequence: string) => Promise<Outcome>>>;
  loadStructureFile: ReturnType<typeof vi.fn>;
}

const storeRef: { current: StoreShape } = vi.hoisted(() => ({ current: {} as StoreShape }));

vi.mock("@/store/appStore", () => ({
  useAppStore: (selector: (s: StoreShape) => unknown) => selector(storeRef.current),
}));

import { createViewer } from "3dmol";
import { strictSpatialContextKey } from "@/lib/strictSpatial";
import type { AppState } from "@/store/types";
import { Selection3DPanel } from "./Selection3DPanel";

function seqInfo(length: number) {
  return {
    header: ">t",
    seq_length: length,
    genes: [{ gene: "T", product: "t", cds_start: 1, cds_end: length * 3, aa_length: length,
      translation: "M" + "A".repeat(length - 1) }],
  };
}

function setStore(patch: Partial<StoreShape> & Record<string, unknown> = {}) {
  storeRef.current = {
    structureAccession: "",
    uniprotAccession: "P12345",
    seqInfo: seqInfo(100),
    selectedGene: "",
    evolveproSelectedVariants: [],
    evolveproRankedCandidates: [],
    yPredMap: {},
    domains: [],
    structure3dState: "off",
    structureCoverage: null,
    fetchPdbText: vi.fn().mockResolvedValue(null),
    fetchActiveSite: vi.fn().mockResolvedValue(null),
    computeDispersion: vi.fn().mockResolvedValue(null),
    predictStructureEsmfold: vi.fn().mockResolvedValue(null),
    adoptReferenceEsmfold: vi.fn<(sequence: string) => Promise<Outcome>>().mockResolvedValue("used"),
    loadStructureFile: vi.fn(),
    ...patch,
  } as StoreShape;
}

/** A store in strict spatial mode with a current certificate for the given structure. */
function setStrictStore(accession: string) {
  const base = {
    structureAccession: accession,
    evolveproSelectedVariants: ["A2V"],
    maxPrimers: 1,
    evolveproCsvPath: "/tmp/c.csv",
    evolveproVariantColumn: "variant",
    evolveproScoreColumn: "y_pred",
    evolveproScoreOrder: "desc",
    evolveproSheetName: "",
    strictSpatialEnabled: true,
    structuralDiversityEnabled: true,
    evolveproMode: "pipeline",
    mutationInputMode: "evolvepro",
    strictSpatialBudgetMode: "unique_sites",
    strictSpatialSiteCap: null,
  };
  setStore(base);
  const result = {
    selected_variants: ["A2V"],
    selected_positions: [2],
    mapping: [{ reference_position: 2, structure_position: 2, coordinate: [0, 0, 0], confidence: 90 }],
    pdb_text: "ATOM      1  CA  ALA A   2       0.000   0.000   0.000  1.00 90.00           C\n",
    source_accession: accession,
    budget_mode: "unique_sites",
    site_cap: null,
    score_available: true,
    requested_count: 1,
    selected_site_count: 1,
    eligible_site_count: 1,
  };
  setStore({
    ...base,
    strictSpatialSelection: { result, contextKey: strictSpatialContextKey(storeRef.current as unknown as AppState) },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockBrowseFile.mockResolvedValue();
  setStore();
});

describe("Selection3DPanel: strict mode active-site lookup", () => {
  it("looks up active sites for an AlphaFold accession", async () => {
    setStrictStore("P12345");
    render(<Selection3DPanel defaultOpen />);
    await waitFor(() => expect(storeRef.current.fetchActiveSite).toHaveBeenCalledWith("P12345"));
  });

  it("does not send an ESMFold key to the UniProt lookup", async () => {
    setStrictStore("ESMFOLD:ABC123");
    render(<Selection3DPanel defaultOpen />);
    // The viewer is rendered right before the lookup would run.
    await waitFor(() => {
      const viewer = vi.mocked(createViewer).mock.results[0]?.value as { render: ReturnType<typeof vi.fn> } | undefined;
      expect(viewer?.render).toHaveBeenCalled();
    });
    expect(storeRef.current.fetchActiveSite).not.toHaveBeenCalled();
  });
});

describe("Selection3DPanel: accession structure does not cover the reference", () => {
  it("retries a stale adoption for the same frame and shows the resulting refusal", async () => {
    const adopt = vi.fn<(sequence: string) => Promise<Outcome>>()
      .mockResolvedValueOnce("stale")
      .mockResolvedValueOnce("refused");
    setStore({ structure3dState: "frame_mismatch", adoptReferenceEsmfold: adopt });
    render(<Selection3DPanel />);

    await waitFor(() => expect(screen.getByTestId("frame-needs-file")).toBeInTheDocument());
    expect(adopt).toHaveBeenCalledTimes(2);
    expect(adopt).toHaveBeenNthCalledWith(2, "M" + "A".repeat(99));
  });

  it("predicts the reference with ESMFold when the frame mismatches and consent is given", async () => {
    setStore({ structure3dState: "frame_mismatch" });
    render(<Selection3DPanel />);
    await waitFor(() => expect(storeRef.current.adoptReferenceEsmfold).toHaveBeenCalledTimes(1));
    expect(storeRef.current.adoptReferenceEsmfold).toHaveBeenCalledWith("M" + "A".repeat(99));
    expect(screen.queryByTestId("frame-needs-file")).toBeNull();
  });

  it("says 3D needs consent or a structure file and offers the picker when consent is refused", async () => {
    setStore({
      structure3dState: "frame_mismatch",
      adoptReferenceEsmfold: vi.fn<(sequence: string) => Promise<Outcome>>().mockResolvedValue("refused"),
    });
    render(<Selection3DPanel />);
    await waitFor(() => expect(screen.getByTestId("frame-needs-file")).toBeInTheDocument());
    expect(screen.getByTestId("frame-needs-file").textContent).toContain("frameNeedsConsentOrFile");
    expect(storeRef.current.adoptReferenceEsmfold).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("frame-load-structure-file"));
    expect(mockBrowseFile).toHaveBeenCalledTimes(1);
    const onPick = mockBrowseFile.mock.calls[0]?.[1];
    onPick?.("/tmp/server.zip");
    expect(storeRef.current.loadStructureFile).toHaveBeenCalledWith("/tmp/server.zip");
  });

  it("points a sequence over 400 residues at AlphaFold Server without calling ESMFold", () => {
    setStore({ structure3dState: "frame_mismatch", seqInfo: seqInfo(450) });
    render(<Selection3DPanel />);
    expect(screen.getByTestId("frame-alphafold-server")).toBeInTheDocument();
    expect(screen.getByTestId("frame-load-structure-file")).toBeInTheDocument();
    expect(storeRef.current.adoptReferenceEsmfold).not.toHaveBeenCalled();
  });

  it("uses a terminally truncated exact overlap as is and reports its coverage", () => {
    setStore({ structure3dState: "active", structureCoverage: { covered: 90, reference_length: 100 } });
    render(<Selection3DPanel />);
    expect(screen.getByTestId("frame-coverage")).toBeInTheDocument();
    expect(storeRef.current.adoptReferenceEsmfold).not.toHaveBeenCalled();
    expect(screen.queryByTestId("frame-needs-file")).toBeNull();
    expect(screen.queryByTestId("frame-alphafold-server")).toBeNull();
  });

  it("does not claim an ESMFold prediction is in use when its coordinates are gone, and predicts again", async () => {
    setStore({ structureAccession: "ESMFOLD:ABC123", structure3dState: "no_structure" });
    render(<Selection3DPanel defaultOpen />);
    expect(screen.queryByTestId("esmfold-reference-note")).toBeNull();
    await waitFor(() => expect(storeRef.current.adoptReferenceEsmfold).toHaveBeenCalledTimes(1));
  });

  it("predicts again when strict mode lost the ESMFold prediction", async () => {
    setStore({ structureAccession: "ESMFOLD:ABC123", structure3dState: "frame_mismatch" });
    render(<Selection3DPanel defaultOpen />);
    await waitFor(() => expect(storeRef.current.adoptReferenceEsmfold).toHaveBeenCalledTimes(1));
  });

  it("names the ESMFold prediction of the reference once it replaces the database model", () => {
    setStore({ structureAccession: "ESMFOLD:ABC123", structure3dState: "active" });
    render(<Selection3DPanel defaultOpen />);
    expect(screen.getByTestId("esmfold-reference-note")).toBeInTheDocument();
    expect(storeRef.current.fetchPdbText).not.toHaveBeenCalled();
    expect(storeRef.current.adoptReferenceEsmfold).not.toHaveBeenCalled();
  });
});
