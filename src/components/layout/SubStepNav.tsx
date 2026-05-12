/**
 * SubStepNav — vertical sub-step nav-item list with StepBadge.
 *
 * [source: spec §3.2 — SubStepNav.tsx]
 *
 * Each row shows: label + StepBadge (done/active/pending)
 * Badge status:
 *   - stepStatus[id].done  → "done"
 *   - id === currentSubStep → "active"
 *   - else                 → "pending"
 * index = 1-based position in subSteps array
 *
 * §D3.2: store prop 추가. "kuro" (default) | "mame"
 */

import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/appStore";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { StepBadge } from "./StepBadge";
import type { MajorStepId, SubStepId } from "@/store/slices/navigationSlice";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";

export interface SubNavItem {
  id: SubStepId | MameSubStepId;
  labelKey: string;
}

interface SubStepNavProps {
  major: MajorStepId | string;
  subSteps: SubNavItem[];
  /** Store selector: "kuro" uses appStore, "mame" uses mameAppStore. Default: "kuro". */
  store?: "kuro" | "mame";
}

/** kuro store 구독 래퍼 */
function KuroSubStepNav({ subSteps }: { subSteps: SubNavItem[] }) {
  const { t } = useTranslation();
  const currentSubStep = useAppStore((s) => s.currentSubStep);
  const setSubStep = useAppStore((s) => s.setSubStep);
  const stepStatus = useAppStore((s) => s.stepStatus);

  return (
    <nav className="flex flex-col gap-1 p-2" role="navigation" aria-label="sub steps">
      {subSteps.map((step, idx) => {
        const isCurrent = step.id === currentSubStep;
        const isDone = stepStatus[step.id as SubStepId]?.done ?? false;
        const badgeStatus: "done" | "active" | "pending" = isDone
          ? "done"
          : isCurrent
            ? "active"
            : "pending";
        const index = idx + 1;
        return (
          <button
            key={step.id}
            role="tab"
            aria-selected={isCurrent}
            aria-controls="major-step-main"
            data-active={isCurrent}
            onClick={() => setSubStep(step.id as SubStepId)}
            className={cn(
              "flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors text-left",
              "hover:bg-muted/40",
              isCurrent && "bg-muted",
            )}
          >
            <span
              className={cn(
                "flex-1 min-w-0 truncate",
                isCurrent ? "text-foreground font-medium" : "text-muted-foreground",
              )}
            >
              {t(step.labelKey)}
            </span>
            <StepBadge status={badgeStatus} index={index} className="ml-2 shrink-0" />
          </button>
        );
      })}
    </nav>
  );
}

/** mame store 구독 래퍼 */
function MameSubStepNav({ subSteps }: { subSteps: SubNavItem[] }) {
  const { t } = useTranslation();
  const currentSubStep = useMameAppStore((s) => s.currentMameSubStep);
  const setSubStep = useMameAppStore((s) => s.setMameSubStep);

  return (
    <nav className="flex flex-col gap-1 p-2" role="navigation" aria-label="sub steps">
      {subSteps.map((step, idx) => {
        const isCurrent = step.id === currentSubStep;
        // mame stepStatus는 미구현(D4 예정) — done 항상 false
        const badgeStatus: "done" | "active" | "pending" = isCurrent ? "active" : "pending";
        const index = idx + 1;
        return (
          <button
            key={step.id}
            role="tab"
            aria-selected={isCurrent}
            aria-controls="major-step-main"
            data-active={isCurrent}
            onClick={() => setSubStep(step.id as MameSubStepId)}
            className={cn(
              "flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors text-left",
              "hover:bg-muted/40",
              isCurrent && "bg-muted",
            )}
          >
            <span
              className={cn(
                "flex-1 min-w-0 truncate",
                isCurrent ? "text-foreground font-medium" : "text-muted-foreground",
              )}
            >
              {t(step.labelKey)}
            </span>
            <StepBadge status={badgeStatus} index={index} className="ml-2 shrink-0" />
          </button>
        );
      })}
    </nav>
  );
}

export function SubStepNav({ major: _major, subSteps, store = "kuro" }: SubStepNavProps) {
  if (store === "mame") {
    return <MameSubStepNav subSteps={subSteps} />;
  }
  return <KuroSubStepNav subSteps={subSteps} />;
}
