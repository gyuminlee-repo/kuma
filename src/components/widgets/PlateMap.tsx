import { useEffect, useMemo, useState } from "react";
import { useAppStore } from "../../store/appStore";
import type { SdmPrimerResult } from "../../types/models";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"];
const COLS = Array.from({ length: 12 }, (_, i) => i + 1);

interface WellEntry {
  well: string;
  label: string;
  sequence: string;
  mutation: string;
  shared?: boolean; // Rev primer shared by multiple mutations
}

function wellName(indexInPlate: number): string {
  const col = Math.floor(indexInPlate / 8) + 1;
  const row = indexInPlate % 8;
  return `${ROWS[row]}${col}`;
}

function useSortedResults(): SdmPrimerResult[] {
  const designResults = useAppStore((s) => s.designResults);
  const tableSorting = useAppStore((s) => s.tableSorting);

  return useMemo(() => {
    if (tableSorting.length === 0) return designResults;
    const sort = tableSorting[0];
    if (sort.id !== "mutation") return designResults;
    const sorted = [...designResults].sort((a, b) => {
      const posA = a.aa_position ?? 0;
      const posB = b.aa_position ?? 0;
      return posA !== posB ? posA - posB : 0;
    });
    return sort.desc ? sorted.reverse() : sorted;
  }, [designResults, tableSorting]);
}

interface PlatePair {
  fwd: Map<string, WellEntry>;
  rev: Map<string, WellEntry>;
  fwdCount: number;
  revCount: number;
}

function buildPlatePairs(sortedResults: SdmPrimerResult[]): PlatePair[] {
  const plateCount = Math.max(1, Math.ceil(sortedResults.length / 96));
  const pairs: PlatePair[] = [];

  for (let p = 0; p < plateCount; p++) {
    const start = p * 96;
    const end = Math.min(start + 96, sortedResults.length);
    const chunk = sortedResults.slice(start, end);

    const fwdGrid = new Map<string, WellEntry>();
    for (let i = 0; i < chunk.length; i++) {
      const r = chunk[i];
      const well = wellName(i);
      fwdGrid.set(well, { well, label: `${r.mutation}_F`, sequence: r.forward_seq, mutation: r.mutation });
    }

    const seenSeq = new Map<string, { firstMut: string; seq: string; mutations: string[] }>();
    for (const r of chunk) {
      const existing = seenSeq.get(r.reverse_seq);
      if (existing) {
        existing.mutations.push(r.mutation);
      } else {
        seenSeq.set(r.reverse_seq, { firstMut: r.mutation, seq: r.reverse_seq, mutations: [r.mutation] });
      }
    }
    const revGrid = new Map<string, WellEntry>();
    let idx = 0;
    for (const [revSeq, info] of seenSeq) {
      const well = wellName(idx++);
      const shared = info.mutations.length > 1;
      revGrid.set(well, {
        well,
        label: `${info.firstMut}_R`,
        sequence: revSeq,
        mutation: info.mutations.join(", "),
        shared,
      });
    }

    pairs.push({ fwd: fwdGrid, rev: revGrid, fwdCount: chunk.length, revCount: seenSeq.size });
  }

  return pairs;
}

