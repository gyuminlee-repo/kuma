import type { VerdictClass } from "../../types/models";
import { cn } from "@/lib/utils";

interface VerdictMeta {
  label: string;
  bgColor: string;
  textColor: string;
  dotColor: string;
}

const verdictMeta: Record<VerdictClass, VerdictMeta> = {
  PASS: {
    label: "Pass",
    bgColor: "bg-verdict-pass-light",
    textColor: "text-verdict-pass",
    dotColor: "bg-verdict-pass",
  },
  AMBIGUOUS: {
    label: "Ambiguous",
    bgColor: "bg-verdict-ambiguous-light",
    textColor: "text-verdict-ambiguous",
    dotColor: "bg-verdict-ambiguous",
  },
  WRONG_AA: {
    label: "AA mismatch",
    bgColor: "bg-verdict-fail-light",
    textColor: "text-verdict-fail",
    dotColor: "bg-verdict-fail",
  },
  FRAMESHIFT: {
    label: "Frameshift",
    bgColor: "bg-verdict-frameshift-light",
    textColor: "text-verdict-frameshift",
    dotColor: "bg-verdict-frameshift",
  },
  MANY: {
    label: "Too many changes",
    bgColor: "bg-verdict-many-light",
    textColor: "text-verdict-many",
    dotColor: "bg-verdict-many",
  },
  LOWDEPTH: {
    label: "Low depth",
    bgColor: "bg-verdict-lowdepth-light",
    textColor: "text-verdict-lowdepth",
    dotColor: "bg-verdict-lowdepth",
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
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold",
        meta.bgColor,
        meta.textColor,
        className,
      )}
      aria-label={`Verdict: ${meta.label}`}
    >
      {showDot && (
        <span
          className={cn("h-1.5 w-1.5 rounded-full flex-shrink-0", meta.dotColor)}
          aria-hidden="true"
        />
      )}
      {meta.label}
    </span>
  );
}
