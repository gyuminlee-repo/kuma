/**
 * Typed view over the generated file-shape previews.
 *
 * The JSON beside this file is written by `scripts/gen_mame_format_preview.py`
 * straight out of `templates/`, so the tables the operator reads in the panel
 * are the very rows of the file the sample-data loader will hand them. This
 * module only puts a type on it; nothing here restates a cell value.
 */
import generated from "./mameFormatPreviews.generated.json";

/** Which cell of which window tells sibling formats apart. */
export interface FormatPreviewHighlight {
  /** Index into `windows`. */
  window: number;
  /** Row index inside that window. */
  row: number;
  /** Column index inside that row. */
  col: number;
}

/** A contiguous run of rows lifted out of the source file. */
export interface FormatPreviewWindow {
  /** One-based row number in the source file, for the caption. */
  startRow: number;
  /** Rectangular grid of already-rendered cell strings. */
  rows: string[][];
}

export interface FormatPreview {
  /** Repo-relative path of the template the rows were read from. */
  source: string;
  /** Whether the first row of the first window is a column header. */
  headerRow: boolean;
  windows: FormatPreviewWindow[];
  /** Rows were skipped between the two windows. */
  ellipsisBetweenWindows: boolean;
  /** The file continues past the last row shown. */
  truncatedAfter: boolean;
  highlight: FormatPreviewHighlight | null;
}

/** Every preview the generator emits, keyed by preview id. */
export const MAME_FORMAT_PREVIEWS: Readonly<Record<string, FormatPreview>> =
  generated.previews;

/** Ids a field can ask for. Verdict and output have no preview by design. */
export type FormatPreviewId = keyof typeof generated.previews;

export function getFormatPreview(id: FormatPreviewId): FormatPreview {
  return MAME_FORMAT_PREVIEWS[id] as FormatPreview;
}
