/**
 * The "?" beside a file field: what the file it wants looks like, shown as the
 * spreadsheet rows themselves.
 *
 * Written for step 4.1 first and now used by every file field in the app whose
 * input is a table the operator prepares. Fields that take a folder, a
 * sequence, a structure, a file the app itself wrote, or an output path have no
 * "?": there is no shape for the reader to match.
 *
 * The field labels name a format ("Raw Agilent report", "Numeric-ID Agilent
 * report") and a sentence of prose underneath describes it, but three of those
 * formats are the same file for their first fifteen rows and differ in one
 * cell. A reader holding an unfamiliar export cannot settle which one they
 * have from a description; they can settle it by comparing their sheet to the
 * sheet. So the rows come out of `templates/` through
 * `scripts/gen_mame_format_preview.py`, which is the same file the sample-data
 * loader puts in this field.
 *
 * For a block format that means two windows, not the top of the file: the top
 * is the wild-type block every one of them carries. The window that matters is
 * the first non-wild-type block, and inside it the sample name cell, which is
 * marked.
 *
 * The locale keys this file reads still sit under `mame.buildEvolvepro`, where
 * they were written when only step 4.1 had a preview, so KURO now reads a MAME
 * key. Moving them means re-stamping ten locale files and the step 4.1 tests
 * for no change on screen; fold it into the next round of locale work rather
 * than paying it on its own.
 */
import { useTranslation } from "react-i18next";
import { InfoPopover } from "@/components/ui/InfoPopover";
import {
  getFormatPreview,
  type FormatPreview,
  type FormatPreviewId,
} from "@/data/mameFormatPreviews";
import {
  getColumnRequirement,
  type FormatColumnRequirementId,
} from "@/data/formatColumnRequirements";

/** Wide enough for the ten-column designed variant list before it scrolls. */
const PANEL_WIDTH = 420;

/** One preview to show, with the already-translated name of its format. */
export interface FormatPreviewEntry {
  id: FormatPreviewId;
  /** Format name, used as the table caption. */
  title: string;
  /**
   * One sentence the table itself cannot carry, shown under the caption. Two
   * numeric-ID formats are the same shape and differ in what the numbers count,
   * which is a fact about the run and not a cell anyone can point at.
   */
  note?: string;
}

/** A file with no bundled sample: the columns it must carry, and nothing else. */
export interface RequiredColumnsEntry {
  id: FormatColumnRequirementId;
  /** Format name, used as the table caption. */
  title: string;
  /** How the columns are laid out (delimiter, which sheet, header row). */
  note: string;
}

function fileName(source: string): string {
  const parts = source.split("/");
  return parts[parts.length - 1] ?? source;
}

function isHighlighted(
  preview: FormatPreview,
  windowIndex: number,
  rowIndex: number,
  colIndex: number,
): boolean {
  const highlight = preview.highlight;
  return (
    highlight !== null &&
    highlight.window === windowIndex &&
    highlight.row === rowIndex &&
    highlight.col === colIndex
  );
}

function PreviewCell({
  value,
  highlighted,
  testId,
}: {
  value: string;
  highlighted: boolean;
  testId?: string;
}) {
  return (
    <td
      data-testid={testId}
      className={
        highlighted
          ? "whitespace-nowrap border border-primary bg-primary/15 px-1.5 py-0.5 font-semibold text-primary"
          : "whitespace-nowrap border border-border/60 px-1.5 py-0.5 text-foreground"
      }
    >
      {value}
    </td>
  );
}

/** Caption block shared by both table kinds: the format name, then the note. */
function PreviewCaption({ title, note }: { title: string; note?: string }) {
  return (
    <caption className="px-1.5 py-1 text-left text-caption text-foreground">
      <span className="block font-semibold">{title}</span>
      {note && (
        <span className="block font-normal text-muted-foreground">{note}</span>
      )}
    </caption>
  );
}

/**
 * The columns a file has to carry, with no rows under them. A header and
 * nothing else is the honest rendering: the app ships no sample of this file,
 * so any row here would be a value nobody measured.
 */
