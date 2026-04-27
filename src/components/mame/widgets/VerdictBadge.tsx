import type { VerdictClass } from "@/types/mame/models";
import { cn } from "@/lib/utils";

interface VerdictMeta {
  label: string;
  /** Outline badge: border + text color via semantic token class */
  colorClass: string;
  /** Shape prefix for colorblind accessibility (§6.6) */
  shape: string;
}

const verdictMeta: Record<VerdictClass, VerdictMeta> = {
  PASS: {
    label: "Pass",
    colorClass: "border-success/40 text-success",
    shape: "●",
  },
  AMBIGUOUS: {
    label: "Ambiguous",
    colorClass: "border-warning/40 text-warning",
    shape: "■",
  },
  WRONG_AA: {
    label: "AA mismatch",
    colorClass: "border-error/40 text-error",
    shape: "▲",
  },
  FRAMESHIFT: {
    label: "Frameshift",
    colorClass: "border-error/40 text-error",
    shape: "▲",
  },
  MANY: {
    label: "Too many changes",
    colorClass: "border-warning/40 text-warning",
    shape: "■",
  },
  LOWDEPTH: {
    label: "Low depth",
    colorClass: "border-border text-muted-foreground",
    shape: "◆",
  },
};

interface VerdictBadgeProps {
  verdict: VerdictClass;
  className?: string;
  showDot?: boolean;
}

export function VerdictBadge({ verdict, className, showDot = true }: VerdictBadgeProps) {
  const meta = verdictMeta[verdict];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-control border px-2 py-0.5 text-caption font-semibold",
        meta.colorClass,
        className,
      )}
      aria-label={`Verdict: ${meta.label}`}
    >
      {showDot && (
        <span aria-hidden="true">{meta.shape}</span>
      )}
      {meta.label}
    </span>
  );
}
