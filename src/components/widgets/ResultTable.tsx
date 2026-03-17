import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useAppStore } from "../../store/appStore";
import type { SdmPrimerResult } from "../../types/models";

const col = createColumnHelper<SdmPrimerResult & { rank: number }>();

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

/** Forward primer with overlap(blue) + mutation(red) + downstream(black) coloring */
function ColoredFwdSeq({ seq, overlapLen }: {
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

/** Candidate comparison popover */
function CandidatePopover({
  mutation,
  current,
  onClose,
}: {
  mutation: string;
  current: SdmPrimerResult;
  onClose: () => void;
}) {
  const [candidates, setCandidates] = useState<SdmPrimerResult[] | null>(null);
  const [loading, setLoading] = useState(true);
  const getAlternatives = useAppStore((s) => s.getAlternatives);
  const swapPrimer = useAppStore((s) => s.swapPrimer);

  // Load candidates on mount
  useEffect(() => {
    getAlternatives(mutation).then((c) => {
      setCandidates(c);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [mutation, getAlternatives]);

  async function handleSwap(idx: number) {
    await swapPrimer(mutation, idx);
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl p-4 max-w-3xl max-h-[80vh] overflow-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold">
            {mutation} — {candidates?.length ?? "..."} candidates
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-lg px-2"
          >
            ×
          </button>
        </div>

        {loading ? (
          <div className="text-xs text-gray-400 py-4 text-center">Loading...</div>
        ) : !candidates || candidates.length === 0 ? (
          <div className="text-xs text-gray-400 py-4 text-center">No candidates</div>
        ) : (
          <table className="w-full text-[10px] border-collapse">
            <thead>
              <tr className="bg-gray-50 text-gray-600 font-semibold">
                <th className="px-2 py-1 text-left">#</th>
                <th className="px-2 py-1 text-left">Forward</th>
                <th className="px-2 py-1 text-left">Reverse</th>
                <th className="px-2 py-1">Fwd</th>
                <th className="px-2 py-1">Rev</th>
                <th className="px-2 py-1">Tm F</th>
                <th className="px-2 py-1">Tm R</th>
                <th className="px-2 py-1">Tm Ov</th>
                <th className="px-2 py-1">GC% F</th>
                <th className="px-2 py-1">GC% R</th>
                <th className="px-2 py-1">Tol</th>
                <th className="px-2 py-1">Pen</th>
                <th className="px-2 py-1"></th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, idx) => {
                const isCurrent = c.forward_seq === current.forward_seq
                  && c.reverse_seq === current.reverse_seq;
                return (
                  <tr
                    key={idx}
                    className={`border-b border-gray-100 ${isCurrent ? "bg-green-50 font-semibold" : "hover:bg-gray-50"}`}
                  >
                    <td className="px-2 py-1 text-center">{idx + 1}</td>
                    <td className="px-2 py-1 font-mono break-all max-w-[160px]">
                      <ColoredFwdSeq seq={c.forward_seq} overlapLen={c.overlap_len ?? 0} />
                    </td>
                    <td className="px-2 py-1 font-mono break-all max-w-[140px]">{c.reverse_seq}</td>
                    <td className="px-2 py-1 text-center">{c.fwd_len}</td>
                    <td className="px-2 py-1 text-center">{c.rev_len}</td>
                    <td className="px-2 py-1 text-center">{c.tm_no_fwd.toFixed(1)}</td>
                    <td className="px-2 py-1 text-center">{c.tm_no_rev.toFixed(1)}</td>
                    <td className="px-2 py-1 text-center">{c.tm_overlap.toFixed(1)}</td>
                    <td className="px-2 py-1 text-center">{c.gc_fwd.toFixed(1)}</td>
                    <td className="px-2 py-1 text-center">{c.gc_rev.toFixed(1)}</td>
                    <td className="px-2 py-1 text-center">{`\u00B1${c.tolerance_used.toFixed(1)}`}</td>
                    <td className="px-2 py-1 text-center">{c.penalty.toFixed(1)}</td>
                    <td className="px-2 py-1 text-center">
                      {isCurrent ? (
                        <span className="text-green-600 text-[9px]">current</span>
                      ) : (
                        <button
                          className="px-2 py-0.5 bg-blue-500 text-white rounded text-[9px] hover:bg-blue-600"
                          onClick={() => handleSwap(idx)}
                        >
                          Use
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

const HEADER_TOOLTIPS: Record<string, string> = {
  rank: "Input order (EVOLVEpro: y_pred descending rank)",
  mutation: "Amino acid substitution. Click header to sort by aa position",
  forward_seq: "Full forward primer (overlap + mutation codon + downstream). Click to compare candidates",
  reverse_seq: "Full reverse primer. Click to compare candidates",
  fwd_len: "Forward primer length (bp)",
  rev_len: "Reverse primer length (bp)",
  tm_no_fwd: "Forward whole-primer Tm (SantaLucia 1998)",
  tm_no_rev: "Reverse whole-primer Tm (SantaLucia 1998)",
  tm_overlap: "Overlap region Tm - should be lower than Fwd/Rev Tm",
  tolerance_used: "Tm tolerance applied (starts at +/-0.5, widens by 0.5 up to +/-3.0)",
  penalty: "Sum of Tm deviations + GC% penalty (lower is better)",
  candidate_count: "Number of alternative primer candidates for this mutation",
  has_offtarget: "Off-target binding detected on template strand",
  gc_fwd: "Forward primer GC content (40-60% recommended)",
  gc_rev: "Reverse primer GC content (40-60% recommended)",
  wt_codon: "Wild-type codon at this position",
  mt_codon: "Mutant codon (E. coli optimal)",
};

function makeColumns(groupColorMap: Map<number, string>) {
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
        return (
          <span className="font-mono font-medium">
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
        );
      },
    }),
    col.accessor("forward_seq", {
      header: "Forward Primer",
      size: 220,
      enableSorting: false,
      meta: { clickable: true },
      cell: (info) => {
        const row = info.row.original;
        return (
          <ColoredFwdSeq
            seq={info.getValue()}
            overlapLen={row.overlap_len ?? 0}
          />
        );
      },
    }),
    col.accessor("reverse_seq", {
      header: "Reverse Primer",
      size: 200,
      enableSorting: false,
      meta: { clickable: true },
      cell: (info) => (
        <span className="font-mono text-[10px] break-all">
          {info.getValue()}
        </span>
      ),
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
      size: 50,
      cell: (info) => {
        const val = info.getValue();
        return val != null ? `\u00B1${val.toFixed(1)}` : "\u2014";
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
      size: 42,
      enableSorting: false,
      cell: (info) => {
        const val = info.getValue();
        return val != null && val > 0 ? val : "\u2014";
      },
    }),
    col.accessor("has_offtarget", {
      header: "OT",
      size: 40,
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
    col.accessor("wt_codon", {
      header: "WT",
      size: 40,
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
    col.accessor("mt_codon", {
      header: "MT",
      size: 40,
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
  ];
}

export function ResultTable() {
  const designResults = useAppStore((s) => s.designResults);
  const failedMutations = useAppStore((s) => s.failedMutations);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [popover, setPopover] = useState<{ mutation: string; current: SdmPrimerResult } | null>(null);

  const rankedData = useMemo(
    () => designResults.map((r, i) => ({ ...r, rank: i + 1 })),
    [designResults],
  );

  const groupColorMap = useMemo(
    () => buildGroupColorMap(designResults),
    [designResults],
  );

  const columns = useMemo(
    () => makeColumns(groupColorMap),
    [groupColorMap],
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
    }
  }, []);

  if (designResults.length === 0) {
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
                  title={HEADER_TOOLTIPS[header.column.id] ?? ""}
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
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className="hover:bg-green-50 border-b border-gray-100"
            >
              {row.getVisibleCells().map((cell) => {
                const isClickable = !!(cell.column.columnDef.meta as Record<string, boolean> | undefined)?.clickable;
                return (
                  <td
                    key={cell.id}
                    className={`px-2 py-1 ${isClickable ? "cursor-pointer hover:bg-blue-50" : ""}`}
                    onClick={isClickable ? () => handleCellClick(row.original, cell.column.id) : undefined}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                );
              })}
            </tr>
          ))}
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
                className="bg-red-100 px-1.5 py-0.5 rounded cursor-help"
                title={`#${f.rank} | ${f.reason}`}
              >
                #{f.rank} {f.mutation}
              </span>
            ))}
          </div>
        </div>
      )}

      {designResults.length > 0 && (
        <div className="border-t border-gray-200 bg-gray-50 px-3 py-1.5 text-[10px] text-gray-500">
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
    </div>
  );
}
