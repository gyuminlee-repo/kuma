/**
 * JanusMappingPanel: dry-run preview gating.
 *
 * The export writes a file with no way to inspect it first, so the panel must
 * fetch the preview on mount and on every destination-layout change, and it
 * must refuse to export while the preview reports a plate-layout problem. A
 * preview that merely failed to load is a different thing: export keeps its
 * own fail-fast guards, so a broken preview must not brick a working export.
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
// The panel reads its Janus policy from the store, so the double has to be a
// real store: a plain selector over a frozen object would never re-render on edit.
vi.mock("@/store/mame/mameAppStore", async () => {
  const { create } = await import("zustand");
  const { DEFAULT_JANUS_SETTINGS } = await import("@/lib/mame/janusSettings");
  const useMameAppStore = create<JanusStoreDouble>()((set) => ({
    isExporting: false,
    janusSettings: DEFAULT_JANUS_SETTINGS,
    janusMappingAutosave: null,
    setJanusSettings: (janusSettings: JanusExportSettings) => set({ janusSettings }),
    setJanusMappingAutosave: (janusMappingAutosave) => set({ janusMappingAutosave }),
  }));
  return { useMameAppStore };
});

import { save } from "@tauri-apps/plugin-dialog";
import {
  fetchMameJanusPreview,
  handleExportMameJanusMapping,
} from "@/lib/mame/janus";
import { DEFAULT_JANUS_SETTINGS } from "@/lib/mame/janusSettings";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type {
  JanusAutosaveResult,
  JanusExcludedEntry,
  JanusExportSettings,
  JanusPreviewResult,
  JanusResolvedSettings,
} from "@/types/mame/models";
import { JanusMappingPanel } from "./JanusMappingPanel";

interface JanusStoreDouble {
  isExporting: boolean;
  janusSettings: JanusExportSettings;
  janusMappingAutosave: JanusAutosaveResult | null;
  setJanusSettings: (settings: JanusExportSettings) => void;
  setJanusMappingAutosave: (result: JanusAutosaveResult | null) => void;
}

const mockPreview = vi.mocked(fetchMameJanusPreview);
const mockExport = vi.mocked(handleExportMameJanusMapping);
const mockSave = vi.mocked(save);

/**
 * The instrument sheet header, in the order the writer emits it
 * (`JANUS_DEVICE_HEADER`, kuma_core/shared/janus_deck.py).
 *
 * Written out here rather than imported from the panel: this list is what the
 * file assertions are pinned to, and importing the panel's own fallback would
 * let the two move together with every gate still green.
 */
const INSTRUMENT_COLUMNS = [
  "name",
  "type",
  "no",
  "Asp. Rack",
  "Asp. Posi",
  "Dsp. Rack",
  "Dsp. Posi",
  "volume",
];

/**
 * A preview reply for the shipped defaults, carrying the deck the sidecar
 * generated for a two plate run.
 *
 * `source_racks` and `dest_rack` are empty because the panel offers no way to
 * name a plate by hand; the names the file carries live in the `resolved_`
 * pair, which is what the table reads.
 */
const SETTINGS: JanusResolvedSettings = {
  dest_layout: "source",
  include_verdicts: ["PASS"],
  include_fallback: false,
  output_schema: "device",
  volume: 70,
  sample_type: "cell stock",
  // Recorded with the run and written to no file: the eight column sheet has no
  // liquid class column, which is why no preview cell below carries this.
  liquid_class: "",
  source_racks: {},
  dest_rack: null,
  resolved_source_racks: { NB01: "Stock plate1", NB02: "Stock plate2" },
  resolved_dest_rack: "final culture plate",
  columns: [...INSTRUMENT_COLUMNS],
};

const CLEAN: JanusPreviewResult = {
  rows: [
    {
      name: "HIGH",
      source_plate: "NB01",
      source_well: "E7",
      dest_well: "E7",
      priority_score: 300,
    },
    {
      name: "LOW",
      source_plate: "NB02",
      source_well: "H12",
      dest_well: "H12",
      priority_score: 10,
    },
  ],
  errors: [],
  warnings: [],
  row_count: 2,
  excluded: [],
  excluded_count: 0,
  settings: SETTINGS,
};

