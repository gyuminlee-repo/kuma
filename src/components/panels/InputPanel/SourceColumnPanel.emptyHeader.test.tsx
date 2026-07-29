/**
 * SourceColumnPanel.test.tsx, regression guard for the empty-header crash.
 *
 * Root cause: `preview_evolvepro_source` can report an empty header string,
 * because a pandas `df.to_csv(path)` / `df.to_excel(path)` writes an unnamed
 * index column first (observed payload: `headers = ["", "variant", "score"]`).
 * Feeding that straight into a Radix `<SelectItem value="">` throws during
 * render, and Radix renders SelectContent children even while the dropdown is
 * closed (into a detached DocumentFragment, for collection measurement), so
 * the panel crashed without anyone opening the dropdown.
 *
 * The fix maps every column to an index sentinel (`__col_N__`) and converts it
 * back to the real header before it reaches the store. These tests fail if
 * that mapping is reverted.
 *
 * Note: closed Radix items live in a detached fragment, so they are not
 * reachable through `screen`. The preview table is used as the in-document
 * observation window for the label, and typeahead (a closed-trigger keydown,
 * no pointer APIs needed) exercises the write path.
 */

import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";

const mocks = vi.hoisted(() => ({ sendRequest: vi.fn() }));

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { SourceColumnPanel } from "./SourceColumnPanel";
import { useAppStore } from "@/store/appStore";
import type { EvolveproPreview } from "@/types/models";

/** Payload shape observed from the installed sidecar on a pandas-written csv. */
const PREVIEW_WITH_EMPTY_HEADER: EvolveproPreview = {
  sheets: ["Sheet1"],
  headers: ["", "variant", "score"],
  rows: [["0", "F89W", "0.91"]],
};

const PREVIEW_ALL_NAMED: EvolveproPreview = {
  sheets: ["Sheet1"],
  headers: ["variant", "score"],
  rows: [["F89W", "0.91"]],
};

function seedStore(preview: EvolveproPreview | null): void {
  // The panel auto-previews on mount whenever a file path is set, and that
  // response overwrites the seeded store value. Resolve the mock to the same
  // payload so the auto-fetch is a no-op instead of clobbering it with
  // undefined.
  mocks.sendRequest.mockResolvedValue(preview);
  useAppStore.setState({
    evolveproCsvPath: "/tmp/evolvepro.csv",
    evolveproPreview: preview,
    evolveproVariantColumn: null,
    evolveproScoreColumn: null,
    evolveproScoreOrder: "desc",
    evolveproSheetName: null,
    evolveproUsedVariantColumn: null,
    evolveproUsedScoreColumn: null,
  });
}

describe("SourceColumnPanel, empty header column", () => {
  beforeEach(() => {
    seedStore(null);
  });

  it("renders without crashing when a header is an empty string", () => {
    seedStore(PREVIEW_WITH_EMPTY_HEADER);

    expect(() => render(<SourceColumnPanel />)).not.toThrow();

    // The panel has its own error boundary, so a render-time throw would be
    // swallowed into a role="alert" fallback instead of propagating. Assert
    // the real panel body rendered, not the fallback.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Column mapping")).toBeInTheDocument();
    expect(screen.getAllByRole("combobox")).toHaveLength(2);
  });

  it("keeps the empty column listed and labels it as unnamed", async () => {
    seedStore(PREVIEW_WITH_EMPTY_HEADER);
    render(<SourceColumnPanel />);

    // The panel clears the store preview on mount and refetches, so the table
    // appears only once the auto-preview promise settles.
    await screen.findByRole("table");
    const headerCells = screen.getAllByRole("columnheader");
    expect(headerCells.map((c) => c.textContent)).toEqual([
      "Unnamed column 1",
      "variant",
      "score",
    ]);
  });

  it("stores the real header string, not the __col_N__ sentinel", async () => {
    seedStore(PREVIEW_WITH_EMPTY_HEADER);
    render(<SourceColumnPanel />);
    await screen.findByRole("table");

    // Radix typeahead resolves a printable keydown on the closed trigger and
    // fires onValueChange with the item value (the sentinel). "v" uniquely
    // matches "variant" among "Auto-detect" / "Unnamed column 1" / "score".
    const variantTrigger = screen.getAllByRole("combobox")[0];
    fireEvent.keyDown(variantTrigger, { key: "v" });

    expect(useAppStore.getState().evolveproVariantColumn).toBe("variant");
  });

  it("renders a preview whose headers are all named", async () => {
    seedStore(PREVIEW_ALL_NAMED);
    render(<SourceColumnPanel />);

    const table = await screen.findByRole("table");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((c) => c.textContent),
    ).toEqual(["variant", "score"]);
    expect(screen.queryByText(/Unnamed column/)).not.toBeInTheDocument();
  });
});
