/**
 * The KURO mutation field shows the shape of an EVOLVEpro prediction table.
 *
 * The field already had a "?" for the notation a typed mutation uses. That
 * sentence is the whole answer while mutations are typed and no answer at all
 * once the field takes a file, so in EVOLVEpro mode the same control carries
 * the sentence and the table together instead of a second identical button.
 *
 * SourceColumnPanel, which sits below, is not what this replaces: it reads the
 * headers of a file already loaded. The preview answers the earlier question,
 * what to put in the file before there is one.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { useAppStore } from "@/store/appStore";
import {
  generatedRows,
  openPreview,
  previewTriggerIds,
  renderedRows,
} from "@/components/ui/formatPreviewTestUtils";

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("../../../lib/file-utils", () => ({ browseFile: vi.fn() }));
vi.mock("../../../lib/workspace", () => ({ useArtifact: () => null }));
vi.mock("./SourceColumnPanel", () => ({
  SourceColumnPanel: () => <div data-testid="source-column-panel" />,
}));
vi.mock("../../widgets/EvolveproSelectTable", () => ({
  EvolveproSelectTable: () => <div data-testid="evolvepro-select-table" />,
}));

import { MutationInput } from "./MutationInput";

beforeEach(() => {
  useAppStore.setState({
    mutationInputMode: "evolvepro",
    evolveproCsvPath: "",
    evolveproTotalCount: 0,
    evolveproRankedCandidates: [],
    evolveproSelectedVariants: [],
  });
});

describe("KURO mutation input file-shape preview", () => {
  it("shows the prediction table as the generator read it", () => {
    render(<MutationInput />);

    openPreview("format-preview-evolvepro");
    expect(renderedRows("evolveproPrediction")).toEqual(
      generatedRows("evolveproPrediction"),
    );
  });

  it("carries the notation sentence inside the same panel, not a second '?'", () => {
    render(<MutationInput />);

    expect(previewTriggerIds()).toEqual(["format-preview-evolvepro-trigger"]);
    openPreview("format-preview-evolvepro");
    expect(
      screen.getByText(
        "Mutations in HGVS or plain format (e.g. A123V, L45*). One per line or comma-separated.",
      ),
    ).toBeInTheDocument();
  });

  it("falls back to the plain sentence when mutations are typed rather than loaded", () => {
    useAppStore.setState({ mutationInputMode: "text" });
    render(<MutationInput />);

    // Negative control: with no file in play there is no shape to show, so the
    // one-string help stays and no preview trigger is rendered.
    expect(previewTriggerIds()).toEqual([]);
  });
});
