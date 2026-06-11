/**
 * §18 Warning vs Error Standardisation — verdict badge for mame.
 *
 * Colour conventions align with StatusBadge semantic tokens so the two
 * badge families are visually consistent across kuro and mame.
 * Verdict-specific shapes (●/■/▲/◆) are preserved for colorblind
 * accessibility (§6.6).
 */

import type { VerdictClass } from "@/types/mame/models";
import { cn } from "@/lib/utils";
import { VERDICT_LABEL } from "@/lib/mame/verdictColors";
import { useTranslation } from "react-i18next";

interface VerdictMeta {
  label: string;
  /** Colour class aligned with §18 StatusBadge semantic tokens */
  colorClass: string;
  /** Shape prefix for colorblind accessibility (§6.6) */
  shape: string;
}

const verdictMeta: Record<VerdictClass, VerdictMeta> = {
  PASS: {
    label: VERDICT_LABEL.PASS,
    colorClass: "border-success/40 text-success",
    shape: "●",
  },
  AMBIGUOUS: {
    label: VERDICT_LABEL.AMBIGUOUS,
    colorClass: "border-warning/40 text-warning",
    shape: "■",
  },
  MIXED: {
    label: VERDICT_LABEL.MIXED,
    colorClass: "border-destructive/40 text-destructive",
    shape: "▲",
  },
  WRONG_AA: {
    label: VERDICT_LABEL.WRONG_AA,
    colorClass: "border-destructive/40 text-destructive",
    shape: "▲",
  },
  FRAMESHIFT: {
    label: VERDICT_LABEL.FRAMESHIFT,
    colorClass: "border-destructive/40 text-destructive",
    shape: "▲",
  },
  MANY: {
    label: VERDICT_LABEL.MANY,
    colorClass: "border-warning/40 text-warning",
    shape: "■",
  },
  LOWDEPTH: {
    label: VERDICT_LABEL.LOWDEPTH,
    colorClass: "border-border text-muted-foreground",
    shape: "◆",
  },
  NO_CALL: {
    label: VERDICT_LABEL.NO_CALL,
    colorClass: "border-muted-foreground/30 text-muted-foreground/80",
    shape: "○",
  },
};

interface VerdictBadgeProps {
  verdict: VerdictClass;
  className?: string;
  showDot?: boolean;
}

export function VerdictBadge({ verdict, className, showDot = true }: VerdictBadgeProps) {
  const { t } = useTranslation();
  const meta = verdictMeta[verdict];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-control border px-2 py-0.5 text-caption font-semibold",
        meta.colorClass,
        className,
      )}
      aria-label={`Verdict: ${meta.label}`}
      title={t(`mame.verdictBadge.help.${verdict}`)}
    >
      {showDot && (
        <span aria-hidden="true">{meta.shape}</span>
      )}
      {meta.label}
    </span>
  );
}
