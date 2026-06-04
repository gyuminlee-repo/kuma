import { useEffect, useState } from "react";
import { Layers } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

/**
 * Store-driven confirm dialog for the native-barcode detect -> confirm -> per-NB
 * demux flow. Mounted bare (no props) in MameAppLayout. Visible iff the store
 * field `detectedNativeBarcodes` is non-null. Pre-selects the is_used barcodes;
 * confirm resumes per-NB demux+analyze with the selected MinKNOW dir names.
 *
 * Scientific terms (barcode, sort_barcode, FASTQ, MB) stay English; only
 * natural-language UI strings are localized.
 */
export function NativeBarcodeConfirmDialog() {
  const { t } = useTranslation();
  const detected = useMameAppStore((s) => s.detectedNativeBarcodes);
  const confirmSelection = useMameAppStore((s) => s.confirmNativeBarcodeSelection);
  const cancelSelection = useMameAppStore((s) => s.cancelNativeBarcodeSelection);

  const open = detected !== null;

  // Local selection state, seeded from is_used whenever the dialog (re)opens.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!detected) return;
    setSelected(new Set(detected.filter((nb) => nb.is_used).map((nb) => nb.name)));
    setSubmitting(false);
  }, [detected]);

  function toggle(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function close() {
    cancelSelection();
  }

  async function confirm() {
    if (selected.size === 0 || submitting) return;
    setSubmitting(true);
    // Preserve detect order (sorted by fastq_bytes desc) in the selection.
    const names = (detected ?? [])
      .map((nb) => nb.name)
      .filter((name) => selected.has(name));
    await confirmSelection(names);
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("mame.nativeBarcodeDialog.title")}</DialogTitle>
          <DialogDescription>{t("mame.nativeBarcodeDialog.description")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div
            className="grid grid-cols-[auto_1fr_1fr_auto_auto] items-center gap-x-3 gap-y-1 px-1 text-caption font-medium text-muted-foreground"
            aria-hidden="true"
          >
            <span />
            <span>barcode</span>
            <span>sort_barcode</span>
            <span className="text-right">FASTQ (MB)</span>
            <span className="text-right">{t("mame.nativeBarcodeDialog.shareHeader")}</span>
          </div>

          <ul className="space-y-1.5">
            {(detected ?? []).map((nb) => {
              const checkboxId = `nb-${nb.name}`;
              const checked = selected.has(nb.name);
              return (
                <li
                  key={nb.name}
                  className="grid grid-cols-[auto_1fr_1fr_auto_auto] items-center gap-x-3 rounded-control border border-border px-3 py-2"
                >
                  <input
                    id={checkboxId}
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(nb.name)}
                    className="h-4 w-4 accent-primary"
                    aria-label={t("mame.nativeBarcodeDialog.selectAriaLabel", { name: nb.name })}
                  />
                  <Label htmlFor={checkboxId} className="font-mono text-sm text-foreground">
                    {nb.name}
                  </Label>
                  <span className="font-mono text-sm text-muted-foreground">
                    {nb.sort_barcode_name}
                  </span>
                  <span className="text-right text-sm tabular-nums text-foreground">
                    {nb.fastq_mb.toFixed(1)}
                  </span>
                  <span className="text-right text-sm tabular-nums text-muted-foreground">
                    {(nb.share * 100).toFixed(1)}%
                  </span>
                </li>
              );
            })}
          </ul>

          <p className="text-caption text-muted-foreground">
            {t("mame.nativeBarcodeDialog.selectedCount", { count: selected.size })}
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={close} disabled={submitting}>
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            className="gap-2"
            onClick={() => void confirm()}
            disabled={selected.size === 0 || submitting}
          >
            <Layers size={14} aria-hidden="true" />
            {submitting
              ? t("mame.nativeBarcodeDialog.confirming")
              : t("mame.nativeBarcodeDialog.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
