/**
 * OffLayoutRecordsNotice, reads that arrived from wells nobody declared.
 *
 * When the operator declares which wells the campaign occupies, the rest are
 * stated to be empty. An empty well that produces reads is worth seeing, and it
 * used to be invisible: the record was scored against whatever the draft
 * happened to place there, or filed under an `UNKNOWN_*` key nobody reads.
 *
 * Reported, never a refusal. The same counts appear when barcode crosstalk
 * leaks reads between wells, and the count alone does not say which of the two
 * happened, so this hands the operator the wells and stops there.
 */

import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

/** How many wells to name before the notice starts counting instead. */
const NAMED_WELL_LIMIT = 8;

export function OffLayoutRecordsNotice() {
  const { t } = useTranslation();
  const offLayoutRecords = useMameAppStore((s) => s.offLayoutRecords);

  if (offLayoutRecords === null || offLayoutRecords.count === 0) return null;

  const named = offLayoutRecords.wells.slice(0, NAMED_WELL_LIMIT);
  const remaining = offLayoutRecords.wells.length - named.length;

  return (
    <div
      role="status"
      data-testid="off-layout-records-notice"
      className="flex items-start gap-2 rounded-control border border-border bg-muted/40 px-3 py-2 text-caption"
    >
      <Info size={16} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
      <div className="min-w-0 space-y-0.5">
        <p className="font-semibold text-foreground">
          {t("mame.qc.offLayoutRecords.title", {
            records: offLayoutRecords.count,
            wells: offLayoutRecords.wells.length,
          })}
        </p>
        <p className="text-muted-foreground">
          {t("mame.qc.offLayoutRecords.desc", {
            list: named.map((w) => `${w.well} (${w.records})`).join(", "),
          })}
          {remaining > 0
            ? ` ${t("mame.qc.offLayoutRecords.more", { count: remaining })}`
            : ""}
        </p>
      </div>
    </div>
  );
}
