import { useState, type MouseEvent } from "react";
import type { TFunction } from "i18next";
import { createColumnHelper } from "@tanstack/react-table";
import type { RescuedMutation, SdmPrimerResult } from "../../types/models";
import { ColoredFwdSeq, CopySeqButton, formatTolerance } from "./primerDisplay";

const col = createColumnHelper<SdmPrimerResult>();

const GROUP_COLORS = [
  "#3b82f6", "#ef4444", "#f59e0b", "#10b981",
  "#8b5cf6", "#ec4899", "#06b6d4", "#f97316",
];

export const HEADER_TOOLTIPS: Record<string, string> = {
  rank: "Input order (y_pred descending rank)",
  mutation: "Amino acid substitution. Click header to sort by aa position",
  y_pred: "Predicted fitness score (higher = better predicted activity)",
  forward_seq: "Full forward primer (overlap + mutation codon + downstream). Click to compare candidates",
  reverse_seq: "Full reverse primer. Click to compare candidates",
  fwd_len: "Forward primer length (bp)",
  rev_len: "Reverse primer length (bp)",
  tm_no_fwd: "Forward whole-primer Tm (SantaLucia 1998)",
  tm_no_rev: "Reverse whole-primer Tm (SantaLucia 1998)",
  tm_overlap: "Overlap region Tm - should be lower than Fwd/Rev Tm",
  recommended_ta: "Recommended annealing temperature (Ta). Hover a cell for the formula and touchdown schedule",
  tolerance_used: "Tm tolerance Fwd/Rev (each starts at +/-0.5, widens by 0.5 up to +/-3.0)",
  penalty: "Penalty score: Tm deviation + GC% + codon distance + hairpin/homodimer + synthesis difficulty (lower = better)",
  candidate_count: "Unique forward / reverse candidates (click to compare if >1)",
  has_offtarget: "Off-target binding detected on template strand",
  hairpin: "Hairpin/Homodimer worst Tm (>40°C = warning)",
  gc_fwd: "Forward primer GC content (40-60% recommended)",
  gc_rev: "Reverse primer GC content (40-60% recommended)",
  synth: "Synthesis quality score (100=ideal). Penalizes: homopolymer runs, GC-rich stretches, dinucleotide repeats, extreme GC%. Hover cell for Fwd/Rev breakdown",
  wt_codon: "Wild-type codon at this position",
};

function CopySeqAction({ seq }: { seq: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    navigator.clipboard.writeText(seq).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };
  return <CopySeqButton seq={seq} copied={copied} onCopy={handleCopy} />;
}

/**
 * Builds a position→color map for duplicate aa positions.
 * Only positions that appear ≥2 times in the input array receive a color.
 * Colors are assigned in first-appearance order.
 */
export function buildPositionColorMap(positions: (number | null)[]): Map<number, string> {
  const posCount = new Map<number, number>();
  for (const pos of positions) {
    if (pos != null) posCount.set(pos, (posCount.get(pos) ?? 0) + 1);
  }

  const colorMap = new Map<number, string>();
  let idx = 0;
  for (const [pos, count] of posCount) {
    if (count >= 2) {
      colorMap.set(pos, GROUP_COLORS[idx % GROUP_COLORS.length]);
      idx++;
    }
  }
  return colorMap;
}

export function buildGroupColorMap(results: SdmPrimerResult[]): Map<number, string> {
  return buildPositionColorMap(results.map((r) => r.aa_position));
}

