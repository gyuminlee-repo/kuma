/**
 * MappingIntegrityAlert, whole-run well/variant mapping sanity warning.
 *
 * Surfaces `mapping_integrity.suspect` from the last analyze response
 * (`kuma_core/mame/qc/mapping_integrity.py`). This is the post-hoc signal for
 * the 2026-08 incident: every well individually classified fine against
 * whatever expected set it was scoped to, and only comparing observed changes
 * across the whole plate exposed a systematic well<->variant swap. Unlike
 * `PlateClusterAlert` (a soft, collapsible heads-up about clustered failures),
 * this is a loud, always-expanded warning: the run already finished, but the
 * operator must be told not to trust it before acting on it.
 *
 * Never blocks anything -- this is a judgment about a result that already
 * exists, not a run gate.
 */

import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

/** Fraction (0..1) -> whole-number percent string for interpolation. */
function toPercent(rate: number): string {
  return (rate * 100).toFixed(1);
}

export function MappingIntegrityAlert() {
  const { t } = useTranslation();
  const mappingIntegrity = useMameAppStore((s) => s.mappingIntegrity);

  if (mappingIntegrity === null || !mappingIntegrity.suspect) return null;

  return (
    <div
      role="alert"
      aria-label={t("mame.qc.mappingIntegrity.alertAriaLabel")}
      data-testid="mapping-integrity-alert"
      className="flex items-start gap-2 rounded-control border border-error/60 bg-error/10 px-3 py-2 text-caption"
    >
      <AlertTriangle
        size={16}
        className="mt-0.5 flex-shrink-0 text-error"
        aria-hidden="true"
      />
      <div className="min-w-0 space-y-0.5">
        <p className="font-semibold text-error">
          {t("mame.qc.mappingIntegrity.alertTitle")}
        </p>
        <p className="text-foreground">
          {t("mame.qc.mappingIntegrity.alertDesc", {
            wells: mappingIntegrity.wells_considered,
            selfPercent: toPercent(mappingIntegrity.self_rate),
            crossPercent: toPercent(mappingIntegrity.cross_rate),
          })}
        </p>
      </div>
    </div>
  );
}
