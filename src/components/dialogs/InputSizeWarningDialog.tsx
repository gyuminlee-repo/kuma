/**
 * §19 Performance Guardrails — 입력 크기 사전 경고 다이얼로그
 *
 * Dialog(shadcn/ui)를 재사용. AlertDialog 컴포넌트가 프로젝트에 없으므로
 * 기존 Dialog 패턴을 따름 (AppLayout.tsx missingFields 모달 동일 패턴).
 *
 * level "warn" = 경고 톤, continue 버튼 "Continue"
 * level "block" = 강권 톤, continue 버튼 "Continue anyway"
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
import type { InputSizeLevel } from "@/lib/inputThresholds";

interface InputSizeWarningDialogProps {
  open: boolean;
  level: InputSizeLevel;
  message: string;
  onContinue: () => void;
  onCancel: () => void;
}

export function InputSizeWarningDialog({
  open,
  level,
  message,
  onContinue,
  onCancel,
}: InputSizeWarningDialogProps) {
  const title =
    level === "block"
      ? "입력 크기 경고 — 매우 큰 작업"
      : "입력 크기 경고";

  const continueLabel = level === "block" ? "Continue anyway" : "Continue";

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onCancel();
      }}
    >
      <DialogContent className="max-w-md" role="alertdialog" aria-modal="true">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription asChild>
            <p>{message}</p>
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            variant={level === "block" ? "outline" : "default"}
            className={level === "block" ? "text-warning border-warning/40 hover:bg-warning/8" : ""}
            onClick={onContinue}
          >
            {continueLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