function RequiredColumnsTable({ id, title, note }: RequiredColumnsEntry) {
  const { t } = useTranslation();
  const requirement = getColumnRequirement(id);
  return (
    <div className="mb-3 last:mb-0">
      <div className="overflow-x-auto rounded-control border border-border">
        <table
          data-testid={`format-columns-table-${id}`}
          className="w-full border-collapse text-plate-tiny font-mono"
        >
          <PreviewCaption title={title} note={note} />
          <thead>
            <tr className="bg-muted">
              {requirement.columns.map((column) => (
                <th
                  key={column}
                  scope="col"
                  className="whitespace-nowrap border border-border/60 px-1.5 py-0.5 text-left font-semibold text-muted-foreground"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
        </table>
      </div>
      <p className="mt-1 text-caption text-muted-foreground">
        {t("mame.buildEvolvepro.formatPreview.requiredColumnsNote")}
      </p>
    </div>
  );
}

function FormatPreviewTable({ id, title, note }: FormatPreviewEntry) {
  const { t } = useTranslation();
  const preview = getFormatPreview(id);
  const columnCount = preview.windows[0]?.rows[0]?.length ?? 1;
  // A header row is the first row of the first window and is never part of the
  // body, so the body of that window starts one row later.
  const headerCells = preview.headerRow ? preview.windows[0]?.rows[0] : undefined;

  return (
    <div className="mb-3 last:mb-0">
      <div className="overflow-x-auto rounded-control border border-border">
        <table
          data-testid={`format-preview-table-${id}`}
          className="w-full border-collapse text-plate-tiny font-mono"
        >
          <PreviewCaption title={title} note={note} />
          {headerCells && (
            <thead>
              <tr className="bg-muted">
                {headerCells.map((cell, colIndex) => (
                  <th
                    key={colIndex}
                    scope="col"
                    className="whitespace-nowrap border border-border/60 px-1.5 py-0.5 text-left font-semibold text-muted-foreground"
                  >
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          {preview.windows.map((window, windowIndex) => {
            const bodyRows =
              preview.headerRow && windowIndex === 0
                ? window.rows.slice(1)
                : window.rows;
            const rowOffset = preview.headerRow && windowIndex === 0 ? 1 : 0;
            return (
              <tbody key={windowIndex}>
                {windowIndex > 0 && preview.ellipsisBetweenWindows && (
                  <tr>
                    <td
                      colSpan={columnCount}
                      className="border border-border/60 px-1.5 py-0.5 text-center text-muted-foreground"
                    >
                      <span aria-hidden="true">⋮</span>
                      <span className="sr-only">
                        {t("mame.buildEvolvepro.formatPreview.omitted")}
                      </span>
                    </td>
                  </tr>
                )}
                {bodyRows.map((row, bodyIndex) => (
                  <tr key={bodyIndex}>
                    {row.map((cell, colIndex) => {
                      const highlighted = isHighlighted(
                        preview,
                        windowIndex,
                        bodyIndex + rowOffset,
                        colIndex,
                      );
                      return (
                        <PreviewCell
                          key={colIndex}
                          value={cell}
                          highlighted={highlighted}
                          testId={
                            highlighted ? `format-preview-highlight-${id}` : undefined
                          }
                        />
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            );
          })}
          {preview.truncatedAfter && (
            <tfoot>
              <tr>
                <td
                  colSpan={columnCount}
                  className="border border-border/60 px-1.5 py-0.5 text-center text-muted-foreground"
                >
                  <span aria-hidden="true">⋮</span>
                  <span className="sr-only">
                    {t("mame.buildEvolvepro.formatPreview.omitted")}
                  </span>
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      {preview.highlight !== null && (
        <p className="mt-1 text-caption text-muted-foreground">
          {t("mame.buildEvolvepro.formatPreview.highlightNote")}
        </p>
      )}
      <p className="mt-0.5 text-caption text-muted-foreground">
        {t("mame.buildEvolvepro.formatPreview.sourceLabel", {
          file: fileName(preview.source),
        })}
      </p>
    </div>
  );
}

export function FormatPreviewHelp({
  fieldLabel,
  entries = [],
  columnEntries = [],
  intro,
  testId,
}: {
  /** Translated label of the field this help belongs to. */
  fieldLabel: string;
  /** One entry per format the field accepts, in the order they are shown. */
  entries?: FormatPreviewEntry[];
  /** Formats with no bundled sample, shown as their required columns. */
  columnEntries?: RequiredColumnsEntry[];
  /**
   * Prose that already belonged to this field, kept above the tables instead of
   * beside them: a field carrying its own "?" for a sentence and a second "?"
   * for the shape offers the reader two identical buttons and no way to guess
   * which is which.
   */
  intro?: string;
  testId: string;
}) {
  const { t } = useTranslation();
  const formatCount = entries.length + columnEntries.length;
  if (formatCount === 0) return null;
  return (
    <InfoPopover
      variant="icon"
      width={PANEL_WIDTH}
      testId={testId}
      label={t("mame.buildEvolvepro.formatPreview.heading")}
      ariaLabel={t("mame.buildEvolvepro.formatPreview.trigger", {
        label: fieldLabel,
      })}
    >
      {intro && (
        <p className="mb-2 text-caption text-muted-foreground">{intro}</p>
      )}
      {formatCount > 1 && (
        <p className="mb-2 text-caption text-muted-foreground">
          {t("mame.buildEvolvepro.formatPreview.multipleFormats")}
        </p>
      )}
      {entries.map((entry) => (
        <FormatPreviewTable
          key={entry.id}
          id={entry.id}
          title={entry.title}
          note={entry.note}
        />
      ))}
      {columnEntries.map((entry) => (
        <RequiredColumnsTable
          key={entry.id}
          id={entry.id}
          title={entry.title}
          note={entry.note}
        />
      ))}
    </InfoPopover>
  );
}
