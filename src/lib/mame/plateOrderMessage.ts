/**
 * One wording for "this expected workbook disagrees with its own plate sheet".
 *
 * Two paths report the same fact: `useAutosaveHydration` after restoring a
 * project, and the analyze inputs panel after a file pick or a validation. They
 * used to have separate copy, which reads as two different problems. Both go
 * through here now, so the same disagreement is always described the same way.
 *
 * Blocking since 2026-08-05: `validate_inputs` reports the disagreement as an
 * error and `selectCanRun` holds the button, so this says why the run is refused
 * and what ends the refusal. It was informational between v0.15.6 and then, on
 * the reasoning that a sample map or a confirmed layout made the sheet order
 * irrelevant. It does not: placing wells is not the same as recording which of
 * the workbook's two plates went into the tubes.
 *
 * Nothing here repairs anything. Which sheet describes the tubes that were
 * actually pipetted is the operator's call, not a guess this layer can make
 * (see the module docstring of `kuma_core/mame/io/plate_order_check.py`), and
 * the workbook is the only place that call can be recorded.
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
  /** What ends the refusal: a workbook whose two plates agree. */
  resolution: string;
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
  const body = t("mame.plateOrder.bodyBlocked", { sheet });
  // Names the one thing that clears it. No setting on this screen does, so this
  // points at the workbook: re-export it, or pick one whose sheets agree.
  const resolution = t("mame.plateOrder.resolution");
  const text = [title, body, ...examples, missing, resolution]
    .filter((part): part is string => Boolean(part))
    .join(" ");
  return { severity: finding.severity, title, body, examples, missing, resolution, text };
}