const DUPLICATE: JanusPreviewResult = {
  rows: [
    {
      name: "NB01_A1",
      source_plate: "NB01",
      source_well: "A1",
      dest_well: "A1",
      priority_score: 200,
    },
    {
      name: "NB02_A1",
      source_plate: "NB02",
      source_well: "A1",
      dest_well: "A1",
      priority_score: 100,
    },
  ],
  errors: [
    {
      code: "duplicate_dest_well",
      severity: "error",
      message: "Janus mapping: duplicate dest_well would dispense multiple clones",
      mutant_ids: ["NB01_A1", "NB02_A1"],
    },
  ],
  warnings: [],
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
    selected_plate: "NB01",
    is_fallback: false,
  },
  {
    mutant_id: "LOWDEP",
    reason: "verdict_class",
    verdict: "LOWDEPTH",
    selected_plate: "NB01",
    is_fallback: false,
  },
  {
    mutant_id: "FB",
    reason: "fallback",
    verdict: "PASS",
    selected_plate: "NB02",
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
    // The sidecar names every plate of the run whether or not anything was
    // entered, so these are what the preview cells read. Nothing in the panel
    // fills the override maps above.
    resolved_source_racks:
      Object.keys(settings.sourceRacks).length > 0
        ? settings.sourceRacks
        : { NB01: "Stock plate1", NB02: "Stock plate2" },
    resolved_dest_rack: settings.destRack ?? "final culture plate",
    // One sheet, so no branch: the 5-column `legacy5` file is written by
    // analyze as the pick list and never from this panel.
    columns: [...INSTRUMENT_COLUMNS],
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
  mockSave.mockReset();
  mockPreview.mockImplementation(async (settings) => cleanPreviewFor(settings));
});

