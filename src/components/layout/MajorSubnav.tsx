/**
 * MajorSubnav — horizontal major-step nav for Phase F layout.
 *
 * [source: spec Phase F — F4 shadcn TabsList 통일]
 *
 * Props:
 *   majors: array of { id, labelKey, countBadge? }
 *
 * Layout: outer flex row (border-b) contains:
 *   - <Tabs> + <TabsList> (shadcn) for tab switching
 *   - Clear All button (ml-auto, outside TabsList)
 *
 * Accessibility: Radix Tabs primitives provide role=tablist / role=tab /
 *   aria-selected natively.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
      <div className="flex items-center border-b border-border px-3 pt-2 pb-0">
        <Tabs
          value={currentMajor}
          onValueChange={(v) => setMajor(v as MajorStepId)}
        >
          <TabsList className="shrink-0 w-fit h-9 gap-0 bg-transparent p-0 rounded-none">
            {majors.map((m) => (
              <TabsTrigger
                key={m.id}
                value={m.id}
                className="relative flex items-center gap-1.5 rounded-none border-b-2 border-transparent px-3 py-1.5 text-sm data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:text-foreground data-[state=inactive]:text-muted-foreground"
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
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <Button
          variant="outline"
          size="sm"
          className="ml-auto h-7 rounded-control text-caption"
          onClick={handleClearAll}
          disabled={isDesigning}
        >
          {t("appLayout.clearAll")}
        </Button>
      </div>

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
