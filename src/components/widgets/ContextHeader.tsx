import { type ReactNode } from "react";

export type ContextHeaderProps = {
  /** Bold primary label */
  title: string;
  /** Secondary label, single-line truncated */
  subtitle?: string;
  /** Action buttons (0-3). Last one is typically primary. */
  actions?: ReactNode;
};

/**
 * ContextHeader — main-area header strip.
 * Matches mockup CSS line 114-116: grid 1fr/auto, padding 11px 14px.
 */
export function ContextHeader({ title, subtitle, actions }: ContextHeaderProps) {
  return (
    <header
      role="banner"
      aria-label="screen-header"
      className="grid shrink-0 items-center gap-3 border-b border-border bg-card px-[14px] py-[11px]"
      style={{ gridTemplateColumns: "1fr auto" }}
    >
      <div className="min-w-0">
        <span className="block truncate text-sm font-semibold text-foreground">
          {title}
        </span>
        {subtitle && (
          <span className="block truncate text-xs text-muted-foreground">
            {subtitle}
          </span>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-1.5">{actions}</div>
      )}
    </header>
  );
}
