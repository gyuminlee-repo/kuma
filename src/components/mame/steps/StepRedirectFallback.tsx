/**
 * StepRedirectFallback — sub-step mismatch fallback.
 *
 * [source: spec #12 — sidebar에서 현재 major 외 sub-step 클릭 시 빈 창 방지]
 *
 * 각 StepView (Setup/Analyze/Activity) 의 switch default 분기에서 사용한다.
 * 마운트 시 expectedFor major 의 첫 sub-step 으로 자동 보정하고
 * 보정 진행 중 i18n status 메시지를 표시한다.
 */

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";

type MameMajor = "setup" | "analyze" | "activity";

const FIRST_SUB: Record<MameMajor, MameSubStepId> = {
  setup: "setup.files",
  analyze: "analyze.inputs",
  activity: "activity.ingest",
};

export interface StepRedirectFallbackProps {
  currentSub: MameSubStepId;
  expectedFor: MameMajor;
  setSubStep: (id: MameSubStepId) => void;
}

export function StepRedirectFallback({
  currentSub,
  expectedFor,
  setSubStep,
}: StepRedirectFallbackProps) {
  const { t } = useTranslation();
  const target = FIRST_SUB[expectedFor];

  useEffect(() => {
    if (currentSub === target) return;
    // setTimeout(0)으로 render cycle 분리 → React state-update-in-render 경고 회피
    const handle = setTimeout(() => {
      setSubStep(target);
    }, 0);
    return () => clearTimeout(handle);
  }, [currentSub, target, setSubStep]);

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex h-full items-center justify-center p-6 text-caption text-muted-foreground"
    >
      {t("phaseC.mameSubSteps.fallback.redirecting")}
    </div>
  );
}
