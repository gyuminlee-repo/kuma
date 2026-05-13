/**
 * WizardContainer — wizard step 레이아웃 wrapper.
 *
 * Provides:
 *   - Step heading (Step N: <label>)
 *   - 1-line description (optional)
 *   - Scrollable children area
 *   - Footer: "Step N / Total" indicator + Back/Next buttons
 *
 * [source: spec Phase E — E2 WizardContainer]
 */

import { type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

interface WizardContainerProps {
  stepIndex: number;
  stepTotal: number;
  titleKey: string;
  descriptionKey?: string;
  onNext?: () => void;
  onPrev?: () => void;
  nextLabelKey?: string;
  children: ReactNode;
}

export function WizardContainer({
  stepIndex,
  stepTotal,
  titleKey,
  descriptionKey,
  onNext,
  onPrev,
  nextLabelKey,
  children,
}: WizardContainerProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col h-full" data-testid="wizard-container">
      <div className="flex-1 overflow-auto">
        <div className="content-card max-w-3xl mx-auto p-6 space-y-4">
          <header className="space-y-1">
            <h2 className="text-xl font-semibold text-foreground">
              {t("phaseE.wizard.stepLabel", { n: stepIndex })}: {t(titleKey)}
            </h2>
            {descriptionKey && (
              <p className="text-sm text-muted-foreground">
                {t(descriptionKey)}
              </p>
            )}
          </header>
          <div>{children}</div>
        </div>
      </div>
      <footer
        className="flex-shrink-0 border-t border-border bg-muted/20 px-6 h-12 flex items-center justify-between"
        aria-label={t("phaseE.wizard.progress", {
          current: stepIndex,
          total: stepTotal,
        })}
      >
        <div className="text-xs text-muted-foreground">
          {t("phaseE.wizard.progress", {
            current: stepIndex,
            total: stepTotal,
          })}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onPrev}
            disabled={!onPrev}
            aria-label={t("phaseE.wizard.back")}
          >
            {t("phaseE.wizard.back")}
          </Button>
          {onNext !== undefined && (
            <Button
              size="sm"
              onClick={onNext}
              aria-label={
                nextLabelKey ? t(nextLabelKey) : t("phaseE.wizard.next")
              }
            >
              {nextLabelKey ? t(nextLabelKey) : t("phaseE.wizard.next")}
            </Button>
          )}
        </div>
      </footer>
    </div>
  );
}
