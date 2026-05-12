/**
 * CloseConfirmDialog — §22 Graceful Shutdown 용 close 확인 모달.
 *
 * busy 상태(디자인/분석/export)에서 창 닫기 시도 시 표시.
 * "Wait" 버튼: isBusy가 false로 바뀌면 자동 close.
 * "Force close" 버튼: 즉시 destroy.
 */

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export type BusyReason = "designing" | "analyzing" | "exporting";

interface CloseConfirmDialogProps {
  open: boolean;
  reason: BusyReason | null;
  isBusy: boolean;
  onWait: () => void;
  onForceClose: () => void;
}

const REASON_KEYS: Record<BusyReason, { titleKey: string; descriptionKey: string }> = {
  designing: {
    titleKey: "closeConfirm.designing.title",
    descriptionKey: "closeConfirm.designing.description",
  },
  analyzing: {
    titleKey: "closeConfirm.analyzing.title",
    descriptionKey: "closeConfirm.analyzing.description",
  },
  exporting: {
    titleKey: "closeConfirm.exporting.title",
    descriptionKey: "closeConfirm.exporting.description",
  },
};

export function CloseConfirmDialog({
  open,
  reason,
  isBusy,
  onWait,
  onForceClose,
}: CloseConfirmDialogProps) {
  const { t } = useTranslation();

  // isBusy가 false로 바뀌면 자동 close (Wait 선택 후 작업 완료 시)
  useEffect(() => {
    if (open && !isBusy) {
      onForceClose();
    }
  }, [open, isBusy, onForceClose]);

  const keys = reason ? REASON_KEYS[reason] : REASON_KEYS.designing;
  const isExportingReason = reason === "exporting";

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // 외부 dismiss (ESC, 오버레이 클릭) → Wait 동작과 동일
        if (!next) onWait();
      }}
    >
      <DialogContent className="max-w-sm" aria-labelledby="close-confirm-title" aria-describedby="close-confirm-desc">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <AlertTriangle
              size={18}
              aria-hidden="true"
              className={isExportingReason ? "text-destructive" : "text-warning"}
            />
            <DialogTitle id="close-confirm-title">{t(keys.titleKey)}</DialogTitle>
          </div>
          <DialogDescription id="close-confirm-desc" className="pt-1">
            {t(keys.descriptionKey)}
          </DialogDescription>
        </DialogHeader>

        {isExportingReason && (
          <p
            className="rounded-control border border-destructive/30 bg-destructive/5 px-3 py-2 text-caption text-destructive"
            role="alert"
          >
            {t("closeConfirm.exporting.forceCloseWarning")}
          </p>
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onWait}
            aria-label={t("closeConfirm.waitAriaLabel")}
          >
            {t("closeConfirm.waitLabel")}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onForceClose}
            aria-label={t("closeConfirm.forceCloseAriaLabel")}
          >
            {t("closeConfirm.forceCloseLabel")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
