import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/utils";

export interface StateViewProps {
  variant: "loading" | "empty" | "error" | "success";
  title: string;
  description?: string;
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

export function StateView({ variant, title, description, action, className }: StateViewProps) {
  const icon = VARIANT_ICON[variant];
  const titleColor = VARIANT_TITLE_COLOR[variant];

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
      ) : icon ? (
        <span className={cn("text-title font-semibold", titleColor)} aria-hidden="true">
          {icon}
        </span>
      ) : null}

      <p className={cn("text-title font-semibold", titleColor)}>{title}</p>

      {description ? (
        <p className="max-w-xs text-caption text-muted-foreground">{description}</p>
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
