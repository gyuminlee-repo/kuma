/**
 * CoverageLossNotice, "the run produced results, and also threw a lot away".
 *
 * `EmptyAnalysisNotice` names the coverage gate as a cause only when the run
 * yields nothing at all (`passed_coverage === 0`). A run that scores most wells
 * and silently drops the rest hits none of that: the screen fills with verdicts
 * and the discarded wells look like wells the experiment never produced.
 *
 * That gap is not hypothetical. Comparing MAME against an external pipeline on
 * a 96-well plate, 34 wells returned nothing while holding hundreds of reads
 * each, and the reason was the coverage gate rather than the bench: every
 * alignment stopped a constant ~28 bp short of the reference 3' end, where the
 * reverse primer sits. A constant shortfall against a *fractional* threshold
 * scales with reference length, so short amplicons fail a gate that identical
 * data clears on long ones. Nothing on screen said so.
 *
 * The counters that prove it are already in the analyze response, so this reads
 * them and states the loss. It does not name a fix beyond where the knob lives:
 * the right coverage value depends on the amplicon, and asserting a number here
 * would be guessing.
 */

import { Info } from "lucide-react";
import { useId } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { AnalyzeYield } from "@/types/mame/models";

/**
 * Share of MAPQ-passing reads the coverage gate discarded, or null when the
 * question does not apply.
 *
 * Returns null when a counter is missing, when nothing aligned (that is
 * `EmptyAnalysisNotice` "noAlignment" case), when nothing survived coverage
 * (its "noCoverage" case, which already speaks), or when the loss is below
 * `MIN_REPORTABLE_LOSS`. Some loss is normal, chimeric and partial reads are
 * supposed to be dropped, so a notice on every run would be noise.
 */
export const MIN_REPORTABLE_LOSS = 0.25;

export function diagnoseCoverageLoss(
  analyzeYield: AnalyzeYield | null,
): number | null {
  if (analyzeYield === null) return null;
  const { passed_mapq, passed_coverage } = analyzeYield;
  if (passed_mapq === undefined || passed_coverage === undefined) return null;
  if (passed_mapq <= 0) return null;
  // Both endpoints belong to EmptyAnalysisNotice, which states them with the
  // stronger "this run produced nothing" framing.
  if (passed_coverage <= 0) return null;
  if (passed_coverage > passed_mapq) return null;
  const lost = (passed_mapq - passed_coverage) / passed_mapq;
  return lost >= MIN_REPORTABLE_LOSS ? lost : null;
}

export function CoverageLossNotice() {
  const { t } = useTranslation();
  const analyzeYield = useMameAppStore((s) => s.analyzeYield);
  const titleId = useId();

  const lost = diagnoseCoverageLoss(analyzeYield);
  if (lost === null || analyzeYield === null) return null;

  const passedMapq = analyzeYield.passed_mapq ?? 0;
  const passedCoverage = analyzeYield.passed_coverage ?? 0;

  return (
    <section
      aria-labelledby={titleId}
      className="rounded-control border border-warning/40 bg-warning/10 p-3"
    >
      <div className="flex items-start gap-2">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
        <div className="min-w-0 space-y-1">
          <h3 id={titleId} className="text-caption font-medium">
            {t("mame.analyze.coverageLoss.title", {
              percent: (lost * 100).toFixed(0),
            })}
          </h3>
          <p className="text-caption text-muted-foreground">
            {t("mame.analyze.coverageLoss.body", {
              aligned: passedMapq.toLocaleString(),
              kept: passedCoverage.toLocaleString(),
            })}
          </p>
          <p className="text-caption text-muted-foreground">
            {t("mame.analyze.coverageLoss.hint")}
          </p>
        </div>
      </div>
    </section>
  );
}
