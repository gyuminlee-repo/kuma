import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ExcludedGcRow, PreviewGcRow } from "@/types/mame/build_evolvepro_input";
import { toExcludedRow } from "@/lib/mame/gcRowReview";
import { GcRowReview, type GcRowReviewState } from "./GcRowReview";

function row(overrides: Partial<PreviewGcRow>): PreviewGcRow {
  return {
    source: "round1_report_xlsx",
    block_index: 1,
    row_index: 2,
    sample_name: "5F",
    area: 100,
    kind: "variant",
    status: "used",
    reason: null,
    detail: "",
    flags: [],
    ...overrides,
  };
}

const USED = row({ row_index: 2, sample_name: "5F" });
const WT = row({ row_index: 3, sample_name: "WT", kind: "wt", status: "wt" });
const BLANK = row({ row_index: 4, sample_name: "BLANK", status: "set_aside", reason: "non_well_sample" });
const LOCKED = row({ row_index: 5, sample_name: "A1", status: "locked", reason: "other_notation" });
const FLAGGED = row({ block_index: 2, row_index: 2, sample_name: "WT", status: "wt", flags: ["duplicate_replicate"] });

function ready(rows: PreviewGcRow[], refusal: string | null = null): GcRowReviewState {
  return { status: "ready", result: { rows, refusal, selection_refusal: null } };
}

function renderReview(state: GcRowReviewState, excludedRows: ExcludedGcRow[] = []) {
  const onChange = vi.fn();
  const onRetry = vi.fn();
  render(<GcRowReview state={state} excludedRows={excludedRows} onChange={onChange} onRetry={onRetry} />);
  return { onChange, onRetry };
}

describe("GcRowReview", () => {
  it("shows an empty state before the inputs are chosen", () => {
    renderReview({ status: "idle" });
    expect(screen.getByText(/Choose the measurement file/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("offers a retry when the rows could not be read", () => {
    const { onRetry } = renderReview({ status: "failed", message: "file locked" });
    expect(screen.getByRole("alert")).toHaveTextContent("file locked");
    fireEvent.click(screen.getByRole("button", { name: "Read again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("ticks the rows the build uses and disables the rows it does not", () => {
    renderReview(ready([USED, WT, BLANK, LOCKED]));
    const used = screen.getByRole("checkbox", { name: "Use 5F at block 1, row 2" });
    const wt = screen.getByRole("checkbox", { name: "Use WT at block 1, row 3" });
    const blank = screen.getByRole("checkbox", { name: "Use BLANK at block 1, row 4" });
    const locked = screen.getByRole("checkbox", { name: "Use A1 at block 1, row 5" });
    expect(used).toBeChecked();
    expect(used).toBeEnabled();
    expect(wt).toBeChecked();
    expect(wt).toBeEnabled();
    expect(blank).not.toBeChecked();
    expect(blank).toBeDisabled();
    expect(locked).toBeDisabled();
    expect(blank).toHaveAccessibleDescription(/not a well of this plate/);
    expect(locked).toHaveAccessibleDescription(/refuses the build whether ticked or not/);
  });

  it("reports an unticked row as an exclusion and shows a saved one unticked", () => {
    const { onChange } = renderReview(ready([USED, WT]));
    fireEvent.click(screen.getByRole("checkbox", { name: "Use 5F at block 1, row 2" }));
    expect(onChange).toHaveBeenCalledWith([toExcludedRow(USED)]);
  });

  it("restores every tick at once", () => {
    const { onChange } = renderReview(ready([USED, WT]), [toExcludedRow(USED)]);
    expect(screen.getByRole("checkbox", { name: "Use 5F at block 1, row 2" })).not.toBeChecked();
    expect(screen.getByText("1 row(s) unticked by you")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tick all again" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("lists flagged rows first, outside the folded groups", () => {
    renderReview(ready([USED, FLAGGED]));
    const flagged = screen.getByRole("checkbox", { name: "Use WT at block 2, row 2" });
    expect(flagged.closest("details")).toBeNull();
    expect(screen.getByText(/Check these rows first \(1\)/)).toBeInTheDocument();
    const used = screen.getByRole("checkbox", { name: "Use 5F at block 1, row 2" });
    expect(used.closest("details")).not.toBeNull();
  });

  it("states a refusal the build would give", () => {
    renderReview(ready([USED], "row 9 uses the other notation"));
    expect(screen.getByRole("alert")).toHaveTextContent("row 9 uses the other notation");
  });

  it("keeps the column headers in English", () => {
    renderReview(ready([USED]));
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Use", "File", "Block", "Row", "Sample", "Area", "Reason",
    ]);
  });
});
