import { CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatRunDuration } from "@/lib/mame/runDuration";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Completion popup for the MAME step 2.1 analysis run: states how long the run
 * took once it finishes.
 *
 * Props-driven rather than store-driven, because "has been shown for this run"
 * is view state: the store only knows the duration of the last completed run
 * and would re-open the dialog on every remount. AnalyzeStepView owns the
 * null -> number edge and clears `durationMs` on close.
 *
 * Esc, overlay click and the Close button all dismiss it (Radix Dialog).
 */
export interface AnalyzeDurationDialogProps {
  /** Elapsed wall-clock milliseconds of the finished run; null = closed. */
  durationMs: number | null;
  onClose: () => void;
}

export function AnalyzeDurationDialog({ durationMs, onClose }: AnalyzeDurationDialogProps) {
  const { t } = useTranslation();
  const open = durationMs !== null;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-sm" data-testid="analyze-duration-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CheckCircle2 size={18} className="text-success" aria-hidden="true" />
            {t("mame.analyze.durationDialog.title")}
          </DialogTitle>
          <DialogDescription>
            {t("mame.analyze.durationDialog.description")}
          </DialogDescription>
        </DialogHeader>

        <p className="flex items-baseline gap-2 text-body">
          <span className="text-muted-foreground">
            {t("mame.analyze.durationDialog.elapsedLabel")}
          </span>
          <span
            className="min-w-0 font-medium tabular-nums text-foreground"
            data-testid="analyze-duration-value"
          >
            {durationMs !== null ? formatRunDuration(durationMs, t) : ""}
          </span>
        </p>

        <DialogFooter>
          <Button size="sm" onClick={onClose}>
            {t("common.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
