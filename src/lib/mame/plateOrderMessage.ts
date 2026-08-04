/**
 * One wording for "this expected workbook disagrees with its own plate sheet".
 *
 * Two paths report the same fact: `useAutosaveHydration` after restoring a
 * project, and the analyze inputs panel after a file pick or a validation. They
 * used to have separate copy, which reads as two different problems. Both go
 * through here now, so the same disagreement is always described the same way
 * and only the severity changes the tone.
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

/** Layout inputs that decide whether the sheet order reaches a well at all. */
export interface PlateOrderLayoutInputs {
  hasSampleMap: boolean;
  hasWellLayout: boolean;
}

/**
 * Grade an ungraded report the way the sidecar does.
 *
 * Mirrors `_plate_order_finding` in
 * `python-core/sidecar_mame/handlers/analyze.py`: `expected_mutations` is a well
 * coordinate system only when the layout is inferred from it, which happens
 * exactly when neither a sample map nor a confirmed well layout is given.
 * Used for the `check_plate_order` response (which carries no severity) and to
 * re-grade a stored finding after the operator supplies one of those inputs.
 */
export function gradePlateOrder(
  report: PlateOrderReport,
  inputs: PlateOrderLayoutInputs,
): PlateOrderSeverity {
  return inputs.hasSampleMap || inputs.hasWellLayout ? "info" : "blocking";
}

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
  /** How to get past a blocking finding; null for an informational one. */
  escape: string | null;
  /** Everything above as one paragraph, for single-string channels. */
  text: string;
}

function basename(filePath: string): string {
  return filePath.split(/[/\\]/).pop() ?? filePath;
}

/**
 * Build the user-facing description of a graded finding.
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
  const body =
    finding.severity === "blocking"
      ? t("mame.plateOrder.bodyBlocking", { sheet })
      : t("mame.plateOrder.bodyInfo", { sheet });
  const escape =
    finding.severity === "blocking" ? t("mame.plateOrder.escape") : null;
  const text = [title, body, ...examples, missing, escape]
    .filter((part): part is string => Boolean(part))
    .join(" ");
  return { severity: finding.severity, title, body, examples, missing, escape, text };
}
