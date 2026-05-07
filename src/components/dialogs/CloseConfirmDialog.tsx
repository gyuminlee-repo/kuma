/**
 * CloseConfirmDialog — §22 Graceful Shutdown 용 close 확인 모달.
 *
 * busy 상태(디자인/분석/export)에서 창 닫기 시도 시 표시.
 * "Wait" 버튼: isBusy가 false로 바뀌면 자동 close.
 * "Force close" 버튼: 즉시 destroy.
 */

import { useEffect } from "react";
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

const REASON_LABELS: Record<BusyReason, { title: string; description: string }> = {
  designing: {
    title: "디자인 진행 중",
    description: "프라이머 디자인이 실행 중입니다. 지금 닫으면 작업이 취소됩니다.",
  },
  analyzing: {
    title: "분석 진행 중",
    description: "시퀀싱 데이터 분석이 실행 중입니다. 지금 닫으면 작업이 취소됩니다.",
  },
  exporting: {
    title: "Export 진행 중",
    description:
      "파일을 저장하는 중입니다. 지금 닫으면 파일이 손상되거나 저장되지 않을 수 있습니다.",
  },
};

export function CloseConfirmDialog({
  open,
  reason,
  isBusy,
  onWait,
  onForceClose,
}: CloseConfirmDialogProps) {
  // isBusy가 false로 바뀌면 자동 close (Wait 선택 후 작업 완료 시)
  useEffect(() => {
    if (open && !isBusy) {
      onForceClose();
    }
  }, [open, isBusy, onForceClose]);

  const labels = reason ? REASON_LABELS[reason] : REASON_LABELS.designing;
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
            <DialogTitle id="close-confirm-title">{labels.title}</DialogTitle>
          </div>
          <DialogDescription id="close-confirm-desc" className="pt-1">
            {labels.description}
          </DialogDescription>
        </DialogHeader>

        {isExportingReason && (
          <p
            className="rounded-control border border-destructive/30 bg-destructive/5 px-3 py-2 text-caption text-destructive"
            role="alert"
          >
            Export 중 강제 종료 시 출력 파일이 손상될 수 있습니다.
          </p>
        )}

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onWait}
            aria-label="작업 완료까지 대기"
          >
            대기 (작업 완료 후 자동 종료)
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onForceClose}
            aria-label="지금 강제 종료"
          >
            강제 종료
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
