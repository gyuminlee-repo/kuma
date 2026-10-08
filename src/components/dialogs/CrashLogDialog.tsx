import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { getCrashLog, type CrashEntry } from "../../lib/crashLog";

interface CrashLogDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function formatEntry(e: CrashEntry): string {
  return `[${e.timestamp}] ${e.component}: ${e.message}${e.stack ? "\n" + e.stack : ""}`;
}

export function CrashLogDialog({ open, onOpenChange }: CrashLogDialogProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const log = getCrashLog();
  const text = log.length > 0 ? log.map(formatEntry).join("\n---\n") : "(no crash entries)";

  async function handleCopy() {
    if (log.length === 0) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) setCopied(false);
    onOpenChange(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("crashLog.title")}</DialogTitle>
          <DialogDescription>
            {log.length > 0 ? t("crashLog.descEntries", { count: log.length }) : t("crashLog.descEmpty")}
          </DialogDescription>
        </DialogHeader>

        <pre
          className="text-caption font-mono whitespace-pre-wrap max-h-96 overflow-auto rounded-control border border-border bg-muted/50 p-3 text-foreground"
          tabIndex={0}
          aria-label={t("crashLog.contentAriaLabel")}
        >
          {text}
        </pre>

        <DialogFooter className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => void handleCopy()}
            disabled={log.length === 0}
          >
            {copied ? t("crashLog.copiedBtn") : t("crashLog.copyBtn")}
          </Button>
          <Button size="sm" onClick={() => onOpenChange(false)}>
            {t("crashLog.closeBtn")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
