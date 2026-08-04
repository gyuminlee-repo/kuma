/**
 * The variant-column picker, as the operator meets it.
 *
 * What matters is that the mapping on screen is the mapping that runs: the
 * auto-detected column is preselected rather than left blank, and a KURO export
 * (whose reader knows its own column) is not asked about at all.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { useMameAppStore } from "@/store/mame/mameAppStore";
import { VariantColumnMapping } from "./VariantColumnMapping";

const PLAIN_LIST_INFO = {
  is_kuro_export: false,
  sheets: ["Sheet1", "Notes"],
  headers: { Sheet1: ["no", "mutation", "note"], Notes: ["free text"] },
  suggested_column: "mutation",
};

describe("VariantColumnMapping", () => {
  beforeEach(() => {
    useMameAppStore.setState({
      variantSourceInfo: null,
      variantSheet: null,
      variantColumn: null,
      variantSelectionExplicit: false,
    });
  });

  it("renders nothing before a file has been inspected", () => {
    const { container } = render(<VariantColumnMapping />);
    expect(container).toBeEmptyDOMElement();
  });

  it("hides itself for a KURO export, which needs no mapping", () => {
    useMameAppStore.setState({
      variantSourceInfo: { ...PLAIN_LIST_INFO, is_kuro_export: true },
    });

    const { container } = render(<VariantColumnMapping />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows the auto-detected column as the current selection", () => {
    useMameAppStore.setState({
      variantSourceInfo: PLAIN_LIST_INFO,
      variantSheet: "Sheet1",
      variantColumn: PLAIN_LIST_INFO.suggested_column,
    });

    render(<VariantColumnMapping />);

    expect(screen.getByTestId("variant-column-mapping")).toBeInTheDocument();
    // The trigger reads back the chosen column, not a placeholder.
    const triggers = screen.getAllByRole("combobox");
    expect(triggers.some((el) => el.textContent?.includes("mutation"))).toBe(true);
    // And the detection is stated, so a wrong guess is visible before a run.
    expect(screen.getByTestId("variant-column-mapping")).toHaveTextContent(
      /Auto-detected column: mutation/i,
    );
  });

  it("offers the sheet picker only when the file has more than one sheet", () => {
    useMameAppStore.setState({
      variantSourceInfo: {
        ...PLAIN_LIST_INFO,
        sheets: ["Sheet1"],
        headers: { Sheet1: ["no", "mutation"] },
      },
      variantSheet: "Sheet1",
      variantColumn: "mutation",
    });

    render(<VariantColumnMapping />);

    expect(screen.getAllByRole("combobox")).toHaveLength(1);
  });

  it("keeps offering the auto option, so a manual pick can be undone", () => {
    useMameAppStore.setState({
      variantSourceInfo: PLAIN_LIST_INFO,
      variantSheet: "Sheet1",
      variantColumn: "note",
      variantSelectionExplicit: true,
    });

    render(<VariantColumnMapping />);

    expect(screen.getByTestId("variant-column-mapping")).toHaveTextContent("note");
  });
});
