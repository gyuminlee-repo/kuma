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

type Outcome = "used" | "refused" | "failed";
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

import { Selection3DPanel } from "./Selection3DPanel";

function seqInfo(length: number) {
  return {
    header: ">t",
    seq_length: length,
    genes: [{ gene: "T", product: "t", cds_start: 1, cds_end: length * 3, aa_length: length,
      translation: "M" + "A".repeat(length - 1) }],
  };
}

function setStore(patch: Partial<StoreShape> = {}) {
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
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockBrowseFile.mockResolvedValue();
  setStore();
});

describe("Selection3DPanel: accession structure does not cover the reference", () => {
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

  it("names the ESMFold prediction of the reference once it replaces the database model", () => {
    setStore({ structureAccession: "ESMFOLD:ABC123", structure3dState: "active" });
    render(<Selection3DPanel defaultOpen />);
    expect(screen.getByTestId("esmfold-reference-note")).toBeInTheDocument();
    expect(storeRef.current.fetchPdbText).not.toHaveBeenCalled();
    expect(storeRef.current.adoptReferenceEsmfold).not.toHaveBeenCalled();
  });
});
