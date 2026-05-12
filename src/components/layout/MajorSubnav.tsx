/**
 * MajorSubnav — horizontal major-step nav for Phase D layout.
 *
 * [source: spec §D3.4 — Clear All 흡수, KuroAppBar 삭제]
 *
 * Props:
 *   majors: array of { id, labelKey, countBadge? }
 *
 * - Active tab: border-b-2 border-primary text-foreground font-semibold
 * - Inactive: text-muted-foreground hover:text-foreground
 * - count badge: only rendered when countBadge prop is provided (§14 미정 → v1 hide)
 * - Clear All button: ml-auto 우측 끝 (KuroAppBar에서 흡수)
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/appStore";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
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
  const isDesigning = useAppStore((s) => s.isDesigning);
  const hasDesignResults = useAppStore((s) => s.designResults.length > 0);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);

  function handleClearAll() {
    if (hasDesignResults) {
      setClearConfirmOpen(true);
    } else {
      useAppStore.getState().resetAll();
    }
  }

  return (
    <>
      <nav
        className="flex items-center gap-4 px-4 h-10 border-b border-border"
        role="tablist"
        aria-label={t("phaseC.majors.design")}
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
                "flex items-center gap-1.5 h-full text-sm transition-colors",
                isActive
                  ? "border-b-2 border-primary text-foreground font-semibold"
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

        <Button
          variant="outline"
          size="sm"
          className="ml-auto h-7 rounded-control text-caption"
          onClick={handleClearAll}
          disabled={isDesigning}
        >
          {t("appLayout.clearAll")}
        </Button>
      </nav>

      <Dialog open={clearConfirmOpen} onOpenChange={setClearConfirmOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("appLayout.clearAll")}</DialogTitle>
            <DialogDescription>{t("appLayout.clearAllDesc")}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setClearConfirmOpen(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-error border-error/40 hover:bg-error/8"
              onClick={() => {
                useAppStore.getState().resetAll();
                setClearConfirmOpen(false);
              }}
            >
              {t("appLayout.clear")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
