/**
 * MajorSubnav — 4-tab horizontal subnav for Phase C layout.
 *
 * [source: spec §3.1 — MajorSubnav.tsx]
 *
 * Props:
 *   majors: array of { id, labelKey, countBadge? }
 *
 * - Active tab: border-b-2 border-primary text-foreground font-semibold
 * - Inactive: text-muted-foreground hover:text-foreground
 * - count badge: only rendered when countBadge prop is provided (§14 미정 → v1 hide)
 */

import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/appStore";
import type { MajorStepId } from "@/store/slices/navigationSlice";

export interface MajorNavItem {
  id: MajorStepId;
  labelKey: string;
  /** v1: always undefined (§14 count badge criteria未定). Rendered only when provided. */
  countBadge?: number;
}

interface MajorSubnavProps {
  majors: MajorNavItem[];
}

export function MajorSubnav({ majors }: MajorSubnavProps) {
  const { t } = useTranslation();
  const currentMajor = useAppStore((s) => s.currentMajor);
  const setMajor = useAppStore((s) => s.setMajor);

  return (
    <nav
      className="flex gap-4 px-4 h-10 border-b border-border items-end"
      role="tablist"
      aria-label={t("phaseC.majors.variant")} // generic nav label; individual tabs have aria-selected
    >
      {majors.map((m) => {
        const isActive = m.id === currentMajor;
        return (
          <button
            key={m.id}
            role="tab"
            aria-selected={isActive}
            aria-controls="major-step-main"
            onClick={() => setMajor(m.id)}
            className={cn(
              "flex items-center gap-1.5 pb-2 text-sm transition-colors",
              isActive
                ? "border-b-2 border-primary text-foreground font-semibold pb-px"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <span>{t(m.labelKey)}</span>
            {m.countBadge !== undefined && (
              <span
                className="inline-flex items-center justify-center h-4 min-w-[1rem] rounded-full bg-muted text-muted-foreground text-xs px-1"
                aria-label={String(m.countBadge)}
              >
                {m.countBadge}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
