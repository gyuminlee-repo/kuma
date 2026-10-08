/**
 * §18 Warning vs Error Standardisation — shared status badge component.
 *
 * Provides four semantic states with consistent colour + icon treatment
 * across kuro and mame:
 *   success  → green  ✓
 *   warning  → yellow ⚠
 *   error    → red    ✗
 *   info     → blue   ℹ
 *
 * Shape prefixes satisfy WCAG 1.4.1 (use of colour): each state has a
 * distinct symbol so the badge is distinguishable without colour.
 */

import { cn } from "@/lib/utils";

export type StatusLevel = "success" | "warning" | "error" | "info";

interface StatusConfig {
  shape: string;
  colorClass: string;
  label: string;
}

const STATUS_CONFIG: Record<StatusLevel, StatusConfig> = {
  success: {
    shape: "✓",
    colorClass: "border-success/40 text-success",
    label: "Success",
  },
  warning: {
    shape: "⚠",
    colorClass: "border-warning/40 text-warning",
    label: "Warning",
  },
  error: {
    shape: "✗",
    colorClass: "border-destructive/40 text-destructive",
    label: "Error",
  },
  info: {
    shape: "ℹ",
    colorClass: "border-info/40 text-info",
    label: "Info",
  },
};

export interface StatusBadgeProps {
  /** Semantic level — controls colour and shape prefix. */
  status: StatusLevel;
  /** Visible label text. */
  label: string;
  /** When false the shape prefix is hidden (default: true). */
  showShape?: boolean;
  className?: string;
}

/**
 * Accessible inline badge with a coloured border + text.
 *
 * aria-label is derived from the status level and label so screen readers
 * convey both the severity and the message without relying on colour.
 */
export function StatusBadge({
  status,
  label,
  showShape = true,
  className,
}: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-control border px-2 py-0.5 text-caption font-semibold",
        config.colorClass,
        className,
      )}
      aria-label={`${config.label}: ${label}`}
    >
      {showShape && (
        <span aria-hidden="true">{config.shape}</span>
      )}
      {label}
    </span>
  );
}
