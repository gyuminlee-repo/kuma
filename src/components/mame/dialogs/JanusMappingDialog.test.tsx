/**
 * JanusMappingDialog: dry-run preview gating.
 *
 * The export writes a file with no way to inspect it first, so the dialog must
 * fetch the preview on open and on every destination-layout change, and it must
 * refuse to export while the preview reports a plate-layout problem. A preview
 * that merely failed to load is a different thing: export keeps its own
 * fail-fast guards, so a broken preview must not brick a working export.
 */

import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/plugin-dialog", () => ({
  save: vi.fn(),
}));
vi.mock("@/lib/overwriteConfirm", () => ({
  fileExists: vi.fn(async () => false),
  requestOverwriteConfirm: vi.fn(async () => "overwrite"),
}));
vi.mock("@/lib/mame/janus", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/mame/janus")>();
  return {
    ...actual,
    fetchMameJanusPreview: vi.fn(),
    handleExportMameJanusMapping: vi.fn(),
  };
});
vi.mock("@/state/projectContext", () => ({
  useKumaProject: () => ({ path: "/tmp/proj", name: "proj" }),
}));
// The dialog reads its Janus policy from the store now (an analyze run writes
// its own mapping with the same settings), so the double has to be a real
// store: a plain selector over a frozen object would never re-render on edit.
vi.mock("@/store/mame/mameAppStore", async () => {
  const { create } = await import("zustand");
  const { DEFAULT_JANUS_SETTINGS } = await import("@/lib/mame/janusSettings");
  const useMameAppStore = create<JanusStoreDouble>()((set) => ({
    isExporting: false,
    janusSettings: DEFAULT_JANUS_SETTINGS,
    setJanusSettings: (janusSettings: JanusExportSettings) => set({ janusSettings }),
  }));
  return { useMameAppStore };
});

import {
  fetchMameJanusPreview,
  handleExportMameJanusMapping,
} from "@/lib/mame/janus";
import { DEFAULT_JANUS_SETTINGS } from "@/lib/mame/janusSettings";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type {
  JanusExcludedEntry,
  JanusExportSettings,
  JanusPreviewResult,
  JanusResolvedSettings,
} from "@/types/mame/models";
import { JanusMappingDialog } from "./JanusMappingDialog";

interface JanusStoreDouble {
  isExporting: boolean;
  janusSettings: JanusExportSettings;
  setJanusSettings: (settings: JanusExportSettings) => void;
}

const mockPreview = vi.mocked(fetchMameJanusPreview);
const mockExport = vi.mocked(handleExportMameJanusMapping);

const SETTINGS: JanusResolvedSettings = {
  dest_layout: "compact",
  include_verdicts: ["PASS"],
  include_fallback: false,
  output_schema: "device9",
  volume: 100,
  sample_type: "cell",
  liquid_class: "Cell 100ul",
  source_racks: { P1: 1, P2: 2, P3: 3 },
  dest_rack: 4,
  columns: [
    "name",
    "type",
    "Dsp. Rack",
    "no",
    "Asp. Rack",
    "Asp. Posi",
    "Dsp. Rack",
    "Dsp. Posi",
    "volume",
  ],
};

const CLEAN: JanusPreviewResult = {
  rows: [
    {
      name: "HIGH",
      source_plate: "P1",
      source_well: "E7",
      dest_well: "E7",
      priority_score: 300,
    },
    {
      name: "LOW",
      source_plate: "P2",
      source_well: "H12",
      dest_well: "H12",
      priority_score: 10,
    },
  ],
  errors: [],
  row_count: 2,
  excluded: [],
  excluded_count: 0,
  settings: SETTINGS,
};

const DUPLICATE: JanusPreviewResult = {
  rows: [
    {
      name: "P1_A1",
      source_plate: "P1",
      source_well: "A1",
      dest_well: "A1",
      priority_score: 200,
    },
    {
      name: "P2_A1",
      source_plate: "P2",
      source_well: "A1",
      dest_well: "A1",
      priority_score: 100,
    },
  ],
  errors: [
    {
      code: "duplicate_dest_well",
      message: "Janus mapping: duplicate dest_well would dispense multiple clones",
      mutant_ids: ["P1_A1", "P2_A1"],
    },
  ],
  row_count: 2,
  excluded: [],
  excluded_count: 0,
  settings: SETTINGS,
};

const EXCLUSIONS: JanusExcludedEntry[] = [
  {
    mutant_id: "AMBIG",
    reason: "verdict_class",
    verdict: "AMBIGUOUS",
    selected_plate: "P1",
    is_fallback: false,
  },
  {
    mutant_id: "LOWDEP",
    reason: "verdict_class",
    verdict: "LOWDEPTH",
    selected_plate: "P1",
    is_fallback: false,
  },
  {
    mutant_id: "FB",
    reason: "fallback",
    verdict: "PASS",
    selected_plate: "P2",
    is_fallback: true,
  },
];

