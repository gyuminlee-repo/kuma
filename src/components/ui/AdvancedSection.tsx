/**
 * AdvancedSection — shared collapsible "advanced options" disclosure.
 *
 * Unifies the advanced/expandable option sections across MAME (and matches the
 * KURO Diversity "Advanced settings" pattern): a bordered toggle button with a
 * ▸/▾ chevron and a bordered content panel. Controlled via `open`/`onToggle`.
 */

import { type ReactNode } from "react";

interface AdvancedSectionProps {
  /** Toggle button label. */
  title: string;
  /** Whether the section is expanded. */
  open: boolean;
  /** Toggle handler. */
  onToggle: () => void;
  /** Expanded content. */
  children: ReactNode;
  /** Optional aria-label for the toggle button (defaults to `title`). */
  ariaLabel?: string;
  /** Stable id for the content panel (aria-controls target). */
  id?: string;
}

export function AdvancedSection({
  title,
  open,
  onToggle,
  children,
  ariaLabel,
  id = "advanced-section-panel",
}: AdvancedSectionProps) {
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={ariaLabel}
        onClick={onToggle}
        className="flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
      >
        <span className="text-muted-foreground" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span>{title}</span>
      </button>
      {open && (
        <div
          id={id}
          className="mt-1.5 rounded-container border border-border bg-card p-3"
        >
          {children}
        </div>
      )}
    </div>
  );
}
