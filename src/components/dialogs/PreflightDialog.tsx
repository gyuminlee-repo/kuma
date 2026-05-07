/**
 * §19 Performance Guardrails — Pre-flight check result dialog
 *
 * Shows errors (red) and warnings (yellow) from runPreflightCheck().
 * When errors are present the continue button uses a warning-tinted style
 * (mirrors InputSizeWarningDialog "block" level pattern).
 * "Continue with warnings" proceeds; "Cancel" aborts the run.
 */

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";
import type { PreflightResult } from "@/lib/preflight";

interface PreflightDialogProps {
  open: boolean;
  result: PreflightResult;
  onContinue: () => void;
  onCancel: () => void;
}

export function PreflightDialog({
  open,
  result,
  onContinue,
  onCancel,
}: PreflightDialogProps) {
  const hasErrors = result.errors.length > 0;
  const hasWarnings = result.warnings.length > 0;

  const title = hasErrors
    ? "Pre-flight check failed"
    : "Pre-flight check — warnings";

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onCancel();
      }}
    >
      <DialogContent
        className="max-w-md"
        role="alertdialog"
        aria-modal="true"
        aria-live="assertive"
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {hasErrors
              ? "The following issues must be resolved before running."
              : "Review the following before continuing."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          {hasErrors && (
            <section aria-label="Errors">
              <ul className="space-y-1" role="list">
                {result.errors.map((msg) => (
                  <li
                    key={msg}
                    className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 text-destructive"
                  >
                    <span aria-hidden="true" className="mt-0.5 shrink-0">
                      ✕
                    </span>
                    <span>{msg}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {hasWarnings && (
            <section aria-label="Warnings">
              <ul className="space-y-1" role="list">
                {result.warnings.map((msg) => (
                  <li
                    key={msg}
                    className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/8 px-3 py-2 text-warning-foreground"
                  >
                    <span aria-hidden="true" className="mt-0.5 shrink-0">
                      ⚠
                    </span>
                    <span>{msg}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <DialogFooter className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-warning border-warning/40 hover:bg-warning/8"
            onClick={onContinue}
          >
            Continue with warnings
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
