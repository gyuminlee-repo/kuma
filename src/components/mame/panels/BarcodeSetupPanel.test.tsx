import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { MamePackageResult } from "@/types/mame/barcode_package";
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
  rpc: mockRpc,
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

const RESULT: MamePackageResult = {
  barcodes_xlsx: "/proj/design/custom_barcodes.xlsx",
  amplicon_fa: "/proj/design/amplicon.fa",
  sample_map_template: "/proj/design/sample_map_template.xlsx",
  context_json: "/proj/design/mame_context.json",
  amplicon_length: 534,
  sample_map_prefilled_rows: 1,
  sample_map_preserved: false,
  warnings: [],
};

function seedSetupForm(): void {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      fastaPath: "/proj/input/cds.fa",
      geneStart: "0",
      geneEnd: "534",
      geneName: "egfp",
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
        return Promise.resolve({ seq_length: 900, genes: [] });
      }
      return Promise.resolve(RESULT);
    });
    mockRegisterArtifacts.mockResolvedValue(undefined);
  });

  it("generates into the project design folder and registers all setup outputs", async () => {
    seedSetupForm();
    useMameAppStore.getState().setExpectedPath("/proj/design/kuro_sdm_primers.xlsx");

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
          expected_mutations_path: "/proj/design/kuro_sdm_primers.xlsx",
        }),
      );
    });
    expect(mockRpc).toHaveBeenCalledWith(
      "mame",
      "generate_mame_package",
      expect.objectContaining({
        output_dir: "/proj/design",
        project_root: "/proj",
        expected_mutations_path: "/proj/design/kuro_sdm_primers.xlsx",
      }),
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
          type: "mame_sample_map_xlsx",
          absolutePath: RESULT.sample_map_template,
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
    expect(useMameAppStore.getState().sampleMapPath).toBe(RESULT.sample_map_template);
    expect(useMameAppStore.getState().rawRunParams.customBarcodesPath).toBe(
      RESULT.barcodes_xlsx,
    );
  });
});
