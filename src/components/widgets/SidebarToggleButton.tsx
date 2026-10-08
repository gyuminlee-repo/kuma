/**
 * SidebarToggleButton — chevron toggle for collapsing a sidebar panel.
 *
 * [source: spec Phase G #7 — Output 영역 sidebar toggle]
 */

import { ChevronLeft, ChevronRight } from "lucide-react";

export interface SidebarToggleButtonProps {
  collapsed: boolean;
  onToggle: () => void;
  /** Which side the toggle controls. "right" = collapses right panel (chevron points right when open). */
  side?: "left" | "right";
  ariaLabel?: string;
  className?: string;
}

export function SidebarToggleButton({
  collapsed,
  onToggle,
  side = "right",
  ariaLabel,
  className = "",
}: SidebarToggleButtonProps) {
  // open + side=right → ChevronRight (collapses right)
  // collapsed + side=right → ChevronLeft (expands right)
  const Icon =
    side === "right" ? (collapsed ? ChevronLeft : ChevronRight) : collapsed ? ChevronRight : ChevronLeft;

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={ariaLabel ?? (collapsed ? "Expand panel" : "Collapse panel")}
      aria-expanded={!collapsed}
      className={`inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground ${className}`}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}
