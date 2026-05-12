import { useState } from "react";
import { WifiOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/utils";
import type { ErrorKind } from "@/lib/errorClassifier";

export interface StateViewProps {
  variant: "loading" | "empty" | "error" | "success";
  title: string;
  description?: string;
  /** Traceback 또는 상세 에러 문자열. error variant에서만 표시된다. */
  details?: string;
  /**
   * §4 네트워크 에러 분리 — "network"이면 WifiOff 아이콘과 amber 색조 적용.
   * 미지정 시 기본 error 스타일.
   */
  errorKind?: ErrorKind;
  action?: { label: string; onClick: () => void };
  className?: string;
}

const VARIANT_ICON: Record<StateViewProps["variant"], string | null> = {
  loading: null,
  empty: "○",
  error: "✕",
  success: "✓",
};

const VARIANT_TITLE_COLOR: Record<StateViewProps["variant"], string> = {
  loading: "text-foreground",
  empty: "text-foreground",
  error: "text-error",
  success: "text-success",
};

export function StateView({
  variant,
  title,
  description,
  details,
  errorKind,
  action,
  className,
}: StateViewProps) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);
  const icon = VARIANT_ICON[variant];
  const isNetwork = variant === "error" && errorKind === "network";
  const titleColor = isNetwork ? "text-amber-500 dark:text-amber-400" : VARIANT_TITLE_COLOR[variant];

  return (
    <div
      role={variant === "error" ? "alert" : undefined}
      aria-live={variant === "loading" ? "polite" : undefined}
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-6 py-8 text-center",
        className,
      )}
    >
      {variant === "loading" ? (
        <Spinner size="md" />
      ) : isNetwork ? (
        <WifiOff
          size={24}
          className="text-amber-500 dark:text-amber-400"
          aria-hidden="true"
        />
      ) : icon ? (
        <span className={cn("text-title font-semibold", titleColor)} aria-hidden="true">
          {icon}
        </span>
      ) : null}

      <p className={cn("text-title font-semibold", titleColor)}>{title}</p>

      {description ? (
        <p className="max-w-xs text-caption text-muted-foreground">{description}</p>
      ) : null}

      {variant === "error" && details ? (
        <div className="mt-1 w-full max-w-sm text-left">
          <button
            type="button"
            aria-expanded={showDetails}
            aria-controls="state-view-traceback"
            onClick={() => setShowDetails((prev) => !prev)}
            className={cn(
              "flex items-center gap-1 text-caption text-muted-foreground underline-offset-2",
              "hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2",
              "focus-visible:ring-ring rounded-sm",
            )}
          >
            <span aria-hidden="true">{showDetails ? "▾" : "▸"}</span>
            {showDetails ? t("ui.stateView.hideDetails") : t("ui.stateView.showDetails")}
          </button>

          {showDetails ? (
            <pre
              id="state-view-traceback"
              className={cn(
                "mt-2 max-h-48 overflow-auto rounded-control border border-border",
                "bg-muted px-3 py-2 text-[11px] leading-relaxed text-muted-foreground",
                "whitespace-pre-wrap break-words text-left",
              )}
            >
              {details}
            </pre>
          ) : null}
        </div>
      ) : null}

      {action ? (
        <Button
          variant="outline"
          size="sm"
          onClick={action.onClick}
          className="mt-2 h-control"
        >
          {action.label}
        </Button>
      ) : null}
    </div>
  );
}