describe("JanusMappingPanel preview", () => {
  it("fetches the preview on mount", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({ destLayout: "source", outputSchema: "device" }),
      ),
    );
    expect(await screen.findByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("2 rows")).toBeInTheDocument();
  });

  it("refetches when the destination layout changes", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText("Plate order from A1"));
    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({ destLayout: "compact" }),
      ),
    );
  });

  it("refetches when the liquid class is typed in", async () => {
    render(<JanusMappingPanel />);
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

  it("sends the same settings to the export that the preview was built with", async () => {
    render(<JanusMappingPanel />);
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
    render(<JanusMappingPanel />);

    expect(await screen.findByText("Excluded: 3")).toBeInTheDocument();
    const verdictRow = screen.getByText("Verdict class not included").closest("li");
    expect(verdictRow?.textContent).toContain("AMBIG, LOWDEP");
    const fallbackRow = screen.getByText("Fallback pick").closest("li");
    expect(fallbackRow?.textContent).toContain("FB");
  });

  it("says so when nothing was excluded", async () => {
    render(<JanusMappingPanel />);
    expect(
      await screen.findByText("Every clone made the pick."),
    ).toBeInTheDocument();
  });

  it("shows the exact rows the export would write", async () => {
    render(<JanusMappingPanel />);
    const table = await screen.findByRole("table");
    const cells = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) =>
        within(row)
          .getAllByRole("cell")
          .map((c) => c.textContent),
      );
    // Two plates in the run, so the sidecar names them in plate order and
    // dispenses both into the one culture plate; the cells show those generated
    // names, not the (empty) operator overrides.
    // The last cell is the shipped 70 uL, the volume this lab transfers.
    expect(cells).toEqual([
      ["HIGH", "cell stock", "1", "Stock plate1", "E7", "final culture plate", "E7", "70"],
      ["LOW", "cell stock", "2", "Stock plate2", "H12", "final culture plate", "H12", "70"],
    ]);
    const header = within(table)
      .getAllByRole("columnheader")
      .map((c) => c.textContent);
    expect(header).toEqual(INSTRUMENT_COLUMNS);
  });

  it("pins the eight instrument columns and fills every one of them", async () => {
    // The header the table draws comes from the preview reply, so this is the
    // shape of the file rather than a restatement of the panel's fallback.
    render(<JanusMappingPanel />);
    const table = await screen.findByRole("table");

    const header = within(table)
      .getAllByRole("columnheader")
      .map((c) => c.textContent);
    expect(header).toEqual(INSTRUMENT_COLUMNS);
    expect(header).toHaveLength(8);
    // The nine column sheet named `Dsp. Rack` twice, which is why the panel used
    // to address cells by position as well as by name. Nothing may bring the
    // repeat back without this failing.
    expect(new Set(header).size).toBe(header.length);

    const cells = within(within(table).getAllByRole("row")[1])
      .getAllByRole("cell")
      .map((c) => c.textContent);
    expect(cells).toHaveLength(8);
    // A column the panel does not recognise renders blank rather than throwing,
    // so an empty cell is the only symptom a renamed column would leave. That
    // makes the emptiness itself the thing to assert on.
    expect(cells.filter((value) => value === "")).toEqual([]);
  });

  it("names each rack column once in the note describing the file", async () => {
    // The note is the panel's own account of what it writes, and it is what
    // went stale while the sheet had nine columns: it named `Dsp. Rack` twice
    // and a liquid class column between them. Counting the rack names rather
    // than matching the sentence survives a reword and a translation, and the
    // count is exactly what separates the two sheets.
    render(<JanusMappingPanel />);
    await screen.findByRole("table");

    const note = screen.getByText(/^Columns:/).textContent ?? "";
    expect(note.match(/Dsp\. Rack/g)).toHaveLength(1);
    expect(note.match(/Asp\. Rack/g)).toHaveLength(1);
  });

  it("blocks export while the visible preview is stale for edited settings", async () => {
    render(<JanusMappingPanel />);
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
    render(<JanusMappingPanel />);

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
    render(<JanusMappingPanel />);
    expect(
      await screen.findByText(/duplicate dest_well would dispense/i),
    ).toBeInTheDocument();
    expect(exportButton()).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Plate order from A1"));
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(exportButton()).toBeEnabled());
  });

  it("blocks export when the preview itself fails to load", async () => {
    mockPreview.mockRejectedValue(new Error("sidecar unavailable"));
    render(<JanusMappingPanel />);

    await waitFor(() => expect(mockPreview).toHaveBeenCalled());
    expect(await screen.findByText(/sidecar unavailable/i)).toBeInTheDocument();
    expect(exportButton()).toBeDisabled();
  });

  it("retries a failed preview on demand", async () => {
    mockPreview
      .mockRejectedValueOnce(new Error("sidecar unavailable"))
      .mockImplementationOnce(async (settings) => cleanPreviewFor(settings));
    render(<JanusMappingPanel />);
    await screen.findByText(/sidecar unavailable/i);

    fireEvent.click(screen.getByRole("button", { name: "Retry preview" }));
    expect(await screen.findByText("HIGH")).toBeInTheDocument();
  });

  it("renders an empty state rather than a table when nothing was picked", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      rows: [],
      errors: [],
      warnings: [],
      row_count: 0,
      excluded: [],
      excluded_count: 0,
      settings: resolvedSettingsFromUi(settings),
    }));
    render(<JanusMappingPanel />);

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

    render(<JanusMappingPanel />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByLabelText("Plate order from A1"));
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));

    // The first (source-layout) call now lands late carrying a duplicate error.
    resolveFirst?.(DUPLICATE);
    await waitFor(() => expect(exportButton()).toBeEnabled());
    expect(
      screen.queryByText(/duplicate dest_well would dispense/i),
    ).not.toBeInTheDocument();
  });
});

