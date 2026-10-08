/**
 * Helpers shared by the file-shape preview tests in five panels.
 *
 * Every one of them asks the same question: does the table on screen hold the
 * rows the generator read out of the template, rather than rows somebody typed
 * into a test? Written once here so that a test cannot quietly compare against
 * a hand-copied expectation, which is the exact failure the preview exists to
 * prevent.
 *
 * Outside `components/` on purpose. This file imports `@testing-library`, and
 * everything under `components/ui/` is a control that renders on screen, so a
 * later reader would have had no reason to suspect that importing it drags a
 * test library into the production bundle. Test scaffolding lives at the top
 * of `src/`, beside `test-setup.ts`.
 */
import { screen, within, fireEvent } from "@testing-library/react";
import {
  getFormatPreview,
  type FormatPreviewId,
} from "@/data/mameFormatPreviews";

/** Click the "?" that opens the panel carrying `testId`. */
export function openPreview(testId: string): void {
  fireEvent.click(screen.getByTestId(`${testId}-trigger`));
}

/** Rendered body rows of a preview table, the ellipsis rows dropped. */
export function renderedRows(id: string): string[][] {
  const table = screen.getByTestId(`format-preview-table-${id}`);
  return within(table)
    .getAllByRole("row")
    .map((row) =>
      within(row)
        .queryAllByRole("cell")
        .map((cell) => cell.textContent ?? ""),
    )
    .filter((cells) => cells.length > 1);
}

/** The same rows as the generator wrote them, the header row excluded. */
export function generatedRows(id: FormatPreviewId): string[][] {
  const preview = getFormatPreview(id);
  return preview.windows.flatMap((window, index) =>
    preview.headerRow && index === 0 ? window.rows.slice(1) : window.rows,
  );
}

/** Column names rendered by a required-columns table. */
export function renderedColumns(id: string): string[] {
  const table = screen.getByTestId(`format-columns-table-${id}`);
  return within(table)
    .getAllByRole("columnheader")
    .map((cell) => cell.textContent ?? "");
}

/** Every "?" trigger currently on screen, by test id. */
export function previewTriggerIds(): string[] {
  return screen
    .queryAllByTestId(/^format-(preview|columns)-.*-trigger$/)
    .map((node) => node.getAttribute("data-testid") ?? "");
}
