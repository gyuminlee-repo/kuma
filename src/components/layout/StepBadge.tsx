import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

interface StepBadgeProps {
  status: "done" | "active" | "pending";
  /** active/pending 시 표시할 step 번호 */
  index?: number;
  className?: string;
}

/**
 * Sub-step status badge.
 * - done: success 배경 + 체크 아이콘 + "완료"(i18n)
 * - active: primary 배경 + 인덱스 숫자
 * - pending: 외곽선만 + 인덱스 숫자
 */
export function StepBadge({ status, index, className }: StepBadgeProps) {
  const { t } = useTranslation();

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 h-5 rounded-full text-xs font-medium",
        status === "done" &&
          "bg-success/20 text-success",
        status === "active" &&
          "bg-primary text-primary-foreground",
        status === "pending" &&
          "border border-border text-muted-foreground",
        className,
      )}
      aria-label={
        status === "done"
          ? t("phaseC.badge.done")
          : String(index ?? "")
      }
    >
      {status === "done" ? (
        <>
          <Check size={10} aria-hidden="true" />
          <span>{t("phaseC.badge.done")}</span>
        </>
      ) : (
        <span>{index ?? ""}</span>
      )}
    </span>
  );
}
