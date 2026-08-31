import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { MamePackageResult } from "@/types/mame/barcode_package";
import { validateGenerateBarcodePackage } from "@/store/validation";
import { BarcodeSetupPanel } from "./BarcodeSetupPanel";

const mockRpc = vi.hoisted(() => vi.fn());
const mockRegisterArtifacts = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-fs", () => ({
  readTextFile: vi.fn(() => Promise.resolve(">cds\nATGAAATAG\n")),
}));
vi.mock("@/lib/ipc", () => ({
  rawSidecarRpc: mockRpc,
}));
vi.mock("@/lib/openFolder", () => ({
  revealInOSFolder: vi.fn(),
}));
vi.mock("@/lib/overwriteConfirm", () => ({
  fileExists: vi.fn(() => Promise.resolve(false)),
  requestOverwriteConfirm: vi.fn(),
}));
vi.mock("@/lib/workspace", () => ({
  registerArtifacts: mockRegisterArtifacts,
}));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

const STORAGE_KEY = "kuma:mame:barcodeSetup";

const elementProto = Element.prototype as unknown as Record<string, unknown>;
const savedElementMethods: Record<string, unknown> = {};

function installSelectShims() {
  for (const name of ["hasPointerCapture", "setPointerCapture", "releasePointerCapture", "scrollIntoView"]) {
    savedElementMethods[name] = elementProto[name];
    elementProto[name] = function () {};
  }
}

function removeSelectShims() {
  for (const [name, value] of Object.entries(savedElementMethods)) {
    if (value === undefined) delete elementProto[name];
    else elementProto[name] = value;
  }
}

beforeEach(installSelectShims);
afterEach(removeSelectShims);

const RESULT: MamePackageResult = {
  barcodes_xlsx: "/proj/design/custom_barcodes.xlsx",
  amplicon_fa: "/proj/design/amplicon.fa",
  context_json: "/proj/design/mame_context.json",
  amplicon_length: 534,
  warnings: [],
};

function seedSetupForm(): void {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      fastaPath: "/proj/input/cds.fa",
      geneStart: "0",
      geneEnd: "534",
      geneName: "target_gene",
      polymerase: "Q5",
      flankMin: "100",
      flankMax: "400",
      bindingMinLen: "18",
      bindingMaxLen: "35",
      tmMin: "55.0",
      tmMax: "68.0",
      requireGcClamp: true,
      barcodeSeedsPath: "/proj/input/barcode_seeds.xlsx",
      outputDir: "",
    }),
  );
}

describe("BarcodeSetupPanel project artifacts", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    useMameAppStore.getState().resetInput();
    mockRpc.mockImplementation((_app: string, method: string) => {
      if (method === "load_fasta") {
        return Promise.resolve({ header: "cds", seq_length: 900, genes: [] });
      }
      return Promise.resolve(RESULT);
    });
    mockRegisterArtifacts.mockResolvedValue(undefined);
  });

  it("generates into the project design folder and registers all setup outputs", async () => {
    seedSetupForm();

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BarcodeSetupPanel group="design" />
      </ProjectProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Generate Barcode Package" }));

    await waitFor(() => {
      expect(mockRpc).toHaveBeenCalledWith(
        "mame",
        "generate_mame_package",
        expect.objectContaining({
          output_dir: "/proj/design",
          project_root: "/proj",
          gene_name: "target_gene",
          topology: "linear",
        }),
        // sendRequest states the timeout the raw transport left implicit. Both
        // resolve to the same 60s: an omitted timeout made the Rust host fall
        // back to RPC_TIMEOUT (src-tauri/src/sidecar.rs:25,394).
        60_000,
      );
    });
    expect(mockRpc).toHaveBeenCalledWith(
      "mame",
      "generate_mame_package",
      expect.objectContaining({
        output_dir: "/proj/design",
        project_root: "/proj",
      }),
      60_000,
    );
    await waitFor(() => {
      expect(mockRegisterArtifacts).toHaveBeenCalledWith([
        {
          app: "mame",
          step: "setup",
          type: "mame_barcodes_xlsx",
          absolutePath: RESULT.barcodes_xlsx,
        },
        {
          app: "mame",
          step: "setup",
          type: "mame_reference_fasta",
          absolutePath: RESULT.amplicon_fa,
        },
        {
          app: "mame",
          step: "setup",
          type: "mame_context_json",
          absolutePath: RESULT.context_json,
        },
      ]);
    });
    expect(useMameAppStore.getState().referencePath).toBe(RESULT.amplicon_fa);
    expect(useMameAppStore.getState().rawRunParams.customBarcodesPath).toBe(
      RESULT.barcodes_xlsx,
    );
  });
});
// ─── Unit: validateGenerateBarcodePackage geneName guard ─────────────────────

