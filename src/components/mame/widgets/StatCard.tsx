import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: number | string;
  dotColor?: string;
  className?: string;
  hint?: string;
  "aria-label"?: string;
}

export function StatCard({
  label,
  value,
  dotColor,
  className,
  hint,
  "aria-label": ariaLabel,
}: StatCardProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-lg border border-border bg-background px-4 py-3",
        className,
      )}
      role="status"
      aria-label={ariaLabel ?? `${label}: ${value}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          {dotColor && (
            <span
              className="h-2.5 w-2.5 rounded-full flex-shrink-0"
              style={{ backgroundColor: dotColor }}
              aria-hidden="true"
            />
          )}
          <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
            {label}
          </span>
        </div>
        {dotColor && (
          <span
            className="h-8 w-8 rounded-full border border-border/70 bg-card"
            aria-hidden="true"
            style={{ boxShadow: `inset 0 0 0 5px ${dotColor}` }}
          />
        )}
      </div>
      <span className="font-display text-3xl font-semibold tabular-nums leading-none text-foreground">
        {value}
      </span>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}