describe("JanusMappingPanel warnings", () => {
  /**
   * v0.15.8: a derived deck used to be an error, which meant the lab got no
   * mapping file at all. It is reported now, and the Export button must stay
   * live while it is on screen.
   *
   * The blank liquid class that used to be reported beside it is gone with the
   * column it described: the eight column sheet has none, so there is nothing
   * left to ship blank and nothing to warn about.
   */
  const WARNED: JanusPreviewResult = {
    ...CLEAN,
    warnings: [
      {
        code: "derived_source_rack",
        severity: "warning",
        message:
          "Janus mapping: plate names generated from the plates of this run " +
          "(NB01 -> Stock plate1, NB02 -> Stock plate2, destination -> " +
          "final culture plate). Label the labware on the deck to match.",
        mutant_ids: [],
      },
    ],
  };

  beforeEach(() => {
    useMameAppStore.setState({ janusSettings: DEFAULT_JANUS_SETTINGS });
    mockPreview.mockReset();
    mockExport.mockReset();
  });

  it("shows what the export named for itself without blocking it", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      ...WARNED,
      settings: resolvedSettingsFromUi(settings),
    }));
    render(<JanusMappingPanel />);

    const warned = await screen.findByTestId("janus-preview-warnings");
    expect(warned).toHaveTextContent(/generated from the plates of this run/i);
    // The names are what the operator has to label the deck with, so the
    // warning has to carry them rather than only saying that it derived some.
    expect(warned).toHaveTextContent(/Stock plate1/);
    expect(warned).toHaveTextContent(/final culture plate/);
    // Reported, not enforced.
    expect(warned).toHaveAttribute("role", "status");
    await waitFor(() => expect(exportButton()).toBeEnabled());
  });

  it("still exports while the warnings are on screen", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      ...WARNED,
      settings: resolvedSettingsFromUi(settings),
    }));
    render(<JanusMappingPanel />);
    await screen.findByTestId("janus-preview-warnings");
    await waitFor(() => expect(exportButton()).toBeEnabled());

    fireEvent.click(exportButton());

    await waitFor(() => expect(mockExport).toHaveBeenCalled());
  });
});

describe("JanusMappingPanel generated plate names", () => {
  /**
   * Observed on a real run: the plates were native barcode folders named
   * `sort_barcode07` and up, which a fixed P1/P2/P3 field list had no rack for,
   * so the export refused every clone. The operator fields that regression was
   * about are gone (the sidecar names the plates now), but the same plate
   * labels still key the generated names, so the lookup has to hold for
   * whatever labels the run produced rather than for a shipped list.
   *
   * The panel reads the name with `row.source_plate`, and a key it cannot find
   * renders an empty cell, so a lookup keyed on anything else fails silently.
   * That is what this pins.
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

  it("shows the generated name for whatever plate the run produced", async () => {
    mockPreview.mockImplementation(async (settings) => ({
      ...NATIVE_BARCODE,
      settings: {
        ...resolvedSettingsFromUi(settings),
        resolved_source_racks: {
          sort_barcode07: "Stock plate1",
          sort_barcode08: "Stock plate2",
        },
      },
    }));
    render(<JanusMappingPanel />);
    const table = await screen.findByRole("table");

    const header = within(table)
      .getAllByRole("columnheader")
      .map((c) => c.textContent);
    const aspRack = header.indexOf("Asp. Rack");
    const names = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[aspRack].textContent);

    expect(names).toEqual(["Stock plate1", "Stock plate2"]);
  });
});

describe("JanusMappingPanel volume", () => {
  /**
   * Step 3 used to ask for the transfer volume above the panel, and that input
   * wrote the same stored `janusSettings.volume` this field writes, so the
   * operator answered one question twice. This is the field that stayed, and
   * nothing exercised it before, so its whole edit path is pinned here.
   */

  it("is the only volume field on the step", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());

    expect(screen.getAllByLabelText(/volume/i)).toHaveLength(1);
  });

  it("sends the shipped 70 uL to the sidecar, not just to the constant", async () => {
    render(<JanusMappingPanel />);

    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({ volume: 70 }),
      ),
    );
    expect((screen.getByLabelText(/^Volume/) as HTMLInputElement).value).toBe("70");
  });

  it("writes a volume edit to the store and refetches the preview", async () => {
    render(<JanusMappingPanel />);
    // Wait for the first (debounced) preview so the edit is a second request
    // rather than a reset of the pending timer.
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText(/^Volume/), { target: { value: "45" } });

    expect(useMameAppStore.getState().janusSettings.volume).toBe(45);
    await waitFor(() =>
      expect(mockPreview).toHaveBeenCalledWith(
        expect.objectContaining({ volume: 45 }),
      ),
    );
  });

  it("says where the volume goes without calling it a guess", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());

    // The hint the deleted step input carried had to survive the move; the
    // sentence calling the shipped volume a baseless assumption did not, since
    // 70 uL is the number the lab gave.
    expect(
      screen.getByText(/Written into the instrument mapping file/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/assumption/i)).toBeNull();
    expect(screen.queryByText(/100 ?uL/i)).toBeNull();
  });
});

