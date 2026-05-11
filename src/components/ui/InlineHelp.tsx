/**
 * InlineHelp — reusable inline (?) help tooltip.
 * Replaces ad-hoc `title=` attrs and the local HelpTip in DiversitySections.
 * Renders a small circular "?" button that toggles an inline tip block.
 *
 * Usage:
 *   <InlineHelp text="Explanation shown when the user clicks (?)" />
 *   <InlineHelp text="Multi-line\nsupported" className="ml-1" />
 */
import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

interface InlineHelpProps {
  /** The help text content (plain string; newlines are preserved). */
  text: string;
  className?: string;
}

export function InlineHelp({ text, className }: InlineHelpProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) return;
    const update = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPosition({
        top: Math.min(rect.bottom + 6, window.innerHeight - 120),
        left: Math.min(rect.left, window.innerWidth - 280),
      });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open]);

  return (
    <span className={cn("inline-flex align-middle", className)}>
      <button
        ref={buttonRef}
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
      {open && position && typeof document !== "undefined" &&
        createPortal(
          <span
            role="tooltip"
            className="fixed z-[100] block w-[260px] rounded-control border border-border bg-popover px-2.5 py-2 text-caption leading-relaxed text-popover-foreground shadow-lg whitespace-pre-line"
            style={{ top: position.top, left: position.left }}
          >
            {text}
          </span>,
          document.body,
        )}
    </span>
  );
}