describe("validateGenerateBarcodePackage – geneName", () => {
  const base = {
    fastaPath: "/input.fa",
    barcodeSeedsPath: "/seeds.xlsx",
    geneStart: "0",
    geneEnd: "720",
    isRangeValid: true,
    projectPath: "/proj",
  };

  it("fails when geneName is empty", () => {
    const result = validateGenerateBarcodePackage({ ...base, geneName: "" });
    expect(result.ok).toBe(false);
    expect(result.missing).toContain("mame.barcodeSetup.geneName");
  });

  it("fails when geneName is whitespace-only", () => {
    const result = validateGenerateBarcodePackage({ ...base, geneName: "   " });
    expect(result.ok).toBe(false);
    expect(result.missing).toContain("mame.barcodeSetup.geneName");
  });

  it("passes when geneName is non-blank", () => {
    const result = validateGenerateBarcodePackage({ ...base, geneName: "target_gene" });
    expect(result.ok).toBe(true);
    expect(result.missing).not.toContain("mame.barcodeSetup.geneName");
  });
});

// ─── Component: annotation autofill and geneName blocking ────────────────────

describe("BarcodeSetupPanel annotation autofill", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    useMameAppStore.getState().resetInput();
    mockRegisterArtifacts.mockResolvedValue(undefined);
  });

  it("auto-fills geneName from the best annotated CDS gene field", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        fastaPath: "/proj/input/cds.gb",
        geneStart: "",
        geneEnd: "",
        geneName: "",
        polymerase: "Q5",
        flankMin: "100",
        flankMax: "400",
        bindingMinLen: "18",
        bindingMaxLen: "35",
        tmMin: "55.0",
        tmMax: "68.0",
        requireGcClamp: true,
        barcodeSeedsPath: "/proj/input/barcode_seeds.xlsx",
        outputDir: "",
      }),
    );
    mockRpc.mockImplementation((_app: string, method: string) => {
      if (method === "load_fasta") {
        return Promise.resolve({
          header: "cds",
          seq_length: 900,
          genes: [
            {
              gene: "target_a",
              product: "target protein A",
              cds_start: 0,
              cds_end: 720,
              aa_length: 239,
            },
          ],
        });
      }
      return Promise.resolve(RESULT);
    });

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BarcodeSetupPanel />
      </ProjectProvider>,
    );

    await waitFor(() => {
      const input = screen.getByLabelText("Gene name") as HTMLInputElement;
      expect(input.value).toBe("target_a");
    });
  });

  it("updates geneName when user switches annotated CDS selection", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        fastaPath: "/proj/input/cds.gb",
        geneStart: "",
        geneEnd: "",
        geneName: "",
        polymerase: "Q5",
        flankMin: "100",
        flankMax: "400",
        bindingMinLen: "18",
        bindingMaxLen: "35",
        tmMin: "55.0",
        tmMax: "68.0",
        requireGcClamp: true,
        barcodeSeedsPath: "/proj/input/barcode_seeds.xlsx",
        outputDir: "",
      }),
    );
    mockRpc.mockImplementation((_app: string, method: string) => {
      if (method === "load_fasta") {
        return Promise.resolve({
          header: "cds",
          seq_length: 1800,
          genes: [
            {
              gene: "target_a",
              product: "target protein A",
              cds_start: 0,
              cds_end: 720,
              aa_length: 239,
            },
            {
              gene: "target_b",
              product: "target protein B",
              cds_start: 900,
              cds_end: 1620,
              aa_length: 239,
            },
          ],
        });
      }
      return Promise.resolve(RESULT);
    });

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BarcodeSetupPanel />
      </ProjectProvider>,
    );

    // Wait for autofill from the first candidate.
    await waitFor(() => {
      const input = screen.getByLabelText("Gene name") as HTMLInputElement;
      expect(input.value).toBe("target_a");
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: /CDS \/ ORF candidate/i }));
    await user.click(await screen.findByRole("option", { name: /target_b/i }));

    await waitFor(() => {
      const input = screen.getByLabelText("Gene name") as HTMLInputElement;
      expect(input.value).toBe("target_b");
    });
  });

  it("blocks generation and shows warning when geneName is blank", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        fastaPath: "/proj/input/cds.fa",
        geneStart: "0",
        geneEnd: "720",
        geneName: "",
        polymerase: "Q5",
        flankMin: "100",
        flankMax: "400",
        bindingMinLen: "18",
        bindingMaxLen: "35",
        tmMin: "55.0",
        tmMax: "68.0",
        requireGcClamp: true,
        barcodeSeedsPath: "/proj/input/barcode_seeds.xlsx",
        outputDir: "",
      }),
    );
    // load_fasta is not called for .fa, readTextFile is mocked globally
    mockRpc.mockResolvedValue(RESULT);

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BarcodeSetupPanel />
      </ProjectProvider>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Generate Barcode Package" }),
    );

    await waitFor(() => {
      expect(toast.warning).toHaveBeenCalled();
    });
    // RPC must not have been called with generate_mame_package
    const rpgCalls = (mockRpc as ReturnType<typeof vi.fn>).mock.calls.filter(
      (c: unknown[]) => c[1] === "generate_mame_package",
    );
    expect(rpgCalls).toHaveLength(0);
  });

  it("leaves geneName unchanged for plain FASTA ORF candidates", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        fastaPath: "/proj/input/cds.fa",
        geneStart: "",
        geneEnd: "",
        geneName: "my_custom_gene",
        polymerase: "Q5",
        flankMin: "100",
        flankMax: "400",
        bindingMinLen: "18",
        bindingMaxLen: "35",
        tmMin: "55.0",
        tmMax: "68.0",
        requireGcClamp: true,
        barcodeSeedsPath: "/proj/input/barcode_seeds.xlsx",
        outputDir: "",
      }),
    );
    // Override readTextFile to return a valid FASTA with a long-enough ORF
    // (≥ 30 aa after stop exclusion = ≥ 33 codons = 99 nt minimum).
    // The global mock default (9 nt) produces 0 candidates (too short), so we
    // supply a synthetic ORF that exceeds MIN_AA_LENGTH to confirm the effect ran.
    const orf = "ATG" + "AAA".repeat(32) + "TAA"; // 1 + 32 Lys + stop = 33 codons, 30 aa
    vi.mocked(readTextFile).mockResolvedValueOnce(`>cds\n${orf}\n`);
    mockRpc.mockResolvedValue(RESULT);

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BarcodeSetupPanel />
      </ProjectProvider>,
    );

    // After effect fires (ORFs detected), geneName should still be user value
    await waitFor(() => {
      expect(useMameAppStore.getState().cdsCandidates.length).toBeGreaterThan(0);
    });

    const input = screen.getByLabelText("Gene name") as HTMLInputElement;
    expect(input.value).toBe("my_custom_gene");
  });
});

