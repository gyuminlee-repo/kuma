import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/lib/i18n";
import ko from "@/locales/ko.json";
import type { ExcludedGcRow, PreviewGcRow } from "@/types/mame/build_evolvepro_input";
import { toExcludedRow } from "@/lib/mame/gcRowReview";
import { GcRowReview, withSourceLabels, type GcRowReviewState } from "./GcRowReview";

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

  it("names an unticked row as left out by the operator", () => {
    renderReview(ready([USED, WT]), [toExcludedRow(USED)]);
    expect(screen.getByRole("checkbox", { name: "Use 5F at block 1, row 2" })).toHaveAccessibleDescription("left out by you");
    expect(screen.getByRole("checkbox", { name: "Use WT at block 1, row 3" })).not.toHaveAccessibleDescription();
  });

  it("strikes through the data of an unticked row but not its reason", () => {
    renderReview(ready([USED, WT]), [toExcludedRow(USED)]);
    const cells = within(screen.getByRole("checkbox", { name: "Use 5F at block 1, row 2" }).closest("tr") as HTMLElement).getAllByRole("cell");
    const [, file, block, rowCell, sample, area, reason] = cells;
    for (const cell of [file, block, rowCell, sample, area]) expect(cell).toHaveClass("line-through");
    expect(reason).toHaveTextContent("left out by you");
    expect(reason).not.toHaveClass("line-through");
    expect(reason.closest("tr")).not.toHaveClass("line-through");
    const kept = within(screen.getByRole("checkbox", { name: "Use WT at block 1, row 3" }).closest("tr") as HTMLElement).getAllByRole("cell");
    for (const cell of kept) expect(cell).not.toHaveClass("line-through");
  });

  it("gives every group table the same column widths", () => {
    const { container } = render(
      <GcRowReview state={ready([USED, WT, BLANK])} excludedRows={[]} onChange={vi.fn()} onRetry={vi.fn()} />,
    );
    const tables = [...container.querySelectorAll("table")];
    expect(tables.length).toBeGreaterThan(1);
    const widths = tables.map((table) => [...table.querySelectorAll("colgroup col")].map((col) => col.className).join("|"));
    expect(new Set(widths).size).toBe(1);
    for (const table of tables) expect(table).toHaveClass("table-fixed");
    expect(screen.getByText("BLANK")).toHaveAttribute("title", "BLANK");
  });

  it("shows a refusal with the field labels the File column uses", () => {
    renderReview(ready([USED], "round1_report_xlsx has no WT block areas"));
    expect(screen.getByRole("alert")).toHaveTextContent("Raw Agilent report has no WT block areas");
    expect(screen.getByRole("alert")).not.toHaveTextContent("round1_report_xlsx");
  });
});

describe("withSourceLabels in Korean", () => {
  // The app loads a locale chunk on demand; the test supplies the same file.
  i18n.addResourceBundle("ko", "translation", ko, true, true);
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("replaces each field key with its Korean File-column label and leaves the rest", async () => {
    await i18n.changeLanguage("ko");
    const t = i18n.t.bind(i18n) as (key: string, options?: Record<string, unknown>) => string;
    expect(withSourceLabels(t, "numeric_report_xlsx carries 2 numeric IDs; remeasure_well_xlsx has no WT areas")).toBe(
      "숫자 ID Agilent report carries 2 numeric IDs; Well 라벨 반복 측정 report has no WT areas",
    );
    expect(withSourceLabels(t, "excluded_rows names a row")).toBe("excluded_rows names a row");
  });

  it("shows the Korean label in the review refusal", async () => {
    await i18n.changeLanguage("ko");
    renderReview(ready([USED], "gc_data_xlsx has no row that belongs to this run"));
    expect(screen.getByRole("alert")).toHaveTextContent("GC data 시트 has no row that belongs to this run");
  });
});
