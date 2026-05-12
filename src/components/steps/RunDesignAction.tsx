/**
 * RunDesignAction — primary Run Design button + cancel.
 *
 * [source: spec §1 — "DesignStep main area, primary Button"]
 *
 * Stage 2: minimal implementation — isDesigning + designPrimers() + cancelDesign().
 * Full validation/preflight wiring (collectMissingFields, checkKuroInputSize,
 * runPreflightCheck, flushBeforeDesign) is extracted in Stage 3 alongside
 * AppLayout refactoring, as a shared useRunDesign() hook.
 *
 * TODO Stage 3: replace inline designPrimers() call with useRunDesign() hook
 *   that mirrors AppLayout.tsx tryRunDesign (lines 132–176).
 */

import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/store/appStore";

export function RunDesignAction() {
  const { t } = useTranslation();
  const isDesigning = useAppStore((s) => s.isDesigning);
  const designPrimers = useAppStore((s) => s.designPrimers);

  const handleRun = () => {
    if (isDesigning) return;
    void designPrimers();
  };

  const handleCancel = () => {
    useAppStore.getState().cancelDesign();
  };

  return (
    <div
      className="flex flex-col items-center justify-center gap-4 p-8"
      role="region"
      aria-label={t("phaseC.run.primary")}
    >
      <div className="flex gap-2">
        <Button
          className="h-control-primary min-w-[160px] rounded-control text-body font-semibold"
          onClick={handleRun}
          disabled={isDesigning}
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
      <p className="text-xs text-muted-foreground">
        {/* Stage 3: show missing field warnings here via useRunDesign() hook */}
      </p>
    </div>
  );
}
