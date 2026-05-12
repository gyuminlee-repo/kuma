/**
 * KuroAppBar — kuro tool application bar (appbar slot in AppShell).
 *
 * Contains: Clear All button (moved from sidebar footer per spec §9).
 * Rendered between MenuBar (titlebar) and MajorSubnav (subnav).
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
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

export function KuroAppBar() {
  const { t } = useTranslation();
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
      <div
        className="flex items-center justify-end gap-2 border-b border-border bg-muted/20 px-3 py-1.5"
        role="toolbar"
        aria-label={t("appLayout.toolbarAriaLabel", "Kuro toolbar")}
      >
        <Button
          variant="outline"
          size="sm"
          className="h-7 rounded-control text-caption"
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
