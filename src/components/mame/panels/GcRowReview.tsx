/**
 * Step 4.1 row review: every row of the GC files the build will read, with the
 * build's own judgement, and a tick box on each row the operator may leave out.
 *
 * The statuses come from `mame.activity.preview_gc_rows`, which runs the
 * build's reading stage; this component judges nothing. Suspicious rows (a
 * repeated WT number, a well measured twice) are listed first and stay open;
 * the rest fold by status. Rows the reader set aside, passed over or locked
 * show their reason and cannot be ticked: ticking a BLANK cannot make it a
 * measurement of this run, and a locked row refuses the build either way.
 */
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  ExcludedGcRow,
  GcRowStatus,
  GcSourceField,
  PreviewGcRow,
  PreviewGcRowsResult,
} from "@/types/mame/build_evolvepro_input";
import {
  effectiveExclusions,
  groupRows,
  isRowExcluded,
  isToggleable,
  setRowIncluded,
} from "@/lib/mame/gcRowReview";

export type GcRowReviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "failed"; message: string }
  | { status: "ready"; result: PreviewGcRowsResult };

/** The input field each row came from, named as the field is on screen. */
export const GC_SOURCE_LABEL: Record<GcSourceField, string> = {
  activity_path: "mame.buildEvolvepro.primarySourceLongFormat",
  gc_data_xlsx: "mame.buildEvolvepro.primarySourceGcSheet",
  round1_report_xlsx: "mame.buildEvolvepro.primarySourceRawReport",
  numeric_report_xlsx: "mame.buildEvolvepro.primarySourceNumericReport",
  remeasure_report_xlsx: "mame.buildEvolvepro.confirmationSourceVariantLabels",
  remeasure_numeric_xlsx: "mame.buildEvolvepro.confirmationSourceNumericIds",
  remeasure_well_xlsx: "mame.buildEvolvepro.confirmationSourceWellLabels",
};

const GROUP_LABEL: Record<GcRowStatus, string> = {
  used: "mame.buildEvolvepro.rowReview.groupUsed",
  wt: "mame.buildEvolvepro.rowReview.groupWt",
  set_aside: "mame.buildEvolvepro.rowReview.groupSetAside",
  ignored: "mame.buildEvolvepro.rowReview.groupIgnored",
  locked: "mame.buildEvolvepro.rowReview.groupLocked",
  unjudged: "mame.buildEvolvepro.rowReview.groupUnjudged",
};

/** Reason codes the core emits, as they are worded on screen. */
const REASON_KEYS = new Set([
  "non_well_sample",
  "unrecognized_sample",
  "numeric_calibration",
  "no_area",
  "no_name",
  "unmapped_well",
  "unmapped_variant",
  "declared_wt_well",
  "wt_of_unmeasured_cohort",
  "other_notation",
  "duplicate_replicate",
  "duplicate_well",
  "operator_excluded",
]);

export function rowLocation(
  t: (key: string, options?: Record<string, unknown>) => string,
  row: { block_index: number | null; row_index: number },
): string {
  return row.block_index === null
    ? t("mame.buildEvolvepro.rowReview.locationRow", { row: row.row_index })
    : t("mame.buildEvolvepro.rowReview.locationBlock", { block: row.block_index, row: row.row_index });
}

export function reasonText(
  t: (key: string, options?: Record<string, unknown>) => string,
  code: string,
): string {
  return REASON_KEYS.has(code) ? t(`mame.buildEvolvepro.rowReview.reason.${code}`) : code;
}

function formatArea(area: number | null): string {
  return area === null ? "-" : String(Number(area.toPrecision(6)));
}

