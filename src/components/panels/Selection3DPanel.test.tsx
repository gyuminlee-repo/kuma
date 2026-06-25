/**
 * Selection3DPanel — vitest/jsdom unit tests.
 * Mocks: 3dmol, @/store/appStore
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ComputeDispersionResult, FetchActiveSiteResult, FetchPdbTextResult } from "@/types/models";

// ─── mock 3dmol ─────────────────────────────────────────────────────────────
// Must be declared before vi.mock since vi.mock hoists factories
const mockViewer = {
  addModel: vi.fn(),
  setStyle: vi.fn(),
  addStyle: vi.fn(),
  setHoverable: vi.fn(),
  addSurface: vi.fn().mockResolvedValue(1),
  removeSurface: vi.fn(),
  render: vi.fn(),
  spin: vi.fn(),
  zoomTo: vi.fn(),
  pngURI: vi.fn(() => "data:image/png;base64,abc"),
  removeAllModels: vi.fn(),
  removeAllSurfaces: vi.fn(),
  removeAllLabels: vi.fn(),
  addLabel: vi.fn(),
  clear: vi.fn(),
  getCanvas: vi.fn(),
};
const mockCreateViewer = vi.fn(() => mockViewer);

vi.mock("3dmol", () => ({
  createViewer: mockCreateViewer,
  SurfaceType: { VDW: 1, MS: 2, SAS: 3, SES: 4 },
}));

// ─── mock i18n ───────────────────────────────────────────────────────────────
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (key === "selection3d.droppedWarning" && opts) {
        return `${opts["count"]} position(s) could not be mapped: ${opts["positions"]}`;
      }
      if (key === "selection3d.lengthMismatch") return "Sequence length mismatch";
      return key.split(".").pop() ?? key;
    },
  }),
}));

// ─── store mock ───────────────────────────────────────────────────────────────
// State is a mutable object mutated by __setStoreState helper.
// Factory cannot reference outer variables, so state is defined inline.
const storeRef: {
  current: {
    structureAccession: string;
    uniprotAccession: string;
    seqInfo: null | {
      header: string;
      seq_length: number;
      genes: Array<{
        gene: string;
        product: string;
        cds_start: number;
        cds_end: number;
        aa_length: number;
        translation?: string;
      }>;
    };
    selectedGene: string;
    evolveproSelectedVariants: string[];
    evolveproRankedCandidates: Array<{ variant: string; y_pred: number; aa_position?: number | null }>;
    yPredMap: Record<string, number>;
    domains: Array<{ name: string; id: string; start: number; end: number; db: string }>;
    fetchPdbText: ReturnType<typeof vi.fn>;
    fetchActiveSite: ReturnType<typeof vi.fn>;
    computeDispersion: ReturnType<typeof vi.fn>;
  };
} = {
  current: {
    structureAccession: "",
    uniprotAccession: "",
    seqInfo: null,
    selectedGene: "",
    evolveproSelectedVariants: [],
    evolveproRankedCandidates: [],
    yPredMap: {},
    domains: [],
    fetchPdbText: vi.fn().mockResolvedValue(null),
    fetchActiveSite: vi.fn().mockResolvedValue(null),
    computeDispersion: vi.fn().mockResolvedValue(null),
  },
};

vi.mock("@/store/appStore", () => ({
  useAppStore: (selector: (s: (typeof storeRef)["current"]) => unknown) =>
    selector(storeRef.current),
}));

// ─── mock ipc ───────────────────────────────────────────────────────────────
vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
}));

// Import AFTER all vi.mock calls
import { Selection3DPanel } from "./Selection3DPanel";

// ─── fixtures ────────────────────────────────────────────────────────────────
const STUB_PDB_TEXT =
  "ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00 90.00           C  \nEND\n";

const SUCCESS_PDB: FetchPdbTextResult = {
  success: true,
  accession: "P12345",
  pdb_text: STUB_PDB_TEXT,
  source: "alphafold",
};

const NULL_PDB: FetchPdbTextResult = {
  success: false,
  accession: "P12345",
  pdb_text: null,
  source: "not_found",
};

const ACTIVE_SITE: FetchActiveSiteResult = {
  accession: "P12345",
  active_site_positions: [42, 50],
  binding_positions: [100, 101],
  source: "uniprot",
  has_annotation: true,
};

const ACTIVE_SITE_EMPTY: FetchActiveSiteResult = {
  accession: "P12345",
  active_site_positions: [],
  binding_positions: [],
  source: "uniprot",
  has_annotation: false,
};

const DISPERSION: ComputeDispersionResult = {
  accession: "P12345",
  mapped: [1],
  dropped: [],
  n_positions: 1,
  mean_pairwise: 12.5,
  null_mean: 10.0,
  null_p05: 5.0,
  null_p95: 18.0,
  percentile: 0.72,
  klass: "spread",
  n_trials: 1000,
  seed: 0,
};

const DISPERSION_DROPPED: ComputeDispersionResult = {
  ...DISPERSION,
  mapped: [],
  dropped: [99, 100],
  n_positions: 0,
};

function makeSeqInfo() {
  return {
    header: ">test",
    seq_length: 100,
    genes: [
      {
        gene: "TEST",
        product: "test protein",
        cds_start: 1,
        cds_end: 300,
        aa_length: 100,
        translation: "M" + "A".repeat(99),
      },
    ],
  };
}

function resetStore() {
  storeRef.current = {
    structureAccession: "",
    uniprotAccession: "",
    seqInfo: null,
    selectedGene: "",
    evolveproSelectedVariants: [],
    evolveproRankedCandidates: [],
    yPredMap: {},
    domains: [],
    fetchPdbText: vi.fn().mockResolvedValue(null),
    fetchActiveSite: vi.fn().mockResolvedValue(null),
    computeDispersion: vi.fn().mockResolvedValue(null),
  };
}

function setStore(patch: Partial<(typeof storeRef)["current"]>) {
  storeRef.current = { ...storeRef.current, ...patch };
}

// ─── test suites ─────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  resetStore();
});

describe("Selection3DPanel — disabled state (no accession)", () => {
  it("renders a disabled toggle button", () => {
    render(<Selection3DPanel />);
    expect(screen.getByTestId("panel-toggle")).toBeDisabled();
  });

  it("shows the noAccession message below the toggle", () => {
    render(<Selection3DPanel />);
    const msg = screen.getByTestId("disabled-message");
    expect(msg).toBeInTheDocument();
    expect(msg.textContent).toContain("noAccession");
  });

  it("does not render panel-body", () => {
    render(<Selection3DPanel />);
    expect(screen.queryByTestId("panel-body")).toBeNull();
  });

  it("does not call fetchPdbText", () => {
    const fetchPdbText = vi.fn();
    setStore({ fetchPdbText });
    render(<Selection3DPanel />);
    expect(fetchPdbText).not.toHaveBeenCalled();
  });
});

describe("Selection3DPanel — empty/error state (pdb_text null)", () => {
  beforeEach(() => {
    setStore({
      uniprotAccession: "P12345",
      fetchPdbText: vi.fn().mockResolvedValue(NULL_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE_EMPTY),
      computeDispersion: vi.fn().mockResolvedValue(null),
    });
  });

  it("shows error-state element after fetch returns no structure", async () => {
    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(screen.getByTestId("error-state")).toBeInTheDocument());
  });

  it("shows error-state when fetchPdbText returns null", async () => {
    setStore({ fetchPdbText: vi.fn().mockResolvedValue(null) });
    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(screen.getByTestId("error-state")).toBeInTheDocument());
  });
});

describe("Selection3DPanel — opens and fetches on click", () => {
  function setupFull() {
    setStore({
      uniprotAccession: "P12345",
      evolveproSelectedVariants: ["A1G"],
      evolveproRankedCandidates: [{ variant: "A1G", y_pred: 0.85, aa_position: 1 }],
      yPredMap: { A1G: 0.85 },
      seqInfo: makeSeqInfo(),
      fetchPdbText: vi.fn().mockResolvedValue(SUCCESS_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE),
      computeDispersion: vi.fn().mockResolvedValue(DISPERSION),
    });
  }

  it("toggle is enabled when accession present", () => {
    setupFull();
    render(<Selection3DPanel />);
    expect(screen.getByTestId("panel-toggle")).not.toBeDisabled();
  });

  it("calls fetchPdbText and computeDispersion on open", async () => {
    const fetchPdbText = vi.fn().mockResolvedValue(SUCCESS_PDB);
    const computeDispersion = vi.fn().mockResolvedValue(DISPERSION);
    setStore({ uniprotAccession: "P12345", seqInfo: makeSeqInfo(), fetchPdbText, computeDispersion, fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE), evolveproSelectedVariants: ["A1G"], evolveproRankedCandidates: [{ variant: "A1G", y_pred: 0.85, aa_position: 1 }], yPredMap: { A1G: 0.85 } });
    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => {
      expect(fetchPdbText).toHaveBeenCalledWith("P12345");
      expect(computeDispersion).toHaveBeenCalled();
    });
  });

  it("calls createViewer and addModel when PDB loads successfully", async () => {
    setupFull();
    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => {
      expect(mockCreateViewer).toHaveBeenCalled();
      expect(mockViewer.addModel).toHaveBeenCalledWith(STUB_PDB_TEXT, "pdb");
    });
  });

  it("renders viewer-container immediately on open", () => {
    setupFull();
    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    expect(screen.getByTestId("viewer-container")).toBeInTheDocument();
  });

  it("shows dispersion card after loading", async () => {
    setupFull();
    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(screen.getByTestId("dispersion-card")).toBeInTheDocument());
  });
});

describe("Selection3DPanel — variant spheres use joinMappedYpred mapped positions", () => {
  it("calls addStyle with accPosition=5 when mapped=[5]", async () => {
    const dispersion: ComputeDispersionResult = {
      ...DISPERSION,
      mapped: [5],
      dropped: [],
    };
    setStore({
      uniprotAccession: "P12345",
      evolveproSelectedVariants: ["A1G"],
      evolveproRankedCandidates: [{ variant: "A1G", y_pred: 0.85, aa_position: 1 }],
      yPredMap: { A1G: 0.85 },
      seqInfo: makeSeqInfo(),
      fetchPdbText: vi.fn().mockResolvedValue(SUCCESS_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE_EMPTY),
      computeDispersion: vi.fn().mockResolvedValue(dispersion),
    });

    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));

    await waitFor(() => {
      const sphereCalls = mockViewer.addStyle.mock.calls.filter(
        (c) => (c[1] as { sphere?: unknown }).sphere !== undefined,
      );
      expect(sphereCalls.length).toBeGreaterThan(0);
      // accPosition=5 from mapped[0]
      expect(sphereCalls[0][0]).toEqual({ resi: 5 });
    });
  });
});

describe("Selection3DPanel — pLDDT mode hidden when upload source", () => {
  async function openAndLoad() {
    setStore({
      uniprotAccession: "P12345",
      evolveproSelectedVariants: ["A1G"],
      evolveproRankedCandidates: [{ variant: "A1G", y_pred: 0.85, aa_position: 1 }],
      yPredMap: { A1G: 0.85 },
      seqInfo: makeSeqInfo(),
      fetchPdbText: vi.fn().mockResolvedValue(SUCCESS_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE),
      computeDispersion: vi.fn().mockResolvedValue(DISPERSION),
    });
    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(screen.getByTestId("viewer-toolbar")).toBeInTheDocument());
  }

  it("shows pLDDT button for non-upload structure", async () => {
    await openAndLoad();
    // pLDDT toolbar button should be present
    const toolbar = screen.getByTestId("viewer-toolbar");
    // mock t() returns key suffix: "colorPlddt" for "selection3d.colorPlddt"
    expect(toolbar.textContent).toContain("colorPlddt");

  });

  it("hides pLDDT button after uploading a PDB file", async () => {
    await openAndLoad();
    const pdbContent = "ATOM      1  CA  ALA A   1       1.000   2.000   3.000  1.00 90.00           C  \nEND\n";
    // jsdom File doesn't have .text(); add it manually
    const file = Object.assign(new File([pdbContent], "custom.pdb", { type: "chemical/x-pdb" }), {
      text: () => Promise.resolve(pdbContent),
    });
    const input = screen.getByTestId("upload-input") as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [file], writable: false });
    fireEvent.change(input);


    await waitFor(() =>
      expect(screen.getByTestId("upload-source-note")).toBeInTheDocument(),
    );

    // pLDDT should no longer appear in toolbar
    const toolbar = screen.getByTestId("viewer-toolbar");
    // mock t() returns key suffix: "colorPlddt" for "selection3d.colorPlddt"
    expect(toolbar.textContent).not.toContain("colorPlddt");
  });
});

describe("Selection3DPanel — dropped positions warning", () => {
  it("shows warning with dropped positions listed", async () => {
    setStore({
      uniprotAccession: "P12345",
      evolveproSelectedVariants: ["A99G", "A100G"],
      evolveproRankedCandidates: [
        { variant: "A99G", y_pred: 0.7, aa_position: 99 },
        { variant: "A100G", y_pred: 0.6, aa_position: 100 },
      ],
      yPredMap: { A99G: 0.7, A100G: 0.6 },
      seqInfo: makeSeqInfo(),
      fetchPdbText: vi.fn().mockResolvedValue(SUCCESS_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE_EMPTY),
      computeDispersion: vi.fn().mockResolvedValue(DISPERSION_DROPPED),
    });

    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));

    await waitFor(() =>
      expect(screen.getByTestId("dropped-warning")).toBeInTheDocument(),
    );

    const warning = screen.getByTestId("dropped-warning");
    expect(warning.textContent).toContain("99");
    expect(warning.textContent).toContain("100");
  });
});

describe("Selection3DPanel — position table row click focuses residue", () => {
  it("calls viewer.zoomTo with accPosition when row is clicked", async () => {
    const dispersion: ComputeDispersionResult = {
      ...DISPERSION,
      mapped: [7],
      dropped: [],
    };
    setStore({
      uniprotAccession: "P12345",
      evolveproSelectedVariants: ["A1G"],
      evolveproRankedCandidates: [{ variant: "A1G", y_pred: 0.85, aa_position: 1 }],
      yPredMap: { A1G: 0.85 },
      seqInfo: {
        header: ">test",
        seq_length: 5,
        genes: [
          { gene: "T", product: "t", cds_start: 1, cds_end: 15, aa_length: 5, translation: "MAAAA" },
        ],
      },
      fetchPdbText: vi.fn().mockResolvedValue(SUCCESS_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE_EMPTY),
      computeDispersion: vi.fn().mockResolvedValue(dispersion),
    });

    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));

    await waitFor(() =>
      expect(screen.getAllByTestId("position-row").length).toBeGreaterThan(0),
    );

    fireEvent.click(screen.getAllByTestId("position-row")[0]);
    expect(mockViewer.zoomTo).toHaveBeenCalledWith({ resi: 7 }, 500);
  });
});
describe("Selection3DPanel — viewer lifecycle regression", () => {
  function setupFull() {
    setStore({
      uniprotAccession: "P12345",
      evolveproSelectedVariants: ["A1G"],
      evolveproRankedCandidates: [{ variant: "A1G", y_pred: 0.85, aa_position: 1 }],
      yPredMap: { A1G: 0.85 },
      seqInfo: makeSeqInfo(),
      fetchPdbText: vi.fn().mockResolvedValue(SUCCESS_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE_EMPTY),
      computeDispersion: vi.fn().mockResolvedValue(DISPERSION),
    });
  }

  it("open → close → reopen re-calls createViewer + addModel and shows viewer-container", async () => {
    setupFull();
    render(<Selection3DPanel />);

    // First open
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(mockCreateViewer).toHaveBeenCalledTimes(1));
    expect(mockViewer.addModel).toHaveBeenCalledTimes(1);

    // Close — viewer should be cleared
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(mockViewer.clear).toHaveBeenCalled());

    // Reopen — must reinitialise into fresh container
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(mockCreateViewer).toHaveBeenCalledTimes(2));
    expect(mockViewer.addModel).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("viewer-container")).toBeInTheDocument();
  });

  it("uploading PDB over an already-open viewer clears the prior viewer before creating a new one", async () => {
    setupFull();
    render(<Selection3DPanel />);

    // Open and load structure
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(mockCreateViewer).toHaveBeenCalledTimes(1));

    // Upload a PDB file
    const file = Object.assign(new File([STUB_PDB_TEXT], "custom.pdb", { type: "chemical/x-pdb" }), {
      text: () => Promise.resolve(STUB_PDB_TEXT),
    });
    const input = screen.getByTestId("upload-input") as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [file], writable: false });
    fireEvent.change(input);

    // Second createViewer call happens; prior viewer was cleared
    await waitFor(() => expect(mockCreateViewer).toHaveBeenCalledTimes(2));
    expect(mockViewer.clear).toHaveBeenCalled();
  });
});
describe("Selection3DPanel — cleanupViewer disposes WebGL canvas", () => {
  function setupFull() {
    setStore({
      uniprotAccession: "P12345",
      evolveproSelectedVariants: ["A1G"],
      evolveproRankedCandidates: [{ variant: "A1G", y_pred: 0.85, aa_position: 1 }],
      yPredMap: { A1G: 0.85 },
      seqInfo: makeSeqInfo(),
      fetchPdbText: vi.fn().mockResolvedValue(SUCCESS_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE_EMPTY),
      computeDispersion: vi.fn().mockResolvedValue(DISPERSION),
    });
  }

  function makeFakeCanvas() {
    const loseContext = vi.fn();
    const getExtension = vi.fn().mockReturnValue({ loseContext });
    const fakeGl = { getExtension };
    const canvas = document.createElement("canvas");
    vi.spyOn(canvas, "getContext").mockReturnValue(fakeGl as unknown as CanvasRenderingContext2D);
    const removeSpy = vi.spyOn(canvas, "remove");
    return { canvas, loseContext, getExtension, removeSpy };
  }

  it("calls canvas.remove() and loseContext() when panel is closed", async () => {
    setupFull();
    const { canvas, loseContext, getExtension, removeSpy } = makeFakeCanvas();
    mockViewer.getCanvas = vi.fn().mockReturnValue(canvas);

    render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(mockCreateViewer).toHaveBeenCalled());

    // Close → triggers cleanupViewer
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(mockViewer.clear).toHaveBeenCalled());

    expect(mockViewer.getCanvas).toHaveBeenCalled();
    expect(getExtension).toHaveBeenCalledWith("WEBGL_lose_context");
    expect(loseContext).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
  });

  it("calls canvas.remove() and loseContext() on unmount", async () => {
    setupFull();
    const { canvas, loseContext, removeSpy } = makeFakeCanvas();
    mockViewer.getCanvas = vi.fn().mockReturnValue(canvas);

    const { unmount } = render(<Selection3DPanel />);
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(mockCreateViewer).toHaveBeenCalled());

    unmount();

    expect(loseContext).toHaveBeenCalled();
    expect(removeSpy).toHaveBeenCalled();
  });
});

describe("Selection3DPanel — uploadSource resets on fetched-accession reload", () => {
  function setupFull() {
    setStore({
      uniprotAccession: "P12345",
      evolveproSelectedVariants: ["A1G"],
      evolveproRankedCandidates: [{ variant: "A1G", y_pred: 0.85, aa_position: 1 }],
      yPredMap: { A1G: 0.85 },
      seqInfo: makeSeqInfo(),
      fetchPdbText: vi.fn().mockResolvedValue(SUCCESS_PDB),
      fetchActiveSite: vi.fn().mockResolvedValue(ACTIVE_SITE_EMPTY),
      computeDispersion: vi.fn().mockResolvedValue(DISPERSION),
    });
  }

  it("pLDDT button reappears after close+reopen following an upload", async () => {
    setupFull();
    render(<Selection3DPanel />);

    // Open and wait for toolbar (fetched accession, pLDDT visible)
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(screen.getByTestId("viewer-toolbar")).toBeInTheDocument());
    expect(screen.getByTestId("viewer-toolbar").textContent).toContain("colorPlddt");

    // Upload a PDB — sets uploadSource=true, pLDDT disappears
    const file = Object.assign(new File([STUB_PDB_TEXT], "custom.pdb", { type: "chemical/x-pdb" }), {
      text: () => Promise.resolve(STUB_PDB_TEXT),
    });
    const input = screen.getByTestId("upload-input") as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [file], writable: false });
    fireEvent.change(input);
    await waitFor(() => expect(screen.getByTestId("upload-source-note")).toBeInTheDocument());
    expect(screen.getByTestId("viewer-toolbar").textContent).not.toContain("colorPlddt");

    // Close panel
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(screen.queryByTestId("viewer-toolbar")).toBeNull());

    // Reopen — load() runs again, resets uploadSource=false
    fireEvent.click(screen.getByTestId("panel-toggle"));
    await waitFor(() => expect(screen.getByTestId("viewer-toolbar")).toBeInTheDocument());

    // pLDDT button must be back
    expect(screen.getByTestId("viewer-toolbar").textContent).toContain("colorPlddt");
  });
});
