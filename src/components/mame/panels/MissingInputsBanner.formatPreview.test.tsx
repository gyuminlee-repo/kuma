/**
 * The sequencing summary is only ever chosen here, so the help is only here.
 *
 * No step exposes a picker for it: it arrives with the run folder, and the one
 * moment an operator points at it by hand is when a restored project could not
 * find it. Nothing in the app ships a sample of that file either, so what the
 * "?" shows is the columns the reader has to provide and no values at all.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { useMissingInputs } from "@/lib/mame/missingInputs";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { getColumnRequirement } from "@/data/formatColumnRequirements";
import {
  openPreview,
  previewTriggerIds,
  renderedColumns,
} from "@/components/ui/formatPreviewTestUtils";

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ stat: vi.fn() }));
vi.mock("sonner", () => ({ toast: { warning: vi.fn() } }));

import { MissingInputsBanner } from "./MissingInputsBanner";

beforeEach(() => {
  useMameAppStore.setState((state) => ({
    inputDir: "",
    rawRunParams: {
      ...state.rawRunParams,
      customBarcodesPath: "",
      sequencingSummaryPath: "",
    },
  }));
  useMissingInputs.getState().setMissing([
    { field: "inputDir", name: "run_2026_03" },
    { field: "sequencingSummaryPath", name: "sequencing_summary_x.txt" },
  ]);
});

describe("MissingInputsBanner file-shape help", () => {
  it("lists the columns the summary parser reads, taken from the data file", () => {
    render(<MissingInputsBanner />);

    openPreview("format-preview-sequencing-summary");
    expect(renderedColumns("sequencingSummary")).toEqual(
      getColumnRequirement("sequencingSummary").columns,
    );
  });

  it("shows no sample rows, only the header", () => {
    render(<MissingInputsBanner />);

    openPreview("format-preview-sequencing-summary");
    const table = screen.getByTestId("format-columns-table-sequencingSummary");
    expect(table.querySelectorAll("tbody").length).toBe(0);
  });

  it("gives the run-folder row no '?' at all", () => {
    render(<MissingInputsBanner />);

    // Negative control: the same list carries a directory, which has no shape.
    expect(previewTriggerIds()).toEqual([
      "format-preview-sequencing-summary-trigger",
    ]);
  });
});
