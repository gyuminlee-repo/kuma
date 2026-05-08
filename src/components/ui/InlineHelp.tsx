/**
 * InlineHelp — reusable inline (?) help tooltip.
 * Replaces ad-hoc `title=` attrs and the local HelpTip in DiversitySections.
 * Renders a small circular "?" button that toggles an inline tip block.
 *
 * Usage:
 *   <InlineHelp text="Explanation shown when the user clicks (?)" />
 *   <InlineHelp text="Multi-line\nsupported" className="ml-1" />
 */
import { useState } from "react";
import { cn } from "@/lib/utils";

interface InlineHelpProps {
  /** The help text content (plain string; newlines are preserved). */
  text: string;
  className?: string;
}

export function InlineHelp({ text, className }: InlineHelpProps) {
  const [open, setOpen] = useState(false);

  return (
    <span className={cn("inline-flex flex-col", className)}>
      <button
        type="button"
        aria-label={open ? "Hide help" : "Show help"}
        aria-expanded={open}
        className={cn(
          "inline-flex h-4 w-4 items-center justify-center rounded-full text-plate-tiny font-bold leading-none transition-colors",
          "bg-muted text-muted-foreground",
          "hover:bg-accent hover:text-accent-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
        )}
        onClick={(e) => {
          e.preventDefault();
          setOpen((prev) => !prev);
        }}
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className="mt-0.5 block rounded-control border border-border bg-muted px-1.5 py-1 text-caption leading-relaxed text-muted-foreground whitespace-pre-line"
        >
          {text}
        </span>
      )}
    </span>
  );
}
