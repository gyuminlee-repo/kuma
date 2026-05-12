import type { MouseEvent } from "react";
import { useTranslation } from "react-i18next";

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