function resolvedSettingsFromUi(
  settings: JanusExportSettings | undefined,
): JanusResolvedSettings {
  if (!settings) return SETTINGS;
  return {
    dest_layout: settings.destLayout,
    include_verdicts: settings.includeVerdicts,
    include_fallback: settings.includeFallback,
    output_schema: settings.outputSchema,
    volume: settings.volume,
    sample_type: settings.sampleType,
    liquid_class: settings.liquidClass,
    source_racks: settings.sourceRacks,
    dest_rack: settings.destRack,
    columns:
      settings.outputSchema === "device9"
        ? [
            "name",
            "type",
            "Dsp. Rack",
            "no",
            "Asp. Rack",
            "Asp. Posi",
            "Dsp. Rack",
            "Dsp. Posi",
            "volume",
          ]
        : ["name", "source_plate", "source_well", "dest_well", "priority_score"],
  };
}

function cleanPreviewFor(settings: JanusExportSettings | undefined): JanusPreviewResult {
  return { ...CLEAN, settings: resolvedSettingsFromUi(settings) };
}

function exportButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: /Export Janus Mapping/i });
}

beforeEach(() => {
  // Settings outlive a render now, so each test starts from the defaults.
  useMameAppStore.setState({ janusSettings: DEFAULT_JANUS_SETTINGS });
  mockPreview.mockReset();
  mockExport.mockReset();
  mockPreview.mockImplementation(async (settings) => cleanPreviewFor(settings));
});

describe("JanusMappingDialog preview", () => {
  it("fetches the preview when the dialog opens", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({ destLayout: "compact", outputSchema: "device9" }),
      ),
    );
    expect(await screen.findByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("2 rows")).toBeInTheDocument();
  });

  it("does not fetch while the dialog is closed", () => {
    render(<JanusMappingDialog open={false} onOpenChange={() => {}} />);
    expect(mockPreview).not.toHaveBeenCalled();
  });

  it("refetches when the destination layout changes", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText("Source position"));
    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({ destLayout: "source" }),
      ),
    );
  });

  it("refetches when the liquid class is typed in", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Liquid class"), {
      target: { value: "Cell 100ul" },
    });
    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({ liquidClass: "Cell 100ul" }),
      ),
    );
  });

  it("ignores fractional rack edits instead of truncating them", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText("Deck configuration"));

    fireEvent.change(screen.getByLabelText("Asp. Rack P1"), {
      target: { value: "1.9" },
    });
    fireEvent.change(screen.getByLabelText("Dsp. Rack"), {
      target: { value: "4.7" },
    });

    await new Promise((resolve) => setTimeout(resolve, 350));
    expect(mockPreview).toHaveBeenCalledTimes(1);
  });

  it("sends the same settings to the export that the preview was built with", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    // Wait for the first (debounced) preview before editing, so the edit is a
    // second request rather than a reset of the pending timer.
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Liquid class"), {
      target: { value: "Cell 100ul" },
    });
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(exportButton()).toBeEnabled());

    fireEvent.click(exportButton());
    await waitFor(() => expect(mockExport).toHaveBeenCalled());
    const previewArg = mockPreview.mock.calls.at(-1)?.[0];
    expect(mockExport.mock.calls[0][2]).toEqual(previewArg);
  });

  it("lists the excluded clones with the reason for each", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      ...CLEAN,
      excluded: EXCLUSIONS,
      excluded_count: EXCLUSIONS.length,
      settings: resolvedSettingsFromUi(settings),
    }));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);

    expect(await screen.findByText("Excluded: 3")).toBeInTheDocument();
    const verdictRow = screen.getByText("Verdict class not included").closest("li");
    expect(verdictRow?.textContent).toContain("AMBIG, LOWDEP");
    const fallbackRow = screen.getByText("Fallback pick").closest("li");
    expect(fallbackRow?.textContent).toContain("FB");
  });

  it("says so when nothing was excluded", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    expect(
      await screen.findByText("Every clone made the pick."),
    ).toBeInTheDocument();
  });

  it("shows the exact rows the export would write", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    const table = await screen.findByRole("table");
    const cells = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) =>
        within(row)
          .getAllByRole("cell")
          .map((c) => c.textContent),
      );
    expect(cells).toEqual([
      ["HIGH", "cell", "", "1", "1", "E7", "4", "E7", "100"],
      ["LOW", "cell", "", "2", "2", "H12", "4", "H12", "100"],
    ]);
    const header = within(table)
      .getAllByRole("columnheader")
      .map((c) => c.textContent);
    expect(header).toEqual([
      "name",
      "type",
      "Dsp. Rack",
      "no",
      "Asp. Rack",
      "Asp. Posi",
      "Dsp. Rack",
      "Dsp. Posi",
      "volume",
    ]);
  });

  it("blocks export while the visible preview is stale for edited settings", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(exportButton()).toBeEnabled());

    fireEvent.change(screen.getByLabelText("Liquid class"), {
      target: { value: "Different class" },
    });

    expect(exportButton()).toBeDisabled();
    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({ liquidClass: "Different class" }),
      ),
    );
  });

  it("blocks the export and shows the problem when validation fails", async () => {
    mockPreview.mockResolvedValue(DUPLICATE);
    render(<JanusMappingDialog open onOpenChange={() => {}} />);

    expect(
      await screen.findByText(/duplicate dest_well would dispense/i),
    ).toBeInTheDocument();
    await waitFor(() => expect(exportButton()).toBeDisabled());

    fireEvent.click(exportButton());
    expect(mockExport).not.toHaveBeenCalled();
  });

  it("re-enables the export once a layout change clears the problem", async () => {
    mockPreview
      .mockResolvedValueOnce(DUPLICATE)
      .mockImplementationOnce(async (settings) => cleanPreviewFor(settings));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    expect(
      await screen.findByText(/duplicate dest_well would dispense/i),
    ).toBeInTheDocument();
    expect(exportButton()).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Source position"));
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(exportButton()).toBeEnabled());
  });

  it("blocks export when the preview itself fails to load", async () => {
    mockPreview.mockRejectedValue(new Error("sidecar unavailable"));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);

    await waitFor(() => expect(mockPreview).toHaveBeenCalled());
    expect(await screen.findByText(/sidecar unavailable/i)).toBeInTheDocument();
    expect(exportButton()).toBeDisabled();
  });

  it("retries a failed preview on demand", async () => {
    mockPreview
      .mockRejectedValueOnce(new Error("sidecar unavailable"))
      .mockImplementationOnce(async (settings) => cleanPreviewFor(settings));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await screen.findByText(/sidecar unavailable/i);

    fireEvent.click(screen.getByRole("button", { name: "Retry preview" }));
    expect(await screen.findByText("HIGH")).toBeInTheDocument();
  });

  it("renders an empty state rather than a table when nothing was picked", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      rows: [],
      errors: [],
      row_count: 0,
      excluded: [],
      excluded_count: 0,
      settings: resolvedSettingsFromUi(settings),
    }));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);

    expect(
      await screen.findByText("No confirmed picks to export."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("ignores a stale response from a superseded layout toggle", async () => {
    let resolveFirst: ((v: JanusPreviewResult) => void) | undefined;
    mockPreview
      .mockImplementationOnce(
        () =>
          new Promise<JanusPreviewResult>((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockImplementationOnce(async (settings) => cleanPreviewFor(settings));

    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByLabelText("Source position"));
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));

    // The first (compact-layout) call now lands late carrying a duplicate error.
    resolveFirst?.(DUPLICATE);
    await waitFor(() => expect(exportButton()).toBeEnabled());
    expect(
      screen.queryByText(/duplicate dest_well would dispense/i),
    ).not.toBeInTheDocument();
  });
});