// ─── Output-location notice after Load Sample Data ────────────────────────
//
// outputDir is a save destination the operator chooses; loadSampleData's
// samplePrefill only carries fastaPath + barcodeSeedsPath (analysisSlice.ts
// mameSamplePrefill), so this field stays empty after Load Sample Data the
// same way step 2's export-destination field does. Without an explanation it
// reads exactly like an unfinished pick.
describe("BarcodeSetupPanel sample-data output-location notice", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    useMameAppStore.getState().resetInput();
    mockRegisterArtifacts.mockResolvedValue(undefined);
  });

  it("shows the ordinary 'No path selected' text before any sample data is loaded", () => {
    seedSetupForm();

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BarcodeSetupPanel group="design" />
      </ProjectProvider>,
    );

    expect(screen.getByText("No path selected")).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Sample data does not choose a save location, pick where to write your own output.",
      ),
    ).not.toBeInTheDocument();
  });

  it("swaps in the destination explanation once sampleDataLoaded is true and outputDir is still empty", () => {
    seedSetupForm();
    useMameAppStore.setState({ sampleDataLoaded: true });

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BarcodeSetupPanel group="design" />
      </ProjectProvider>,
    );

    expect(
      screen.getByText(
        "Sample data does not choose a save location, pick where to write your own output.",
      ),
    ).toBeInTheDocument();
  });

  it("does not override the label once the operator has actually chosen an output directory", () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        fastaPath: "/proj/input/cds.fa",
        geneStart: "0",
        geneEnd: "534",
        geneName: "target_gene",
        polymerase: "Q5",
        flankMin: "100",
        flankMax: "400",
        bindingMinLen: "18",
        bindingMaxLen: "35",
        tmMin: "55.0",
        tmMax: "68.0",
        requireGcClamp: true,
        barcodeSeedsPath: "/proj/input/barcode_seeds.xlsx",
        outputDir: "/proj/chosen_output",
      }),
    );
    useMameAppStore.setState({ sampleDataLoaded: true });

    render(
      <ProjectProvider value={{ path: "/proj", name: "Demo", scratch: false }}>
        <BarcodeSetupPanel group="design" />
      </ProjectProvider>,
    );

    expect(
      screen.queryByText(
        "Sample data does not choose a save location, pick where to write your own output.",
      ),
    ).not.toBeInTheDocument();
  });
});
