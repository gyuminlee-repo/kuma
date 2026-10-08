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
 * field `detectedNativeBarcodes` is non-null.
 *
 * What this dialog decides is the REPLICATE AXIS of the run, which is why it
 * says so instead of asking which folders to demultiplex. A run has one plate
 * layout and it applies to every native barcode, so the barcodes ticked here
 * become the plate copies of one plate: `kuma_core/mame/pipeline.py` groups the
 * records by `native_barcode` and hands each group to `pick_best_replicate`,
 * which picks one copy per variant. Ticking one barcode is a legitimate answer
 * (one plate, no replicates); it is not a way to analyze "just part of" a run.
 *
 * Three outcomes, and all three are stated rather than implied:
 *   - per-barcode  → the ticked barcodes become replicates
 *   - pooled       → every read in one pool, one plate, no replicate axis.
 *                    Promoted to a radio because a folder holding two or more
 *                    native barcodes had no way to state it: this dialog opens
 *                    on exactly that folder, its confirm returned early on an
 *                    empty selection, and cancelling aborted the run instead of
 *                    pooling it. Pooling was reachable only for a folder with
 *                    one barcode or none, where the dialog never opens.
 *   - cancel       → the analysis stops. The X button and Escape both route
 *                    here (`close` → `cancelNativeBarcodeSelection`), which
 *                    clears `isAnalyzing` and leaves nothing running.
 *
 * Scientific terms (replicate, plate, barcode, sort_barcode, FASTQ, MB) stay
 * English; only natural-language UI strings are localized.
 */
export function NativeBarcodeConfirmDialog() {
  const { t } = useTranslation();
  const detected = useMameAppStore((s) => s.detectedNativeBarcodes);
  const confirmSelection = useMameAppStore((s) => s.confirmNativeBarcodeSelection);
  const cancelSelection = useMameAppStore((s) => s.cancelNativeBarcodeSelection);

  const open = detected !== null;

  // Local selection state, seeded from is_used whenever the dialog (re)opens.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<"per_barcode" | "pooled">("per_barcode");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!detected) return;
    setSelected(new Set(detected.filter((nb) => nb.is_used).map((nb) => nb.name)));
    setMode("per_barcode");
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

  /** X button, Escape, and the Cancel button. Stops the pending analysis. */
  function close() {
    cancelSelection();
  }

  const perBarcode = mode === "per_barcode";
  const confirmDisabled = submitting || (perBarcode && selected.size === 0);

  async function confirm() {
    if (confirmDisabled) return;
    setSubmitting(true);
    // Preserve detect order (sorted by fastq_bytes desc) in the selection. The
    // pooled answer sends an empty list, which the store reads as "one pool".
    const names = perBarcode
      ? (detected ?? []).map((nb) => nb.name).filter((name) => selected.has(name))
      : [];
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
          <fieldset className="space-y-2" data-testid="replicate-mode-choice">
            <legend className="sr-only">{t("mame.nativeBarcodeDialog.modeLegend")}</legend>
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="radio"
                name="nb-replicate-mode"
                value="per_barcode"
                checked={perBarcode}
                onChange={() => setMode("per_barcode")}
                className="mt-0.5 h-4 w-4 accent-primary"
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">
                  {t("mame.nativeBarcodeDialog.modePerBarcode")}
                </span>
                <span className="block text-caption text-muted-foreground">
                  {t("mame.nativeBarcodeDialog.modePerBarcodeHelp")}
                </span>
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="radio"
                name="nb-replicate-mode"
                value="pooled"
                checked={!perBarcode}
                onChange={() => setMode("pooled")}
                className="mt-0.5 h-4 w-4 accent-primary"
              />
              <span className="min-w-0">
                <span className="block text-sm font-medium text-foreground">
                  {t("mame.nativeBarcodeDialog.modePooled")}
                </span>
                <span className="block text-caption text-muted-foreground">
                  {t("mame.nativeBarcodeDialog.modePooledHelp")}
                </span>
              </span>
            </label>
          </fieldset>

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

          <ul className={perBarcode ? "space-y-1.5" : "space-y-1.5 opacity-50"}>
            {(detected ?? []).map((nb) => {
              const checkboxId = `nb-${nb.name}`;
              const checked = perBarcode && selected.has(nb.name);
              return (
                <li
                  key={nb.name}
                  className="grid grid-cols-[auto_1fr_1fr_auto_auto] items-center gap-x-3 rounded-control border border-border px-3 py-2"
                >
                  <input
                    id={checkboxId}
                    type="checkbox"
                    checked={checked}
                    disabled={!perBarcode}
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

          <p className="text-caption text-muted-foreground" data-testid="replicate-count-line">
            {perBarcode
              ? t("mame.nativeBarcodeDialog.replicateCount", { count: selected.size })
              : t("mame.nativeBarcodeDialog.pooledCount", { count: detected?.length ?? 0 })}
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={close} disabled={submitting}>
            {t("mame.nativeBarcodeDialog.cancel")}
          </Button>
          <Button
            size="sm"
            className="gap-2"
            onClick={() => void confirm()}
            disabled={confirmDisabled}
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