describe("JanusMappingPanel fixed choices", () => {
  /**
   * Four things this panel used to offer had no second answer in this lab: the
   * file format (the instrument reads CSV), the output columns (it reads the
   * instrument sheet), a static deck picture stating a slot layout the JANUS
   * software never reads since it matches plates by name, and the rack number
   * fields that replaced that picture, which stated an address the software
   * does not use either.
   *
   * None of the removed controls was queried by any test, so without these the
   * removal would be silent and so would a revert.
   */

  it("offers no format choice: the instrument takes CSV", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());

    expect(screen.queryByLabelText("CSV")).toBeNull();
    expect(screen.queryByLabelText("XLSX")).toBeNull();
    expect(screen.queryByText("Format")).toBeNull();
    // The placeholder used to interpolate the chosen extension.
    expect(
      screen.getByLabelText("Output file path for Janus mapping"),
    ).toHaveAttribute("placeholder", "Target .csv file path");
  });

  it("writes CSV and offers to save nothing else", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() => expect(exportButton()).toBeEnabled());

    fireEvent.click(
      screen.getByRole("button", { name: "Browse save path for Janus mapping" }),
    );
    await waitFor(() => expect(mockSave).toHaveBeenCalled());
    expect(mockSave.mock.calls[0][0]).toEqual(
      expect.objectContaining({ filters: [{ name: "CSV", extensions: ["csv"] }] }),
    );

    fireEvent.click(exportButton());
    await waitFor(() => expect(mockExport).toHaveBeenCalled());
    // Stated rather than defaulted: the sidecar still knows how to write xlsx,
    // and this call site is the reason it never will from here.
    expect(mockExport.mock.calls[0][1]).toBe("csv");
    expect(mockExport.mock.calls[0][0]).toMatch(/\.csv$/);
  });

  it("fixes the output columns to the instrument sheet", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());

    // Queried by role rather than by the labels the removed radios carried, so
    // that a revert is caught whatever it decides to call the two sheets.
    expect(screen.queryByRole("radio", { name: /columns/i })).toBeNull();
    expect(screen.queryByText("Output columns")).toBeNull();
    // Destination layout is the one radio group left.
    expect(screen.getAllByRole("radiogroup")).toHaveLength(1);
    // The instrument fieldset used to be hidden behind the 5-column choice and
    // renders unconditionally now, with nothing toggled first.
    expect(screen.getByLabelText(/^Volume/)).toBeInTheDocument();
    expect(screen.getByLabelText("Liquid class")).toBeInTheDocument();
  });

  it("sends the instrument schema with the export", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() => expect(exportButton()).toBeEnabled());

    fireEvent.click(exportButton());

    await waitFor(() => expect(mockExport).toHaveBeenCalled());
    expect(mockExport.mock.calls[0][2]).toEqual(
      expect.objectContaining({ outputSchema: "device" }),
    );
  });

  it("falls back to the instrument header when the sidecar sends no columns", async () => {
    // The fallback used to be the 5 kuma columns, which named a file this panel
    // no longer writes. No fixture reaches this path otherwise: every other one
    // comes back with columns filled in.
    mockPreview.mockImplementation(async (settings) => ({
      ...CLEAN,
      settings: { ...resolvedSettingsFromUi(settings), columns: [] },
    }));
    render(<JanusMappingPanel />);

    const table = await screen.findByRole("table");
    const header = within(table)
      .getAllByRole("columnheader")
      .map((c) => c.textContent);
    expect(header).toEqual(INSTRUMENT_COLUMNS);
  });

  it("drops the deck picture and the rack number fields with it", async () => {
    render(<JanusMappingPanel />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalled());

    expect(screen.queryByRole("img", { name: /deck/i })).toBeNull();
    expect(screen.queryByText("JANUS Deck Layout")).toBeNull();
    // The rack fields outlived the picture for a while, since a number did
    // reach the file where a picture never did. A plate name reaches it now,
    // and the sidecar generates that from the plates of the run, so there is
    // nothing left here to ask an operator. The disclosure they sat behind went
    // with them rather than staying to head a single unrelated field.
    expect(screen.queryByText("Deck configuration")).toBeNull();
    expect(screen.queryByRole("spinbutton", { name: /Rack/i })).toBeNull();
    // The generated names are read back in the row preview instead.
    expect(screen.getByLabelText(/^Volume/)).toBeInTheDocument();
  });
});
