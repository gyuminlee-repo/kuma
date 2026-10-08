/**
 * RoundPromptDialog, EVOLVEpro round unset 시 라운드 값을 묻는 다이얼로그.
 *
 * evolveproRound가 0(unset)인 채로 EVOLVEpro campaign이 로드되면 표시.
 * 강제 선택이 아니며(dismissible), Dismiss 시 round는 0으로 유지됨.
 */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";

interface RoundPromptDialogProps {
  open: boolean;
  suggestedRound: number | null;
  onConfirm: (round: number) => void;
  onDismiss: () => void;
}

export function RoundPromptDialog({
  open,
  suggestedRound,
  onConfirm,
  onDismiss,
}: RoundPromptDialogProps) {
  const { t } = useTranslation();
  const [roundStr, setRoundStr] = useState(String(suggestedRound ?? 1));
  const wasOpenRef = useRef(open);

  // Resync roundStr from suggestedRound only on the closed->open transition.
  // suggestedRound can change after mount (round history loading async), so
  // the initial useState value can be stale by the time the dialog opens.
  // Do not resync while already open, that would clobber user typing.
  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setRoundStr(String(suggestedRound ?? 1));
    }
    wasOpenRef.current = open;
  }, [open, suggestedRound]);

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onDismiss();
      }}
    >
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t("roundPrompt.title")}</DialogTitle>
          <DialogDescription asChild>
            <p>{t("roundPrompt.description")}</p>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <label htmlFor="round-prompt-input" className="text-xs font-medium text-foreground">
            {t("roundPrompt.roundLabel")}
          </label>
          <input
            id="round-prompt-input"
            type="number"
            min={1}
            value={roundStr}
            onChange={(e) => setRoundStr(e.target.value)}
            aria-label={t("roundPrompt.roundAriaLabel")}
            className="w-20 rounded border border-border bg-card px-1.5 py-0.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          {suggestedRound !== null && (
            <p className="text-caption text-muted-foreground">
              {t("roundPrompt.suggestedHint", { suggested: suggestedRound })}
            </p>
          )}
        </div>

        <DialogFooter className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onDismiss}>
            {t("roundPrompt.dismissLabel")}
          </Button>
          <Button
            size="sm"
            onClick={() => {
              const n = Number.parseInt(roundStr, 10);
              if (Number.isNaN(n) || n < 1) return;
              onConfirm(n);
            }}
          >
            {t("roundPrompt.confirmLabel")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