export function GcRowReview({
  state,
  excludedRows,
  onChange,
  onRetry,
}: {
  state: GcRowReviewState;
  excludedRows: ExcludedGcRow[];
  onChange: (next: ExcludedGcRow[]) => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  const headingId = useId();

  let body;
  if (state.status === "idle") {
    body = (
      <p role="status" className="rounded-md border border-dashed border-border bg-muted/20 px-3 py-4 text-center text-xs text-muted-foreground">
        {t("mame.buildEvolvepro.rowReview.empty")}
      </p>
    );
  } else if (state.status === "loading") {
    body = (
      <p role="status" aria-busy="true" className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" aria-hidden="true" />
        {t("mame.buildEvolvepro.rowReview.loading")}
      </p>
    );
  } else if (state.status === "failed") {
    body = (
      <div role="alert" className="space-y-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-foreground">
        <p className="whitespace-pre-wrap break-words">
          {t("mame.buildEvolvepro.rowReview.failed", { message: state.message })}
        </p>
        <Button type="button" variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={onRetry}>
          {t("mame.buildEvolvepro.rowReview.retry")}
        </Button>
      </div>
    );
  } else {
    const { rows, refusal } = state.result;
    const active = effectiveExclusions(rows, excludedRows);
    const { suspicious, groups } = groupRows(rows);
    body = (
      <div className="space-y-2">
        {refusal !== null && (
          <p role="alert" className="whitespace-pre-wrap break-words rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            {t("mame.buildEvolvepro.rowReview.refusal", { message: refusal })}
          </p>
        )}
        {rows.length === 0 ? (
          <p role="status" className="text-xs text-muted-foreground">
            {t("mame.buildEvolvepro.rowReview.noRows")}
          </p>
        ) : (
          <>
            {active.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p role="status" className="min-w-0 flex-1 text-xs text-muted-foreground">
                  {t("mame.buildEvolvepro.rowReview.excludedCount", { count: active.length })}
                </p>
                <Button type="button" variant="outline" size="sm" className="h-6 px-2 text-xs" onClick={() => onChange([])}>
                  {t("mame.buildEvolvepro.rowReview.tickAll")}
                </Button>
              </div>
            )}
            {suspicious.length > 0 && (
              <div className="space-y-1 rounded-md border border-amber-500/30 bg-amber-500/5 px-2 py-2">
                <p className="text-xs font-semibold text-amber-700 dark:text-amber-400">
                  {t("mame.buildEvolvepro.rowReview.suspicious", { count: suspicious.length })}
                </p>
                <RowTable rows={suspicious} excludedRows={excludedRows} onChange={onChange} highlight />
              </div>
            )}
            {groups.map(({ status, rows: members }) => (
              <details key={status} className="rounded-md border border-border px-2 py-1.5">
                <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                  {t(GROUP_LABEL[status], { count: members.length })}
                </summary>
                <div className="mt-1.5">
                  <RowTable rows={members} excludedRows={excludedRows} onChange={onChange} />
                </div>
              </details>
            ))}
          </>
        )}
      </div>
    );
  }

  return (
    <section aria-labelledby={headingId} className="space-y-2" data-testid="gc-row-review">
      <h4 id={headingId} className="text-sm font-medium text-foreground">
        {t("mame.buildEvolvepro.rowReview.title")}
      </h4>
      <p className="text-xs text-muted-foreground">{t("mame.buildEvolvepro.rowReview.intro")}</p>
      {body}
    </section>
  );
}

function RowTable({
  rows,
  excludedRows,
  onChange,
  highlight = false,
}: {
  rows: PreviewGcRow[];
  excludedRows: ExcludedGcRow[];
  onChange: (next: ExcludedGcRow[]) => void;
  highlight?: boolean;
}) {
  const { t } = useTranslation();
  const tableId = useId();
  return (
    <div className="max-h-64 overflow-auto rounded-md border border-border">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-muted">
          <tr>
            <th className="px-2 py-1 text-left font-medium">{t("mame.buildEvolvepro.rowReview.colUse")}</th>
            <th className="px-2 py-1 text-left font-medium">{t("mame.buildEvolvepro.rowReview.colFile")}</th>
            <th className="px-2 py-1 text-right font-medium">{t("mame.buildEvolvepro.rowReview.colBlock")}</th>
            <th className="px-2 py-1 text-right font-medium">{t("mame.buildEvolvepro.rowReview.colRow")}</th>
            <th className="px-2 py-1 text-left font-medium">{t("mame.buildEvolvepro.rowReview.colSample")}</th>
            <th className="px-2 py-1 text-right font-medium">{t("mame.buildEvolvepro.rowReview.colArea")}</th>
            <th className="px-2 py-1 text-left font-medium">{t("mame.buildEvolvepro.rowReview.colReason")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = `${row.source}:${row.block_index ?? "-"}:${row.row_index}`;
            const reasonId = `${tableId}-${key}`;
            const toggleable = isToggleable(row);
            const included = toggleable
              ? !isRowExcluded(row, excludedRows)
              : row.status === "locked";
            const reasons = [
              ...(row.reason !== null ? [reasonText(t, row.reason)] : []),
              ...row.flags.map((flag) => reasonText(t, flag)),
              ...(row.status === "locked" ? [t("mame.buildEvolvepro.rowReview.lockedHint")] : []),
            ];
            return (
              <tr
                key={key}
                className={`border-t border-border ${highlight ? "bg-amber-500/10" : ""} ${toggleable && !included ? "text-muted-foreground line-through" : ""}`}
              >
                <td className="px-2 py-1">
                  <input
                    type="checkbox"
                    className="h-4 w-4 cursor-pointer accent-primary disabled:cursor-not-allowed"
                    checked={included}
                    disabled={!toggleable}
                    aria-label={t("mame.buildEvolvepro.rowReview.checkboxLabel", {
                      location: rowLocation(t, row),
                      name: row.sample_name || "-",
                    })}
                    aria-describedby={reasons.length > 0 ? reasonId : undefined}
                    onChange={(event) => onChange(setRowIncluded(excludedRows, row, event.target.checked))}
                  />
                </td>
                <td className="max-w-[10rem] truncate px-2 py-1" title={t(GC_SOURCE_LABEL[row.source])}>
                  {t(GC_SOURCE_LABEL[row.source])}
                </td>
                <td className="px-2 py-1 text-right font-mono">{row.block_index ?? "-"}</td>
                <td className="px-2 py-1 text-right font-mono">{row.row_index}</td>
                <td className="max-w-[8rem] truncate px-2 py-1 font-mono" title={row.sample_name}>
                  {row.sample_name || "-"}
                </td>
                <td className="px-2 py-1 text-right font-mono">{formatArea(row.area)}</td>
                <td id={reasonId} className="min-w-0 px-2 py-1 break-words">
                  {reasons.join("; ")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
