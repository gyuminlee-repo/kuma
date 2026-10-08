/**
 * ExcludedOccupantsNotice, the variants this run left off the plate.
 *
 * Declaring which wells a campaign filled is also declaring which it did not,
 * and what the draft placed in an undeclared well is not sequenced. Those
 * variants have no verdict, so on the review screen they are an absence: the
 * plate cell is blank and the table has no row, which is exactly what a well
 * that was never part of the campaign looks like.
 *
 * The selection panel warns before the run, but that warning is drawn from a
 * draft recomputed off the current inputs, so it cannot speak for a result that
 * was restored from a project. This reads what the run itself recorded
 * (`layout_provenance.excluded_occupants`), which is the only statement of the
 * fact that survives a reopen.
 *
 * Reported, never a complaint: leaving wells out is a description of the bench.
 */

import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

/** How many variants to name before the notice starts counting instead. */
const NAMED_LIMIT = 8;

export function ExcludedOccupantsNotice() {
  const { t } = useTranslation();
  const layoutProvenance = useMameAppStore((s) => s.layoutProvenance);

  const excluded = layoutProvenance?.excluded_occupants;
  // Absent on results written before this field existed, and on every run that
  // declared nothing, so a project from either reads as "nothing was left out"
  // rather than drawing an empty notice.
  if (!excluded) return null;
  const entries = Object.entries(excluded);
  if (entries.length === 0) return null;

  const named = entries.slice(0, NAMED_LIMIT);
  const remaining = entries.length - named.length;

  return (
    <div
      role="status"
      data-testid="excluded-occupants-notice"
      className="flex items-start gap-2 rounded-control border border-border bg-muted/40 px-3 py-2 text-caption"
    >
      <Info size={16} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
      <div className="min-w-0 space-y-0.5">
        <p className="font-semibold text-foreground">
          {t("mame.qc.excludedOccupants.title", { count: entries.length })}
        </p>
        <p className="text-muted-foreground">
          {t("mame.qc.excludedOccupants.desc", {
            list: named.map(([well, sample]) => `${sample} (${well})`).join(", "),
          })}
          {remaining > 0
            ? ` ${t("mame.qc.excludedOccupants.more", { count: remaining })}`
            : ""}
        </p>
      </div>
    </div>
  );
}