function PlateGrid({
  grid,
  color,
}: {
  grid: Map<string, WellEntry>;
  color: "green" | "orange";
}) {
  return (
    <table className="border-collapse text-[9px]">
      <thead>
        <tr>
          <th className="w-4 h-5" />
          {COLS.map((c) => (
            <th key={c} className="w-14 h-5 text-center font-semibold text-gray-500">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ROWS.map((row) => (
          <tr key={row} className="h-6">
            <td className="font-semibold text-gray-500 text-center pr-0.5">{row}</td>
            {COLS.map((col) => {
              const well = `${row}${col}`;
              const entry = grid.get(well);
              const isShared = entry?.shared;

              let cellClass: string;
              if (!entry) {
                cellClass = "bg-white text-gray-200";
              } else if (isShared) {
                cellClass = "bg-blue-100 text-blue-800";
              } else if (color === "green") {
                cellClass = "bg-green-100 text-green-800";
              } else {
                cellClass = "bg-orange-100 text-orange-800";
              }

              return (
                <td
                  key={well}
                  className={`border border-gray-300 text-center px-0.5 py-0.5 rounded-sm ${cellClass}`}
                  title={entry ? `${entry.label}\n${entry.mutation}\n${entry.sequence}` : well}
                >
                  {entry ? (
                    <span className="font-mono truncate block leading-tight">
                      {entry.label.replace(/_[FR]$/, "")}
                    </span>
                  ) : (
                    <span>&middot;</span>
                  )}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function PlateMap() {
  const designResults = useAppStore((s) => s.designResults);
  const sortedResults = useSortedResults();
  const [activeTab, setActiveTab] = useState<"fwd" | "rev">("fwd");
  const [page, setPage] = useState(0);

  const pairs = useMemo(() => buildPlatePairs(sortedResults), [sortedResults]);
  const safeIdx = Math.min(page, Math.max(0, pairs.length - 1));
  const pair = pairs[safeIdx];

  // Reset page when results change
  useEffect(() => setPage(0), [sortedResults]);

  if (designResults.length === 0 || !pair) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-xs">
        Plate map will appear after primer design
      </div>
    );
  }

  const totalRevCount = pairs.reduce((s, p) => s + p.revCount, 0);

  return (
    <div className="h-full overflow-auto p-2">
      {/* Tab row: Fwd | Rev | ← Plate N/M → */}
      <div className="flex items-center gap-1 mb-2">
        <button
          className={`px-3 py-1 text-[10px] font-semibold rounded-t border border-b-0 ${
            activeTab === "fwd"
              ? "bg-green-50 text-green-700 border-green-300"
              : "bg-gray-50 text-gray-500 border-gray-300 hover:bg-gray-100"
          }`}
          onClick={() => setActiveTab("fwd")}
        >
          Forward ({pair.fwdCount})
        </button>
        <button
          className={`px-3 py-1 text-[10px] font-semibold rounded-t border border-b-0 ${
            activeTab === "rev"
              ? "bg-orange-50 text-orange-700 border-orange-300"
              : "bg-gray-50 text-gray-500 border-gray-300 hover:bg-gray-100"
          }`}
          onClick={() => setActiveTab("rev")}
        >
          Reverse ({pair.revCount})
        </button>

        {pairs.length > 1 && (
          <div className="flex items-center gap-1 text-[10px] ml-2">
            <button
              className="px-1.5 py-0.5 rounded border border-gray-300 hover:bg-gray-100 disabled:opacity-30"
              disabled={safeIdx === 0}
              onClick={() => setPage(safeIdx - 1)}
            >
              ‹
            </button>
            <span className="text-gray-500">
              Plate {safeIdx + 1}/{pairs.length}
            </span>
            <button
              className="px-1.5 py-0.5 rounded border border-gray-300 hover:bg-gray-100 disabled:opacity-30"
              disabled={safeIdx >= pairs.length - 1}
              onClick={() => setPage(safeIdx + 1)}
            >
              ›
            </button>
          </div>
        )}
      </div>

      {/* Fixed-height grid — always 8 rows × 12 cols */}
      {activeTab === "fwd" ? (
        <PlateGrid grid={pair.fwd} color="green" />
      ) : (
        <PlateGrid grid={pair.rev} color="orange" />
      )}

      <div className="flex items-center gap-3 text-[10px] text-gray-400 mt-1">
        <span>Total: {sortedResults.length} fwd / {totalRevCount} rev</span>
        {activeTab === "rev" && (
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-blue-100 border border-blue-300 rounded-sm inline-block" />
            shared (multiple mutations)
          </span>
        )}
      </div>
    </div>
  );
}
