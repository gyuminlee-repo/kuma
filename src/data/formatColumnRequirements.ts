/**
 * Typed view over the hand-written column requirements.
 *
 * Two of the file fields in the app take a file the app never ships a sample
 * of: a MinKNOW sequencing summary, which belongs to the run, and a round
 * result workbook, which the operator assembles. There is nothing to lift rows
 * from, so the help beside those fields lists the columns the reader has to
 * provide and shows no values at all. Inventing plausible-looking rows would
 * put numbers on screen that came from nowhere.
 *
 * The names live in JSON beside this file rather than in here so that
 * `tests/scripts/test_format_column_requirements.py` can read the same list the
 * panel reads and assert each name still appears in the Python that requires
 * it.
 */
import requirements from "./formatColumnRequirements.json";

export interface FormatColumnRequirement {
  /** Repo-relative path of the code that requires these columns. */
  source: string;
  /** Column names, in the order they are shown. */
  columns: string[];
}

export const FORMAT_COLUMN_REQUIREMENTS: Readonly<
  Record<string, FormatColumnRequirement>
> = requirements.requirements;

export type FormatColumnRequirementId = keyof typeof requirements.requirements;

export function getColumnRequirement(
  id: FormatColumnRequirementId,
): FormatColumnRequirement {
  return FORMAT_COLUMN_REQUIREMENTS[id] as FormatColumnRequirement;
}
