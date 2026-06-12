/**
 * WizardContainer — wizard step 레이아웃 wrapper.
 *
 * Provides:
 *   - Step heading (Step N: <label>) — fixed slot above scroll area
 *   - 1-line description (optional)
 *   - Scrollable children area
 *   - Footer: "Step N / Total" indicator + Back/Next buttons
 *
 * Layout: heading (flex-shrink-0) / body (flex-1 overflow-auto) / footer (flex-shrink-0).
 * Heading는 children scroll 영역 밖에 고정되어, 모든 사용처에서 동일 Y좌표를 보장한다.
 *
 * [source: spec Phase E — E2 WizardContainer]
 * [source: spec Phase G — #4 maxWidth prop, #3 validation guard]
 */

import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

/** Controls max-width of the scrollable body area. Defaults to "3xl". "full" = no max-width constraint (Output step). */
type MaxWidth = "3xl" | "4xl" | "5xl" | "full";

const MAX_WIDTH_CLASS: Record<MaxWidth, string> = {
  "3xl": "max-w-3xl",
  "4xl": "max-w-4xl",
  "5xl": "max-w-5xl",
  "full": "",
};

const MAX_WIDTH_ALIGN_CLASS: Record<MaxWidth, string> = {
  "3xl": "mr-auto",
  "4xl": "mr-auto",
  "5xl": "mr-auto",
  "full": "",
};

export interface WizardContainerProps {
  stepIndex: number;
  stepTotal: number;
  /**
   * Optional display-only step label override. When provided, header renders
   * `Step {stepLabel}: {title}` instead of `Step {stepIndex}: {title}`.
   * Used by MAME wizard to present Major.Sub numbering (e.g. "1.1", "2.3").
   * KURO callers omit this and continue to use `stepIndex` directly.
   */
  stepLabel?: string;
  /**
   * Optional display-only progress label override. When provided, replaces
   * the default `Step {current} / {total}` footer text. Used by MAME wizard
   * to present sub-step progress within a major group (e.g. "1.1 / 1.2").
   */
  progressLabel?: string;
  titleKey: string;
  descriptionKey?: string;
  onNext?: () => void;
  onPrev?: () => void;
  nextLabelKey?: string;
  /**
   * children 영역의 최대 너비. default "3xl".
   * 사용처별 권장:
   *   - design.* → "3xl" (default)
   *   - output.summary → "full"
   *   - export.all → "4xl"
   *   - mame Run Setup → "3xl", mame Sequencing QC → "4xl", mame Activity Data → "3xl"
   */
  maxWidth?: MaxWidth;
  /**
   * Next 버튼 활성 상태 제어.
   * false 반환 시 Next 버튼 disabled.
   */
  isValid?: () => boolean;
  /**
   * Next 버튼 클릭 직전 프리플라이트 검사.
   * { ok: false, missing: string[] } 반환 시 missing 항목을 나열한 Dialog를 표시.
   * undefined이면 검사 생략.
   */
  validateBeforeNext?: () => { ok: boolean; missing?: string[] };
  children: ReactNode;
}

export function WizardContainer({
  stepIndex,
  stepTotal,
  stepLabel,
  progressLabel,
  titleKey,
  descriptionKey,
  onNext,
  onPrev,
  nextLabelKey,
  maxWidth = "3xl",
  isValid,
  validateBeforeNext,
  children,
}: WizardContainerProps) {
  const { t } = useTranslation();
  const [validationOpen, setValidationOpen] = useState(false);
  const [missingItems, setMissingItems] = useState<string[]>([]);

  const nextDisabled = isValid ? !isValid() : false;

  function handleNextClick() {
    if (validateBeforeNext) {
      const result = validateBeforeNext();
      if (!result.ok) {
        setMissingItems(result.missing ?? []);
        setValidationOpen(true);
        return;
      }
    }
    onNext?.();
  }

  return (
    <>
      <div className="flex flex-col h-full" data-testid="wizard-container">
        {/* heading: flex-shrink-0으로 scroll 영역 밖 고정 — 모든 사용처에서 동일 Y좌표 보장 */}
        <header
          className="flex-shrink-0 border-b border-border bg-background px-6 py-3 space-y-0.5"
          data-testid="wizard-header"
        >
          <h2 className="text-xl font-semibold text-foreground">
            {t("phaseE.wizard.stepLabel", { n: stepLabel ?? stepIndex })}: {t(titleKey)}
          </h2>
          {descriptionKey && (
            <p className="text-sm text-muted-foreground">
              {t(descriptionKey)}
            </p>
          )}
        </header>
        {/* children: 고정 heading/footer 사이의 scrollable 영역. maxWidth는 body에 적용 */}
        <div
          className={`flex-1 overflow-auto px-6 py-4 w-full ${MAX_WIDTH_ALIGN_CLASS[maxWidth]} ${MAX_WIDTH_CLASS[maxWidth]}`}
          data-testid="wizard-body"
        >
          {children}
        </div>
        <footer
          className="flex-shrink-0 border-t border-border bg-muted/20 px-6 h-12 flex items-center justify-between"
          aria-label={
            progressLabel ??
            t("phaseE.wizard.progress", {
              current: stepIndex,
              total: stepTotal,
            })
          }
        >
          <div className="text-xs text-muted-foreground">
            {progressLabel ??
              t("phaseE.wizard.progress", {
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
                onClick={handleNextClick}
                disabled={nextDisabled}
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

      {/* Validation guard dialog: validateBeforeNext가 { ok: false } 반환 시 표시 */}
      <Dialog open={validationOpen} onOpenChange={setValidationOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("wizardContainer.validationDialog.title")}</DialogTitle>
            <DialogDescription>
              {t("wizardContainer.validationDialog.description")}
            </DialogDescription>
          </DialogHeader>
          {missingItems.length > 0 && (
            <ul
              className="text-sm text-foreground space-y-1 list-disc pl-5"
              aria-label={t("wizardContainer.validationDialog.missingItemsLabel")}
            >
              {missingItems.map((item) => (
                <li key={item}>{t(item)}</li>
              ))}
            </ul>
          )}
          <DialogFooter>
            <Button size="sm" onClick={() => setValidationOpen(false)}>
              {t("common.ok")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
