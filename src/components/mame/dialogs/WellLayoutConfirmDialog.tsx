import { useEffect, useState } from "react";
import { LayoutGrid } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { WellLayoutRow } from "@/types/mame/well_layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Store-driven confirm dialog for the well-layout build -> confirm flow.
 * Mounted bare in MameAppLayout. Visible iff `wellLayoutDraft` is non-null.
 *
 * Draft rows from mame.build_well_layout are pre-filled; every row's sample
 * field is editable (including the WT control well). Confirm converts the
 * table to a well->sample Record and stores it for analyze.
 *
 * Scientific terms (well, WT, KURO xlsx) stay English; natural-language UI
 * strings are localized.
 */
export function WellLayoutConfirmDialog() {
  const { t } = useTranslation();
  const draft = useMameAppStore((s) => s.wellLayoutDraft);
  const confirmWellLayout = useMameAppStore((s) => s.confirmWellLayout);
  const cancelWellLayout = useMameAppStore((s) => s.cancelWellLayout);

  const open = draft !== null;

  // Local editable rows, seeded from draft whenever the dialog (re)opens.
  const [rows, setRows] = useState<WellLayoutRow[]>([]);

  useEffect(() => {
    if (!draft) return;
    setRows(draft.map((r) => ({ well: r.well, sample: r.sample })));
  }, [draft]);

  function updateSample(index: number, sample: string) {
    setRows((prev) =>
      prev.map((r, i) => (i === index ? { well: r.well, sample } : r)),
    );
  }

  function handleConfirm() {
    confirmWellLayout(rows);
  }

  function handleClose() {
    cancelWellLayout();
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && handleClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("mame.wellLayoutDialog.title")}</DialogTitle>
          <DialogDescription>{t("mame.wellLayoutDialog.description")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-caption text-muted-foreground">
            {t("mame.wellLayoutDialog.hint")}
          </p>

          {/* Column headers */}
          <div
            className="grid grid-cols-[80px_1fr] gap-x-3 px-3 text-caption font-medium text-muted-foreground"
            aria-hidden="true"
          >
            <span>well</span>
            <span>sample</span>
          </div>

          {rows.length === 0 ? (
            <p className="px-3 py-6 text-center text-caption text-muted-foreground">
              {t("mame.wellLayoutDialog.empty")}
            </p>
          ) : (
            <ul
              className="max-h-80 overflow-y-auto space-y-1"
              aria-label={t("mame.wellLayoutDialog.tableAriaLabel")}
            >
              {rows.map((row, index) => {
                const isWt = row.sample === "WT";
                const inputId = `well-row-${row.well}`;
                return (
                  <li
                    key={row.well}
                    className={`grid grid-cols-[80px_1fr] items-center gap-x-3 rounded-control border px-3 py-1.5 ${
                      isWt ? "border-primary/40 bg-primary/5" : "border-border"
                    }`}
                  >
                    <label
                      htmlFor={inputId}
                      className="font-mono text-sm text-foreground select-none"
                    >
                      {row.well}
                      {isWt && (
                        <span className="ml-1.5 rounded px-1 py-0.5 text-caption bg-primary/15 text-primary font-medium">
                          WT
                        </span>
                      )}
                    </label>
                    <Input
                      id={inputId}
                      value={row.sample}
                      onChange={(e) => updateSample(index, e.target.value)}
                      className="h-7 min-w-0 text-xs font-mono"
                      aria-label={t("mame.wellLayoutDialog.sampleAriaLabel", {
                        well: row.well,
                      })}
                    />
                  </li>
                );
              })}
            </ul>
          )}

          <p className="text-caption text-muted-foreground">
            {t("mame.wellLayoutDialog.rowCount", { count: rows.length })}
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={handleClose}>
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            className="gap-2"
            onClick={handleConfirm}
            disabled={rows.length === 0}
          >
            <LayoutGrid size={14} aria-hidden="true" />
            {t("mame.wellLayoutDialog.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
