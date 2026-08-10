/**
 * RunQualityNotice, whether this run could have produced a scorable plate.
 *
 * Stands above the verdict table rather than beside the other notices, and only
 * when the answer is no. A campaign was sequenced on a flow cell that started
 * with forty pores and returned four reads per well, and the screen drew a
 * ninety-six-well verdict table over it: nine passes, sixty-nine WRONG_AA, and
 * nothing on the page saying the plate never had the depth to be read. Every
 * cell in that table was equally meaningless, which is not a defect any single
 * cell can show. It is a statement about the run, so it goes where a statement
 * about the run cannot be scrolled past.
 *
 * Blocking is loud, warning is quiet, clean says nothing. The three cases are
 * different claims: blocking means no well cleared the depth its own consensus
 * needs, so the verdicts below are artefacts; warning means the plate is
 * scorable and under-powered, which is worth knowing before the next run and is
 * not a reason to distrust this one.
 *
 * Every number carries where it came from, because the floor is a vendor
 * WORKFLOW DEFAULT rather than a specification and the app should not launder
 * one into the other. See `kuma_core/mame/run_quality.py`.
 */

import { AlertTriangle, Info } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useMameAppStore } from "@/store/mame/mameAppStore"
import { cn } from "@/lib/utils"

/** How many pore-scan readings to name; the first and last are what an operator reads. */
function poreSummary(start: number | null, end: number | null): string | null {
  if (start === null) return null
  return end === null || end === start ? `${start}` : `${start} → ${end}`
}

export function RunQualityNotice() {
  const { t } = useTranslation()
  const runQuality = useMameAppStore((s) => s.runQuality)

  // Nothing to report is the ordinary case and must be silent, or the panel
  // becomes furniture nobody reads. Absent block means an older result.
  if (runQuality === null || runQuality.severity === null) return null

  const blocking = runQuality.severity === "blocking"
  const floor = runQuality.thresholds?.floor
  const pores = poreSummary(runQuality.pore_start, runQuality.pore_end)

  return (
    <div
      role={blocking ? "alert" : "status"}
      data-testid="run-quality-notice"
      data-severity={runQuality.severity}
      className={cn(
        "rounded-control border",
        blocking
          ? "border-destructive/50 bg-destructive/8 px-4 py-3"
          : "border-border bg-muted/40 px-3 py-2",
      )}
    >
      <div className="flex items-start gap-2">
        {blocking ? (
          <AlertTriangle
            size={20}
            className="mt-0.5 flex-shrink-0 text-destructive"
            aria-hidden="true"
          />
        ) : (
          <Info size={16} className="mt-0.5 flex-shrink-0" aria-hidden="true" />
        )}
        <div className="min-w-0 space-y-1">
          <p
            className={cn(
              blocking
                ? "font-display text-body font-semibold text-destructive"
                : "text-caption font-semibold text-foreground",
            )}
          >
            {blocking
              ? t("mame.runQuality.blockingTitle", {
                  median: runQuality.median_well_reads,
                  floor: runQuality.min_read_count,
                })
              : t("mame.runQuality.warningTitle")}
          </p>

          {blocking && (
            <p className="text-caption text-foreground">
              {t("mame.runQuality.blockingBody", {
                under: runQuality.wells_under_floor,
                total: runQuality.wells_total,
              })}
            </p>
          )}

          <ul className="space-y-0.5 text-caption text-muted-foreground">
            {runQuality.findings.map((finding) => (
              <li key={finding.code}>
                {t(`mame.runQuality.finding.${finding.code}`, {
                  median: runQuality.median_well_reads,
                  floor: runQuality.min_read_count,
                  recommended: runQuality.recommended_reads,
                  cell: runQuality.flow_cell_id ?? "",
                  previousPores: runQuality.reused_from?.pore_end ?? "",
                })}
              </li>
            ))}
          </ul>

          {/*
            The provenance line. The floor is a parameter default in a vendor
            workflow this app does not run, so it is labelled as such and as
            provisional; saying "ONT standard" would be an overstatement that
            this project already made once in a code comment.
          */}
          <p className="text-caption text-muted-foreground">
            {t("mame.runQuality.thresholdSource", {
              floor: runQuality.min_read_count,
              recommended: runQuality.recommended_reads,
              source: floor?.source ?? "",
            })}
            {floor?.provisional ? ` ${t("mame.runQuality.provisional")}` : ""}
          </p>

          {pores !== null && (
            <p className="text-caption text-muted-foreground">
              {t("mame.runQuality.pores", {
                cell: runQuality.flow_cell_id ?? "",
                pores,
                warranty: runQuality.pore_warranty_min,
              })}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
