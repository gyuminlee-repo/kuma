/**
 * ReplicateModeNotice, "this run covers fewer replicates than the folder holds".
 *
 * A run folder can hold several native barcodes, and a native barcode is a
 * replicate of the one plate this run scores (kuma_core/mame/pipeline.py groups
 * by native_barcode and calls pick_best_replicate on each group). Analyzing one
 * of them, or pooling all of them into a single plate, is a legitimate answer.
 * What is not obvious afterwards is that the answer was given at all: the review
 * screen shows one plate tab and no trace of the copies left out, so a result
 * scored on one replicate looks exactly like a run of a single-barcode folder.
 *
 * The trigger is therefore the comparison, not the mode: it fires when the
 * detect step counted MORE native barcodes than the run ended up scoring as
 * replicates. Keying on "pooled" alone would miss the case that actually loses
 * information (three barcodes detected, one ticked) while firing on a pooled
 * run of a single-barcode folder, where nothing was left out.
 *
 * Informational, never gating. Both readings are valid experiments, and the
 * program has no ground to refuse either. It disappears with the results it
 * describes: `clearResults` drops both store fields back to null.
 */

import { Layers } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";

export function ReplicateModeNotice() {
  const { t } = useTranslation();
  const detectedCount = useMameAppStore((s) => s.detectedBarcodeCount);
  const selected = useMameAppStore((s) => s.selectedNativeBarcodes);

  if (detectedCount === null || selected === null) return null;
  // `[]` means pooled: every read in one pool, so one plate and no replicate
  // axis. A non-empty selection scores one replicate per listed barcode.
  const pooled = selected.length === 0;
  const replicateCount = pooled ? 1 : selected.length;
  if (detectedCount <= replicateCount) return null;

  return (
    <div
      data-testid="replicate-mode-notice"
      data-mode={pooled ? "pooled" : "subset"}
      data-detected={detectedCount}
      data-replicates={replicateCount}
      role="status"
      className="flex items-start gap-2 rounded-control border border-border bg-muted/40 px-2.5 py-1.5"
    >
      <Layers size={12} className="mt-0.5 flex-shrink-0 text-muted-foreground" aria-hidden="true" />
      <p className="min-w-0 break-words text-caption text-muted-foreground">
        {pooled
          ? t("mame.replicateModeNotice.pooled", { detected: detectedCount })
          : t("mame.replicateModeNotice.subset", {
              detected: detectedCount,
              replicates: replicateCount,
            })}
      </p>
    </div>
  );
}
