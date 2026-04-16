import { useState, type MouseEvent } from "react";
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

export function buildGroupColorMap(results: SdmPrimerResult[]): Map<number, string> {
  const posCount = new Map<number, number>();
  for (const r of results) {
    const pos = r.aa_position;
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

export function makeResultTableColumns(opts: {
  groupColorMap: Map<number, string>;
  codonStrategy: "closest" | "optimal";
  swapped: Record<string, string>;
  customCandidates: Record<string, SdmPrimerResult[]>;
  rescuedMutations: Set<string>;
  rescueDetailMap: Map<string, RescuedMutation>;
  removeDesignResult: (mutation: string, reason: string) => void;
  yPredMap: Record<string, number>;
}) {
  const {
    groupColorMap,
    codonStrategy,
    swapped,
    customCandidates,
    rescuedMutations,
    rescueDetailMap,
    removeDesignResult,
    yPredMap,
  } = opts;

  return [
    col.display({
      id: "rank",
      header: "#",
      size: 35,
      enableSorting: false,
      cell: (info) => <span className="text-gray-400">{info.row.index + 1}</span>,
    }),
    col.accessor("mutation", {
      header: "Mutation",
      size: 90,
      sortingFn: (a, b) => {
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
                  className="inline-block ml-1 px-1 rounded text-[8px] font-semibold text-white align-middle"
                  style={{ backgroundColor: color }}
                >
                  Pos{row.aa_position}
                </span>
              )}
            </span>
            {rescueDetail && (
              <span
                className={`ml-1 px-1 py-0.5 rounded text-[8px] leading-none ${
                  rescueDetail.type === "pool_cascade"
                    ? "bg-green-100 text-green-700"
                    : "bg-amber-100 text-amber-700"
                }`}
                title={
                  rescueDetail.type === "pool_cascade"
                    ? `Pool cascade: replaced ${rescueDetail.original}`
                    : "Auto-relax: widened Tm tolerance and GC range"
                }
              >
                {rescueDetail.type === "pool_cascade" ? `\u21BB ${rescueDetail.original}` : "\u26A1 relaxed"}
              </span>
            )}
            {isRescued && !rescueDetail && (
              <button
                className="ml-1 px-1 py-0.5 bg-red-100 text-red-600 rounded text-[8px] hover:bg-red-200 leading-none"
                title="Remove custom rescue — restore to Failed"
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
                <span className="text-gray-500">{val.toFixed(3)}</span>
              ) : (
                <span className="text-gray-300">—</span>
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
          <span className={`flex items-center ${fwdEdited ? "bg-amber-100 rounded px-0.5" : ""}`}>
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
          <span className={`flex items-center font-mono text-[10px] ${revEdited ? "bg-amber-100 rounded px-0.5" : ""}`}>
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
    col.accessor("tm_overlap", { header: "Tm Ov", size: 55, cell: (info) => info.getValue().toFixed(1) }),
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
        return val != null ? val.toFixed(1) : "\u2014";
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
        if (fc <= 0 && rc <= 0) return "\u2014";
        return <span className="text-[10px]">{fc}/{rc}</span>;
      },
    }),
    col.accessor("has_offtarget", {
      header: "OT",
      size: 40,
      meta: { clickable: true, clickType: "offtarget" },
      cell: (info) => {
        const val = info.getValue();
        if (val == null) return "\u2014";
        return val ? (
          <span className="inline-block px-1 py-0.5 rounded text-[10px] font-medium bg-red-100 text-red-700">!!</span>
        ) : (
          <span className="inline-block px-1 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">OK</span>
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
        if (worst <= 0) return "\u2014";
        const warn = worst > 40;
        return (
          <span className={`inline-block px-1 py-0.5 rounded text-[10px] font-medium cursor-pointer ${warn ? "bg-yellow-100 text-yellow-800" : "bg-gray-50 text-gray-400"}`}>
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
        const color = worst >= 85 ? "text-green-600" : worst >= 70 ? "text-amber-600" : "text-red-600";
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