export function makeResultTableColumns(opts: {
  groupColorMap: Map<number, string>;
  codonStrategy: "closest" | "optimal";
  overlapMode: "partial" | "full";
  swapped: Record<string, string>;
  customCandidates: Record<string, SdmPrimerResult[]>;
  rescuedMutations: Set<string>;
  rescueDetailMap: Map<string, RescuedMutation>;
  removeDesignResult: (mutation: string, reason: string) => void;
  yPredMap: Record<string, number>;
  /**
   * Canonical row-order index map produced by sortPrimersCanonical().
   * When provided, the Mutation column sortingFn uses this map as the
   * single source of truth so ResultTable order matches Plate/Mapping views.
   */
  canonicalOrder?: Map<SdmPrimerResult, number>;
  /** When true, adds a visible border to rescue badges so state is
   *  distinguishable without colour (WCAG 1.4.1 compliance). */
  colorblindMode?: boolean;
  /** i18next translate function passed from the parent component. */
  t: TFunction;
}) {
  const {
    groupColorMap,
    codonStrategy,
    overlapMode,
    swapped,
    customCandidates,
    rescuedMutations,
    rescueDetailMap,
    removeDesignResult,
    yPredMap,
    canonicalOrder,
    colorblindMode = false,
    t,
  } = opts;

  return [
    col.display({
      id: "rank",
      header: "#",
      size: 35,
      enableSorting: false,
      cell: (info) => <span className="text-muted-foreground">{info.row.index + 1}</span>,
    }),
    col.accessor("mutation", {
      header: "Mutation",
      size: 90,
      sortingFn: (a, b) => {
        if (canonicalOrder) {
          const ia = canonicalOrder.get(a.original);
          const ib = canonicalOrder.get(b.original);
          if (ia != null && ib != null) return ia - ib;
        }
        // Fallback when canonicalOrder is not provided.
        const posA = a.original.aa_position ?? 0;
        const posB = b.original.aa_position ?? 0;
        if (posA !== posB) return posA - posB;
        return a.index - b.index;
      },
      cell: (info) => {
        const row = info.row.original;
        const color = row.aa_position != null ? groupColorMap.get(row.aa_position) : undefined;
        const isRescued = rescuedMutations.has(row.mutation);
        const rescueDetail = rescueDetailMap.get(row.mutation);
        return (
          <span className="font-mono font-medium flex items-center gap-1">
            <span>
              {info.getValue()}
              {color && (
                <span
                  className="inline-block ml-1 px-1 rounded-control text-plate-tiny font-semibold text-white align-middle"
                  style={{ backgroundColor: color }}
                >
                  Pos{row.aa_position}
                </span>
              )}
            </span>
            {rescueDetail && (() => {
              const badgeMap: Record<string, { icon: string; label: string; tooltip: string; colorClass: string }> = {
                pool_cascade: {
                  icon: "↻",
                  label: `↻ ${rescueDetail.original}`,
                  tooltip: `Pool cascade: replaced ${rescueDetail.original}`,
                  colorClass: "bg-success/10 text-success",
                },
                auto_relax: {
                  icon: "⚡",
                  label: "⚡ relaxed",
                  tooltip: "Auto-relax: widened Tm tolerance and GC range",
                  colorClass: "bg-warning/10 text-warning",
                },
                auto_suggestion: {
                  icon: "\u{1F3AF}",
                  label: "\u{1F3AF} suggestion",
                  tooltip: "Auto-retry (suggestion): re-designed with parameters derived from successful primers in this run",
                  colorClass: "bg-info/10 text-info",
                },
                auto_suggestion_l1: {
                  icon: "\u{1F3AF}¹",
                  label: "\u{1F3AF}¹ stage 1",
                  tooltip: "Cascade stage 1: length range widened",
                  colorClass: "bg-info/10 text-info",
                },
                auto_suggestion_l2: {
                  icon: "\u{1F3AF}²",
                  label: "\u{1F3AF}² stage 2",
                  tooltip: "Cascade stage 2: length + GC range widened",
                  colorClass: "bg-info/10 text-info",
                },
                auto_suggestion_l3: {
                  icon: "\u{1F3AF}³",
                  label: "\u{1F3AF}³ stage 3",
                  tooltip: "Cascade stage 3: length + GC + mild Tm tolerance widened",
                  colorClass: "bg-info/15 text-info",
                },
                auto_suggestion_l4: {
                  icon: "\u{1F3AF}⁴",
                  label: "\u{1F3AF}⁴ stage 4",
                  tooltip: "Cascade stage 4: strong relaxation applied",
                  colorClass: "bg-warning/10 text-warning",
                },
                same_position: {
                  icon: "↻¹",
                  label: "↻¹ same pos",
                  tooltip: `Substituted: same-position alternate variant (substitute: ${rescueDetail.substitute ?? "unknown"})`,
                  colorClass: "bg-success/10 text-success",
                },
                diff_position: {
                  icon: "↻²",
                  label: "↻² diff pos",
                  tooltip: `Substituted: different-position variant (substitute: ${rescueDetail.substitute ?? "unknown"})`,
                  colorClass: "bg-success/15 text-success",
                },
              };
              const badge = badgeMap[rescueDetail.type] ?? {
                icon: "\u{1F3AF}",
                label: "\u{1F3AF} rescued",
                tooltip: `Rescued (${rescueDetail.type})`,
                colorClass: "bg-info/10 text-info",
              };
              // §8 A11y: colorblind mode adds a visible border so badge state
              // is distinguishable by shape/outline, not colour alone (WCAG 1.4.1).
              const cbClass = colorblindMode ? " border border-current" : "";
              return (
                <span
                  className={`ml-1 px-1 py-0.5 rounded-control text-plate-tiny leading-none ${badge.colorClass}${cbClass}`}
                  title={badge.tooltip}
                >
                  {badge.label}
                </span>
              );
            })()}
            {isRescued && !rescueDetail && (
              <button
                className="ml-1 px-1 py-0.5 bg-error/10 text-error rounded-control text-plate-tiny hover:bg-error/20 leading-none"
                title={t("resultTable.removeCustomRescueTitle")}
                onClick={(e) => {
                  e.stopPropagation();
                  removeDesignResult(row.mutation, "Manually removed custom rescue");
                }}
              >
                ✕
              </button>
            )}
          </span>
        );
      },
    }),
    ...(Object.keys(yPredMap).length > 0
      ? [
          col.accessor((row) => yPredMap[row.mutation] ?? -Infinity, {
            id: "y_pred",
            header: "y_pred",
            size: 65,
            sortingFn: "basic",
            cell: (info) => {
              const val = info.getValue();
              return val > -Infinity ? (
                <span className="text-muted-foreground">{val.toFixed(3)}</span>
              ) : (
                <span className="text-muted-foreground/60">—</span>
              );
            },
          }),
        ]
      : []),
    col.accessor("forward_seq", {
      header: "Forward Primer",
      size: 220,
      enableSorting: false,
      meta: { clickable: true },
      cell: (info) => {
        const row = info.row.original;
        const fwdEdited = swapped[row.mutation] === "fwd" || swapped[row.mutation] === "both";
        return (
          <span className={`flex items-center ${fwdEdited ? "bg-warning/10 rounded-control px-0.5" : ""}`}>
            <span className="flex-1 min-w-0">
              <ColoredFwdSeq seq={info.getValue()} overlapLen={row.overlap_len ?? 0} />
            </span>
            <CopySeqAction seq={info.getValue()} />
          </span>
        );
      },
    }),
    col.accessor("reverse_seq", {
      header: "Reverse Primer",
      size: 200,
      enableSorting: false,
      meta: { clickable: true },
      cell: (info) => {
        const revEdited = swapped[info.row.original.mutation] === "rev" || swapped[info.row.original.mutation] === "both";
        return (
          <span className={`flex items-center font-mono text-caption ${revEdited ? "bg-warning/10 rounded-control px-0.5" : ""}`}>
            <span className="flex-1 min-w-0 break-all">{info.getValue()}</span>
            <CopySeqAction seq={info.getValue()} />
          </span>
        );
      },
    }),
    col.accessor("fwd_len", { header: "Fwd", size: 40 }),
    col.accessor("rev_len", { header: "Rev", size: 40 }),
    col.accessor("tm_no_fwd", { header: "Tm F", size: 55, cell: (info) => info.getValue().toFixed(1) }),
    col.accessor("tm_no_rev", { header: "Tm R", size: 55, cell: (info) => info.getValue().toFixed(1) }),
    // In full-overlap mode (NEB Q5 SDM), tm_overlap == tm_fwd (redundant). Hide the column.
    ...(overlapMode !== "full"
      ? [col.accessor("tm_overlap", { header: "Tm Ov", size: 55, cell: (info) => info.getValue().toFixed(1) })]
      : []),
    col.accessor("recommended_ta", {
      header: "Ta (°C)",
      size: 70,
      cell: (info) => {
        const row = info.row.original;
        const ta = info.getValue();
        if (ta == null) return "-";
        const tip =
          (row.ta_detail ?? "") +
          (row.ta_touchdown ? ` · Touchdown: ${row.ta_touchdown}` : "") +
          " · Recommended starting Ta; optimize with gradient or touchdown";
        return (
          <span title={tip}>
            {ta.toFixed(1)}
            {row.ta_mode ? (
              <span className="ml-1 text-plate-tiny text-muted-foreground">{row.ta_mode}</span>
            ) : null}
          </span>
        );
      },
    }),
    col.accessor("tolerance_used", {
      header: "Tol",
      size: 65,
      cell: (info) => {
        const row = info.row.original;
        return formatTolerance(row.tolerance_fwd, row.tolerance_rev, info.getValue());
      },
    }),
    col.accessor("penalty", {
      header: "Pen",
      size: 45,
      cell: (info) => {
        const val = info.getValue();
        return val != null ? val.toFixed(1) : "—";
      },
    }),
    col.accessor("candidate_count", {
      header: "Cand",
      size: 50,
      sortingFn: (a, b) => {
        const customA = (customCandidates[a.original.mutation] ?? []).length;
        const customB = (customCandidates[b.original.mutation] ?? []).length;
        const aMax = Math.max((a.original.candidate_fwd_count ?? 0) + customA, (a.original.candidate_rev_count ?? 0) + customA);
        const bMax = Math.max((b.original.candidate_fwd_count ?? 0) + customB, (b.original.candidate_rev_count ?? 0) + customB);
        return aMax - bMax;
      },
      cell: (info) => {
        const row = info.row.original;
        const customLen = (customCandidates[row.mutation] ?? []).length;
        const fc = (row.candidate_fwd_count ?? 0) + customLen;
        const rc = (row.candidate_rev_count ?? 0) + customLen;
        if (fc <= 0 && rc <= 0) return "—";
        return <span className="text-caption">{fc}/{rc}</span>;
      },
    }),
    col.accessor("has_offtarget", {
      header: "OT",
      size: 40,
      meta: { clickable: true, clickType: "offtarget" },
      cell: (info) => {
        const val = info.getValue();
        if (val == null) return "—";
        return val ? (
          <span className="inline-block px-1 py-0.5 rounded-control text-caption font-medium bg-error/10 text-error">!!</span>
        ) : (
          <span className="inline-block px-1 py-0.5 rounded-control text-caption font-medium bg-success/10 text-success">OK</span>
        );
      },
    }),
    col.display({
      id: "hairpin",
      header: "HP",
      size: 40,
      enableSorting: true,
      sortingFn: (a, b) => {
        const worstA = Math.max(a.original.hairpin_tm_fwd ?? 0, a.original.hairpin_tm_rev ?? 0, a.original.homodimer_tm_fwd ?? 0, a.original.homodimer_tm_rev ?? 0);
        const worstB = Math.max(b.original.hairpin_tm_fwd ?? 0, b.original.hairpin_tm_rev ?? 0, b.original.homodimer_tm_fwd ?? 0, b.original.homodimer_tm_rev ?? 0);
        return worstA - worstB;
      },
      meta: { clickable: true, clickType: "hairpin" },
      cell: (info) => {
        const row = info.row.original;
        const maxHp = Math.max(row.hairpin_tm_fwd ?? 0, row.hairpin_tm_rev ?? 0);
        const maxHd = Math.max(row.homodimer_tm_fwd ?? 0, row.homodimer_tm_rev ?? 0);
        const worst = Math.max(maxHp, maxHd);
        if (worst <= 0) return "—";
        const warn = worst > 40;
        return (
          <span className={`inline-block px-1 py-0.5 rounded-control text-caption font-medium cursor-pointer ${warn ? "bg-warning/10 text-warning" : "bg-muted text-muted-foreground"}`}>
            {worst.toFixed(0)}
          </span>
        );
      },
    }),
    col.accessor("gc_fwd", { header: "GC% F", size: 50, cell: (info) => info.getValue().toFixed(1) }),
    col.accessor("gc_rev", { header: "GC% R", size: 50, cell: (info) => info.getValue().toFixed(1) }),
    col.display({
      id: "synth",
      header: "Syn",
      size: 50,
      enableSorting: true,
      sortingFn: (a, b) => {
        const scoreA = Math.min(a.original.synthesis_score_fwd ?? 100, a.original.synthesis_score_rev ?? 100);
        const scoreB = Math.min(b.original.synthesis_score_fwd ?? 100, b.original.synthesis_score_rev ?? 100);
        return scoreA - scoreB;
      },
      cell: (info) => {
        const row = info.row.original;
        const fwd = row.synthesis_score_fwd ?? 100;
        const rev = row.synthesis_score_rev ?? 100;
        const worst = Math.round(Math.min(fwd, rev));
        const color = worst >= 85 ? "text-success" : worst >= 70 ? "text-warning" : "text-error";
        return <span className={color} title={`Fwd: ${Math.round(fwd)} / Rev: ${Math.round(rev)}`}>{worst}</span>;
      },
    }),
    col.accessor("wt_codon", {
      header: "WT",
      size: 40,
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
    col.accessor("mt_codon", {
      header: "MT",
      size: 40,
      meta: {
        tooltip:
          codonStrategy === "closest"
            ? "Mutant codon (min. nucleotide changes from WT)"
            : "Mutant codon (E. coli optimal)",
      },
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
  ];
}
