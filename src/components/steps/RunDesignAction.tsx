/**
 * RunDesignAction — primary Run Design button + cancel + missing-field warnings.
 *
 * [source: spec §1 — "DesignStep main area, primary Button"]
 *
 * Uses useRunDesign() hook for validation / preflight / flush / design orchestration.
 * Passes dialog state down to InputSizeWarningDialog and PreflightDialog.
 */

import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/store/appStore";
import { useRunDesign } from "@/hooks/useRunDesign";
import { InputSizeWarningDialog } from "@/components/dialogs/InputSizeWarningDialog";
import { PreflightDialog } from "@/components/dialogs/PreflightDialog";

export function RunDesignAction() {
  const { t } = useTranslation();
  const {
    run,
    isDesigning,
    missingFields,
    hasBlockingIssue,
    sizeWarning,
    setSizeWarning,
    preflightResult,
    setPreflightResult,
  } = useRunDesign();

  const handleCancel = () => {
    useAppStore.getState().cancelDesign();
  };

  return (
    <>
      <div
        className="flex flex-col items-center justify-center gap-4 p-8"
        role="region"
        aria-label={t("phaseC.run.primary")}
      >
        {/* Missing field warnings */}
        {missingFields.length > 0 && !isDesigning && (
          <ul
            className="w-full max-w-sm rounded-md border border-warning/40 bg-warning/8 px-4 py-3 text-sm text-warning"
            role="alert"
            aria-live="polite"
          >
            {missingFields.map((field) => (
              <li key={field} className="list-disc ml-4">
                {field}
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap justify-center gap-2">
          <Button
            className="h-control-primary min-w-[160px] rounded-control text-body font-semibold"
            onClick={run}
            disabled={isDesigning || hasBlockingIssue}
            aria-disabled={isDesigning || hasBlockingIssue}
          >
            {isDesigning ? t("appLayout.designing") : t("phaseC.run.primary")}
          </Button>
          {isDesigning && (
            <Button
              variant="outline"
              className="h-control-primary rounded-control px-3 text-error border-error/40 hover:bg-error/8"
              onClick={handleCancel}
            >
              {t("phaseC.run.cancel")}
            </Button>
          )}
        </div>
      </div>

      {/* §19 Size warning dialog */}
      <InputSizeWarningDialog
        open={sizeWarning !== null}
        level={sizeWarning?.level ?? "warn"}
        message={sizeWarning?.message ?? ""}
        onContinue={() => {
          const action = sizeWarning?.pendingAction;
          setSizeWarning(null);
          action?.();
        }}
        onCancel={() => setSizeWarning(null)}
      />

      {/* §19 Pre-flight dialog */}
      <PreflightDialog
        open={preflightResult !== null}
        result={preflightResult?.result ?? { ok: true, warnings: [], errors: [] }}
        onContinue={() => {
          const action = preflightResult?.pendingAction;
          setPreflightResult(null);
          action?.();
        }}
        onCancel={() => setPreflightResult(null)}
      />
    </>
  );
}
