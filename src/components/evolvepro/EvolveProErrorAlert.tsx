import { useTranslation } from "react-i18next";
import type { EvolveProErrorInfo } from "@/store/evolvepro/evolveProStore";

export interface EvolveProErrorAlertProps {
  error: EvolveProErrorInfo;
  onDismiss?: () => void;
}

/**
 * Inline alert (not Toast) for EVOLVEpro errors. Maps error kind to a
 * locale-keyed message and surfaces raw detail. Locale keys follow
 * `evolvePro.error.*` prefix (Wave 1c).
 *
 * Special case: kind === "cancelled" renders a neutral info tone and omits
 * the raw runner message (which would otherwise expose exit-code strings).
 */
export function EvolveProErrorAlert({ error, onDismiss }: EvolveProErrorAlertProps) {
  const { t } = useTranslation();
  const title = t(`evolvePro.error.kind.${error.kind}`, {
    defaultValue: t("evolvePro.error.kind.unknown", { defaultValue: "EVOLVEpro error" }),
  });

  const isCancelled = error.kind === "cancelled";

  return (
    <div
      role="status"
      aria-live="polite"
      className={
        isCancelled
          ? "rounded-lg border border-border bg-muted/50 p-3 text-sm text-foreground"
          : "rounded-lg border border-error/50 bg-error/10 p-3 text-sm text-foreground"
      }
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className={isCancelled ? "font-medium text-muted-foreground" : "font-medium text-error"}>
            {title}
          </div>
          {!isCancelled && error.message ? (
            <div className="mt-1 break-words text-muted-foreground">{error.message}</div>
          ) : null}
        </div>
        {onDismiss ? (
          <button
            type="button"
            className="shrink-0 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={onDismiss}
            aria-label={t("evolvePro.error.dismiss", { defaultValue: "Dismiss" })}
          >
            ×
          </button>
        ) : null}
      </div>
    </div>
  );
}
