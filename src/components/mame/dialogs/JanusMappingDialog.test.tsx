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
vi.mock("@/store/mame/mameAppStore", () => ({
  useMameAppStore: (selector: (s: { isExporting: boolean }) => unknown) =>
    selector({ isExporting: false }),
}));

import {
  fetchMameJanusPreview,
  handleExportMameJanusMapping,
} from "@/lib/mame/janus";
import type { JanusPreviewResult } from "@/types/mame/models";
import { JanusMappingDialog } from "./JanusMappingDialog";

const mockPreview = vi.mocked(fetchMameJanusPreview);
const mockExport = vi.mocked(handleExportMameJanusMapping);

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
};

function exportButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: /Export Janus Mapping/i });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPreview.mockResolvedValue(CLEAN);
});

describe("JanusMappingDialog preview", () => {
  it("fetches the preview when the dialog opens", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalledWith("source"));
    expect(await screen.findByText("HIGH")).toBeInTheDocument();
    expect(screen.getByText("2 rows")).toBeInTheDocument();
  });

  it("does not fetch while the dialog is closed", () => {
    render(<JanusMappingDialog open={false} onOpenChange={() => {}} />);
    expect(mockPreview).not.toHaveBeenCalled();
  });

  it("refetches when the destination layout changes", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(mockPreview).toHaveBeenCalledWith("source"));

    fireEvent.click(screen.getByLabelText("Compact from A1"));
    await waitFor(() => expect(mockPreview).toHaveBeenCalledWith("compact"));
  });

  it("shows the exact rows the export would write", async () => {
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    // Scoped to the table: the deck diagram above it also carries P1/P2 labels.
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
      ["HIGH", "P1", "E7", "E7", "300"],
      ["LOW", "P2", "H12", "H12", "10"],
    ]);
    // Header is the literal export header row, untranslated on purpose.
    const header = within(table)
      .getAllByRole("columnheader")
      .map((c) => c.textContent);
    expect(header).toEqual([
      "name",
      "source_plate",
      "source_well",
      "dest_well",
      "priority_score",
    ]);
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
    mockPreview.mockResolvedValueOnce(DUPLICATE).mockResolvedValueOnce(CLEAN);
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await waitFor(() => expect(exportButton()).toBeDisabled());

    fireEvent.click(screen.getByLabelText("Compact from A1"));
    await waitFor(() => expect(exportButton()).toBeEnabled());
  });

  it("leaves the export enabled when the preview itself fails to load", async () => {
    mockPreview.mockRejectedValue(new Error("sidecar unavailable"));
    render(<JanusMappingDialog open onOpenChange={() => {}} />);

    expect(await screen.findByText(/sidecar unavailable/i)).toBeInTheDocument();
    expect(exportButton()).toBeEnabled();
  });

  it("retries a failed preview on demand", async () => {
    mockPreview
      .mockRejectedValueOnce(new Error("sidecar unavailable"))
      .mockResolvedValueOnce(CLEAN);
    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    await screen.findByText(/sidecar unavailable/i);

    fireEvent.click(screen.getByRole("button", { name: "Retry preview" }));
    expect(await screen.findByText("HIGH")).toBeInTheDocument();
  });

  it("renders an empty state rather than a table when nothing was picked", async () => {
    mockPreview.mockResolvedValue({ rows: [], errors: [], row_count: 0 });
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
      .mockResolvedValueOnce(CLEAN);

    render(<JanusMappingDialog open onOpenChange={() => {}} />);
    fireEvent.click(screen.getByLabelText("Compact from A1"));
    await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));

    // The first (source-layout) call now lands late carrying a duplicate error.
    resolveFirst?.(DUPLICATE);
    await waitFor(() => expect(exportButton()).toBeEnabled());
    expect(
      screen.queryByText(/duplicate dest_well would dispense/i),
    ).not.toBeInTheDocument();
  });
});
