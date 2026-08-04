/**
 * One wording for "this expected workbook disagrees with its own plate sheet".
 *
 * Two paths report the same fact: `useAutosaveHydration` after restoring a
 * project, and the analyze inputs panel after a file pick or a validation. They
 * used to have separate copy, which reads as two different problems. Both go
 * through here now, so the same disagreement is always described the same way.
 *
 * Informational since v0.15.6: the operator names the sheet and the column the
 * variant list is read from, so this states what the workbook says about itself
 * and stops there.
 *
 * Nothing here repairs anything. Which sheet describes the tubes that were
 * actually pipetted is the operator's call, not a guess this layer can make
 * (see the module docstring of `kuma_core/mame/io/plate_order_check.py`).
 */
import i18next from "i18next";
import type {
  PlateOrderFinding,
  PlateOrderReport,
  PlateOrderSeverity,
} from "@/types/mame/models";

/** True when a report has something worth saying at all. */
export function isPlateOrderReportable(report: PlateOrderReport): boolean {
  return (
    report.comparable &&
    (report.mismatched || (report.missing_from_expected ?? []).length > 0)
  );
}

export interface PlateOrderMessage {
  severity: PlateOrderSeverity;
  title: string;
  body: string;
  /** One localized line per disagreeing well; empty when none were returned. */
  examples: string[];
  /** Mutants on the plate with no row in expected_mutations; null when none. */
  missing: string | null;
  /** How to take the sheet order out of the run. */
  escape: string;
  /** Everything above as one paragraph, for single-string channels. */
  text: string;
}

function basename(filePath: string): string {
  return filePath.split(/[/\\]/).pop() ?? filePath;
}

/**
 * Build the user-facing description of a finding.
 *
 * `expectedPath` is named so the operator knows which of the two files they
 * picked is the one that contradicts itself.
 */
export function buildPlateOrderMessage(
  finding: PlateOrderFinding,
  expectedPath: string,
): PlateOrderMessage {
  const t = i18next.t.bind(i18next);
  const filename = basename(expectedPath);
  const sheet = finding.plate_sheet ?? "";
  const examples = (finding.examples ?? []).map((example) =>
    t("mame.plateOrder.example", {
      well: example.well,
      plate: example.plate,
      expected: example.expected,
    }),
  );
  const missingItems = finding.missing_from_expected ?? [];
  const missing =
    missingItems.length > 0
      ? // No `count` option: it would send i18next looking for a plural variant
        // of this key, and the catalogue carries one form in every locale.
        t("mame.plateOrder.missing", { items: missingItems.join(", ") })
      : null;
  const title = t("mame.plateOrder.title", { filename });
  const body = t("mame.plateOrder.bodyInfo", { sheet });
  // Always offered, never demanded. The finding does not stop a run any more
  // (v0.15.6), so this reads as the way to make the sheet order irrelevant
  // rather than as a precondition: name the sheet and column to read, or state
  // the wells with a sample map.
  const escape = t("mame.plateOrder.escape");
  const text = [title, body, ...examples, missing, escape]
    .filter((part): part is string => Boolean(part))
    .join(" ");
  return { severity: finding.severity, title, body, examples, missing, escape, text };
}
