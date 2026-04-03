import { useCallback, useMemo, useState, type MouseEvent } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useAppStore } from "../../store/appStore";
import type { SdmPrimerResult, FailedMutation, RescuedMutation } from "../../types/models";
import { CandidatePopover } from "./popovers/CandidatePopover";
import { HairpinDetail } from "./popovers/HairpinDetail";
import { OffTargetDetail } from "./popovers/OffTargetDetail";
import { FailedMutationPopover } from "./popovers/FailedMutationPopover";

const col = createColumnHelper<SdmPrimerResult & { rank: number }>();

export function formatTolerance(tf?: number, tr?: number, fallback?: number): string {
  if (tf != null && tr != null) return `\u00B1${tf.toFixed(1)}/\u00B1${tr.toFixed(1)}`;
  if (fallback != null) return `\u00B1${fallback.toFixed(1)}`;
  return "\u2014";
}

const GROUP_COLORS = [
  "#3b82f6", "#ef4444", "#f59e0b", "#10b981",
  "#8b5cf6", "#ec4899", "#06b6d4", "#f97316",
];

function buildGroupColorMap(results: SdmPrimerResult[]): Map<number, string> {
  const posCount = new Map<number, number>();
  for (const r of results) {
    const pos = r.aa_position;
    if (pos != null) {
      posCount.set(pos, (posCount.get(pos) ?? 0) + 1);
    }
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

function CopySeqButton({ seq }: { seq: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = (e: MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(seq).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };
  return (
    <button
      className="ml-1 flex-shrink-0 text-gray-300 hover:text-gray-600 text-[10px] leading-none"
      onClick={handleCopy}
      title="Copy sequence"
      aria-label="Copy sequence to clipboard"
    >
      {copied ? "\u2713" : "\uD83D\uDCCB"}
    </button>
  );
}

/** Forward primer with overlap(blue) + mutation(red) + downstream(black) coloring */
export function ColoredFwdSeq({ seq, overlapLen }: {
  seq: string;
  overlapLen: number;
}) {
  const overlap = seq.slice(0, overlapLen);
  const codon = seq.slice(overlapLen, overlapLen + 3);
  const rest = seq.slice(overlapLen + 3);

  return (
    <span className="font-mono text-[10px] break-all">
      <span style={{ color: "#3b82f6" }}>{overlap}</span>
      <span style={{ color: "#ef4444", fontWeight: 600 }}>{codon}</span>
      <span>{rest}</span>
    </span>
  );
}

const HEADER_TOOLTIPS: Record<string, string> = {
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

function makeColumns(opts: {
  groupColorMap: Map<number, string>;
  codonStrategy: "closest" | "optimal";
  swapped: Record<string, string>;
  customCandidates: Record<string, SdmPrimerResult[]>;
  rescuedMutations: string[];
  rescueDetailMap: Map<string, RescuedMutation>;
  removeDesignResult: (mutation: string, reason: string) => void;
  yPredMap: Record<string, number>;
}) {
  const { groupColorMap, codonStrategy, swapped, customCandidates, rescuedMutations, rescueDetailMap, removeDesignResult, yPredMap } = opts;
  return [
    col.accessor("rank", {
      header: "#",
      size: 35,
      enableSorting: false,
      cell: (info) => (
        <span className="text-gray-400">{info.getValue()}</span>
      ),
    }),
    col.accessor("mutation", {
      header: "Mutation",
      size: 90,
      sortingFn: (a, b) => {
        const posA = a.original.aa_position ?? 0;
        const posB = b.original.aa_position ?? 0;
        if (posA !== posB) return posA - posB;
        return a.original.rank - b.original.rank;
      },
      cell: (info) => {
        const row = info.row.original;
        const color = row.aa_position != null ? groupColorMap.get(row.aa_position) : undefined;
        const isRescued = rescuedMutations.includes(row.mutation);
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
                {rescueDetail.type === "pool_cascade"
                  ? `\u21BB ${rescueDetail.original}`
                  : "\u26A1 relaxed"}
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
    ...(Object.keys(yPredMap).length > 0 ? [col.accessor((row) => yPredMap[row.mutation] ?? -Infinity, {
      id: "y_pred",
      header: "y_pred",
      size: 65,
      sortingFn: "basic",
      cell: (info) => {
        const val = info.getValue();
        return val > -Infinity ? (
          <span className="text-gray-500">{val.toFixed(3)}</span>
        ) : <span className="text-gray-300">—</span>;
      },
    })] : []),
    col.accessor("forward_seq", {
      header: "Forward Primer",
      size: 220,
      enableSorting: false,
      meta: { clickable: true },
      cell: (info) => {
        const row = info.row.original;
        const sw = swapped[row.mutation];
        const fwdEdited = sw === "fwd" || sw === "both";
        return (
          <span className={`flex items-center ${fwdEdited ? "bg-amber-100 rounded px-0.5" : ""}`}>
            <span className="flex-1 min-w-0">
              <ColoredFwdSeq
                seq={info.getValue()}
                overlapLen={row.overlap_len ?? 0}
              />
            </span>
            <CopySeqButton seq={info.getValue()} />
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
        const sw = swapped[info.row.original.mutation];
        const revEdited = sw === "rev" || sw === "both";
        return (
          <span className={`flex items-center font-mono text-[10px] ${revEdited ? "bg-amber-100 rounded px-0.5" : ""}`}>
            <span className="flex-1 min-w-0 break-all">{info.getValue()}</span>
            <CopySeqButton seq={info.getValue()} />
          </span>
        );
      },
    }),
    col.accessor("fwd_len", {
      header: "Fwd",
      size: 40,
    }),
    col.accessor("rev_len", {
      header: "Rev",
      size: 40,
    }),
    col.accessor("tm_no_fwd", {
      header: "Tm F",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("tm_no_rev", {
      header: "Tm R",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("tm_overlap", {
      header: "Tm Ov",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
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
          <span
            className={`inline-block px-1 py-0.5 rounded text-[10px] font-medium cursor-pointer ${
              warn ? "bg-yellow-100 text-yellow-800" : "bg-gray-50 text-gray-400"
            }`}
          >
            {worst.toFixed(0)}
          </span>
        );
      },
    }),
    col.accessor("gc_fwd", {
      header: "GC% F",
      size: 50,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("gc_rev", {
      header: "GC% R",
      size: 50,
      cell: (info) => info.getValue().toFixed(1),
    }),
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
        tooltip: codonStrategy === "closest"
          ? "Mutant codon (min. nucleotide changes from WT)"
          : "Mutant codon (E. coli optimal)",
      },
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
  ];
}

export function ResultTable() {
  const designResults = useAppStore((s) => s.designResults);
  const failedMutations = useAppStore((s) => s.failedMutations);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const sorting = useAppStore((s) => s.tableSorting);
  const setSorting = useAppStore((s) => s.setTableSorting);
  const [popover, setPopover] = useState<{ mutation: string; current: SdmPrimerResult } | null>(null);
  const [hpDetail, setHpDetail] = useState<SdmPrimerResult | null>(null);
  const [otDetail, setOtDetail] = useState<SdmPrimerResult | null>(null);
  const [failedPopover, setFailedPopover] = useState<FailedMutation | null>(null);

  const rankedData = useMemo(
    () => designResults.map((r, i) => ({ ...r, rank: i + 1 })),
    [designResults],
  );

  const groupColorMap = useMemo(
    () => buildGroupColorMap(designResults),
    [designResults],
  );

  const codonStrategy = useAppStore((s) => s.codonStrategy);
  const manuallySwapped = useAppStore((s) => s.manuallySwapped);
  const customCandidatesAll = useAppStore((s) => s.customCandidates);
  const rescuedMutations = useAppStore((s) => s.rescuedMutations);
  const rescuedMutationDetails = useAppStore((s) => s.rescuedMutationDetails);
  const rescueDetailMap = useMemo(
    () => new Map(rescuedMutationDetails.map((r) => [r.rescued_by, r])),
    [rescuedMutationDetails],
  );
  const removeDesignResult = useAppStore((s) => s.removeDesignResult);
  const yPredMap = useAppStore((s) => s.yPredMap);
  const columns = useMemo(
    () => makeColumns({ groupColorMap, codonStrategy, swapped: manuallySwapped, customCandidates: customCandidatesAll, rescuedMutations, rescueDetailMap, removeDesignResult, yPredMap }),
    [groupColorMap, codonStrategy, manuallySwapped, customCandidatesAll, rescuedMutations, rescueDetailMap, removeDesignResult, yPredMap],
  );

  const table = useReactTable({
    data: rankedData,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const handleCellClick = useCallback((row: SdmPrimerResult & { rank: number }, columnId: string) => {
    if (columnId === "forward_seq" || columnId === "reverse_seq") {
      setPopover({ mutation: row.mutation, current: row });
    } else if (columnId === "hairpin") {
      const worst = Math.max(row.hairpin_tm_fwd ?? 0, row.hairpin_tm_rev ?? 0, row.homodimer_tm_fwd ?? 0, row.homodimer_tm_rev ?? 0);
      if (worst > 0) setHpDetail(row);
    } else if (columnId === "has_offtarget" && row.has_offtarget) {
      setOtDetail(row);
    }
  }, []);

  if (designResults.length === 0) {
    if (totalCount > 0 && failedMutations.length > 0) {
      return (
        <div className="h-full overflow-auto p-4">
          <div className="text-sm text-red-600 font-semibold mb-2">
            All {totalCount} mutations failed
          </div>
          <div className="text-[10px] text-red-600 font-mono flex flex-wrap gap-1">
            {failedMutations.map((f) => (
              <span
                key={f.mutation}
                className="bg-red-100 px-1.5 py-0.5 rounded cursor-pointer hover:bg-red-200"
                title={`#${f.rank} | ${f.reason}`}
                onClick={() => setFailedPopover(f)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && setFailedPopover(f)}
              >
                #{f.rank} {f.mutation}
              </span>
            ))}
          </div>
          {failedPopover && (
            <FailedMutationPopover
              failed={failedPopover}
              onClose={() => setFailedPopover(null)}
            />
          )}
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Load a sequence file (FASTA / SnapGene) and enter mutations to design SDM primers
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-gray-50 z-10">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className={`px-2 py-1.5 text-left font-semibold text-gray-600 border-b border-gray-300 ${
                    header.column.getCanSort() ? "cursor-pointer select-none hover:bg-gray-100" : ""
                  }`}
                  style={{ width: header.getSize() }}
                  title={(header.column.columnDef.meta as Record<string, string> | undefined)?.tooltip ?? HEADER_TOOLTIPS[header.column.id] ?? ""}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(
                    header.column.columnDef.header,
                    header.getContext(),
                  )}
                  {header.column.getIsSorted() === "asc" ? " \u25B2" : ""}
                  {header.column.getIsSorted() === "desc" ? " \u25BC" : ""}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const isSwapped = !!manuallySwapped[row.original.mutation];
            return (
            <tr
              key={row.id}
              className={`hover:bg-gray-50 border-b border-gray-100 ${isSwapped ? "border-l-3 border-l-amber-400" : ""}`}
            >
              {row.getVisibleCells().map((cell) => {
                const meta = cell.column.columnDef.meta as Record<string, unknown> | undefined;
                const showClickable = !!meta?.clickable;
                return (
                  <td
                    key={cell.id}
                    className={`px-2 py-1 ${showClickable ? "cursor-pointer hover:bg-amber-50" : ""}`}
                    onClick={showClickable ? () => handleCellClick(row.original, cell.column.id) : undefined}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                );
              })}
            </tr>
          );
          })}
        </tbody>
      </table>

      {failedMutations.length > 0 && (
        <div className="border-t border-gray-200 bg-red-50 px-3 py-2">
          <div className="text-xs font-semibold text-red-700 mb-1">
            Failed ({failedMutations.length}/{totalCount})
          </div>
          <div className="text-[10px] text-red-600 font-mono flex flex-wrap gap-1">
            {failedMutations.map((f) => (
              <span
                key={f.mutation}
                className="bg-red-100 px-1.5 py-0.5 rounded cursor-pointer hover:bg-red-200"
                title={`#${f.rank} | ${f.reason}`}
                onClick={() => setFailedPopover(f)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && setFailedPopover(f)}
              >
                #{f.rank} {f.mutation}
              </span>
            ))}
          </div>
        </div>
      )}

      {designResults.length > 0 && (
        <div className="border-t border-gray-200 bg-gray-50 px-3 py-1.5 text-[10px] text-gray-400">
          {successCount}/{totalCount} designed
          {failedMutations.length > 0 && ` | ${failedMutations.length} failed`}
        </div>
      )}

      {popover && (
        <CandidatePopover
          mutation={popover.mutation}
          current={popover.current}
          onClose={() => setPopover(null)}
        />
      )}

      {hpDetail && (
        <HairpinDetail
          result={hpDetail}
          onClose={() => setHpDetail(null)}
        />
      )}

      {otDetail && (
        <OffTargetDetail
          result={otDetail}
          onClose={() => setOtDetail(null)}
        />
      )}

      {failedPopover && (
        <FailedMutationPopover
          failed={failedPopover}
          onClose={() => setFailedPopover(null)}
        />
      )}
    </div>
  );
}
