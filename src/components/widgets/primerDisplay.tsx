import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";

// Legacy hairpin/homodimer warn threshold (pre-engine-flag behavior, see
// PR #443). The frontend has no dH, so it cannot recompute the engine's
// folded-fraction verdict (theta) itself.
export const LEGACY_STRUCTURE_WARN_TM = 40;

// applyReversePropagation (designSlice.helpers.ts) clears warn flags per
// structure, not per row: it copies homodimer_warn_fwd/rev through
// unchanged but resets hairpin_warn_fwd/rev to undefined (Ta-dependent,
// cannot be reused after re-pairing). Judging a whole row as "engine has
// spoken" once any one flag is present reads the absent hairpin flags as
// false and hides a real hairpin warning on a reverse-propagated row.
// Each of the four structures (hairpin fwd/rev, homodimer fwd/rev) is
// judged independently: use the engine flag when present, otherwise fall
// back to the legacy Tm threshold for that structure only.
export function structureWarn(flag: boolean | undefined, tm: number | undefined): boolean {
  if (flag == null) return (tm ?? 0) > LEGACY_STRUCTURE_WARN_TM;
  return flag === true;
}

export function formatTolerance(tf?: number, tr?: number, fallback?: number): string {
  if (tf != null && tr != null) return `\u00B1${tf.toFixed(1)}/\u00B1${tr.toFixed(1)}`;
  if (fallback != null) return `\u00B1${fallback.toFixed(1)}`;
  return "\u2014";
}

export function ColoredFwdSeq({ seq, overlapLen }: {
  seq: string;
  overlapLen: number;
}) {
  const overlap = seq.slice(0, overlapLen);
  const codon = seq.slice(overlapLen, overlapLen + 3);
  const rest = seq.slice(overlapLen + 3);

  return (
    <span className="font-mono text-caption break-all">
      <span style={{ color: "#3b82f6" }}>{overlap}</span>
      <span style={{ color: "#ef4444", fontWeight: 600 }}>{codon}</span>
      <span>{rest}</span>
    </span>
  );
}

export function CopySeqButton({
  seq,
  copied,
  onCopy,
}: {
  seq: string;
  copied: boolean;
  onCopy: (e: MouseEvent<HTMLButtonElement>) => void;
}) {
  const { t } = useTranslation();
  return (
    <button
      className="ml-1 flex-shrink-0 text-muted-foreground/50 hover:text-muted-foreground text-caption leading-none"
      onClick={onCopy}
      title={t("primerDisplay.copySeqTitle")}
      aria-label={t("primerDisplay.copySeqAriaLabel", { seq })}
    >
      {copied ? "\u2713" : "\uD83D\uDCCB"}
    </button>
  );
}
