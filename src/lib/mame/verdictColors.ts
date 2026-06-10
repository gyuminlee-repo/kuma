import type { VerdictClass } from "@/types/mame/models";

/** Fill / text / border hex for one verdict class. */
export interface VerdictColor {
  bg: string;
  text: string;
  border: string;
}

/**
 * Canonical verdict colours, shared by the well grid (WellPlate) and the
 * per-plate verdict breakdown chart (RunHealthPanel) so the same verdict reads
 * the same colour in both views. VerdictBadge keeps its own semantic-token plus
 * shape system, which targets a different (inline badge) rendering context.
 */
export const VERDICT_FILL: Record<VerdictClass, VerdictColor> = {
  PASS: { bg: "#2E7D32", text: "#FFFFFF", border: "#1B5E20" },
  AMBIGUOUS: { bg: "#F9A825", text: "#1A1200", border: "#F57F17" },
  MIXED: { bg: "#FB8C00", text: "#FFFFFF", border: "#E65100" },
  WRONG_AA: { bg: "#C62828", text: "#FFFFFF", border: "#B71C1C" },
  FRAMESHIFT: { bg: "#AD1457", text: "#FFFFFF", border: "#880E4F" },
  MANY: { bg: "#E65100", text: "#FFFFFF", border: "#BF360C" },
  LOWDEPTH: { bg: "#9E9E9E", text: "#FFFFFF", border: "#757575" },
  NO_CALL: { bg: "#616161", text: "#FFFFFF", border: "#424242" },
};

/** Verdict classes counted as "detected" (reproduced) by the backend. */
export const DETECTED_VERDICTS: readonly VerdictClass[] = ["PASS", "AMBIGUOUS"];

/** Canonical display labels for each verdict class. Single source of truth. */
export const VERDICT_LABEL: Record<VerdictClass, string> = {
  PASS: "Pass",
  AMBIGUOUS: "Ambiguous",
  MIXED: "Mixed",
  WRONG_AA: "Wrong AA",
  FRAMESHIFT: "Frameshift",
  MANY: "Many",
  LOWDEPTH: "Low depth",
  NO_CALL: "No call",
};