describe("JanusMappingDialog deck map", () => {
  /**
   * Observed on a real run: the plates were native barcode folders named
   * `sort_barcode07` and up, which a fixed P1/P2/P3 field list has no rack for,
   * so the export refused every clone. The fields must name the plates the run
   * actually produced.
   */
  const NATIVE_BARCODE: JanusPreviewResult = {
    ...CLEAN,
    rows: [
      { ...CLEAN.rows[0], source_plate: "sort_barcode07" },
      { ...CLEAN.rows[1], source_plate: "sort_barcode08" },
    ],
  };

  beforeEach(() => {
    useMameAppStore.setState({ janusSettings: DEFAULT_JANUS_SETTINGS });
    mockPreview.mockReset();
  });

  it("names the rack fields after the plates of the run", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      ...NATIVE_BARCODE,
      settings: resolvedSettingsFromUi(settings),
    }));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());
    fireEvent.click(await screen.findByText("Deck configuration"));

    expect(await screen.findByLabelText("Asp. Rack sort_barcode07")).toBeInTheDocument();
    expect(screen.getByLabelText("Asp. Rack sort_barcode08")).toBeInTheDocument();
    // The shipped P1/P2/P3 names belong to no plate of this run.
    expect(screen.queryByLabelText("Asp. Rack P1")).not.toBeInTheDocument();
  });

  it("records the rack number under the plate name the sidecar checks", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      ...NATIVE_BARCODE,
      settings: resolvedSettingsFromUi(settings),
    }));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(1));
    fireEvent.click(await screen.findByText("Deck configuration"));

    fireEvent.change(screen.getByLabelText("Asp. Rack sort_barcode07"), {
      target: { value: "2" },
    });

    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceRacks: expect.objectContaining({ sort_barcode07: 2 }),
        }),
      ),
    );
  });

  it("says the plate names are still to come when no run has produced any", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      rows: [],
      errors: [],
      row_count: 0,
      excluded: [],
      excluded_count: 0,
      settings: resolvedSettingsFromUi(settings),
    }));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());
    fireEvent.click(await screen.findByText("Deck configuration"));

    expect(screen.getByText(/Plate names come from the run/i)).toBeInTheDocument();
  });
});
