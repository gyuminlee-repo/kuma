/**
 * §19 Performance Guardrails — 입력 크기 사전 경고 다이얼로그
 *
 * Dialog(shadcn/ui)를 재사용. AlertDialog 컴포넌트가 프로젝트에 없으므로
 * 기존 Dialog 패턴을 따름 (AppLayout.tsx missingFields 모달 동일 패턴).
 *
 * level "warn" = 경고 톤, continue 버튼 "Continue"
 * level "block" = 강권 톤, continue 버튼 "Continue anyway"
 */

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
import type { InputSizeLevel } from "@/lib/inputThresholds";

interface InputSizeWarningDialogBaseProps {
  open: boolean;
  level: InputSizeLevel;
  message: string;
  /** Replaces the level-derived title when the limit is not about input size. */
  title?: string;
  onCancel: () => void;
}

/**
 * `onContinue` is required exactly when the dialog renders a continue button.
 *
 * A union rather than an optional prop with a JSDoc note: the note cannot fail
 * a build, and a caller that forgets `onContinue` without `acknowledgeOnly`
 * renders `onClick={undefined}`, a button that looks live and does nothing.
 * `onContinue?: never` on the acknowledge-only arm also rejects passing a
 * handler that would never be reachable.
 */
type InputSizeWarningDialogProps = InputSizeWarningDialogBaseProps &
  (
    | {
        /**
         * Acknowledge-only: a single confirm button and no continue action, for
         * a limit the user cannot proceed past. A "continue anyway" button
         * would be a lie there, and a second dialog component would be the
         * third copy of this one (PreflightDialog is already the second).
         */
        acknowledgeOnly: true;
        onContinue?: never;
      }
    | {
        acknowledgeOnly?: false;
        onContinue: () => void;
      }
  );

export function InputSizeWarningDialog({
  open,
  level,
  message,
  title: titleOverride,
  acknowledgeOnly = false,
  onContinue,
  onCancel,
}: InputSizeWarningDialogProps) {
  const { t } = useTranslation();
  const title =
    titleOverride ??
    (level === "block"
      ? t("inputSizeWarning.titleBlock")
      : t("inputSizeWarning.title"));

  const continueLabel =
    level === "block" ? t("inputSizeWarning.continueLabelBlock") : t("inputSizeWarning.continueLabel");

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
          {acknowledgeOnly ? (
            <Button size="sm" onClick={onCancel}>
              {t("inputSizeWarning.acknowledgeLabel")}
            </Button>
          ) : (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={onCancel}
              >
                {t("inputSizeWarning.cancelLabel")}
              </Button>
              <Button
                size="sm"
                variant={level === "block" ? "outline" : "default"}
                className={level === "block" ? "text-warning border-warning/40 hover:bg-warning/8" : ""}
                onClick={onContinue}
              >
                {continueLabel}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
