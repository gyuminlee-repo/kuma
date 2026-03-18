import { useEffect, useMemo, useState } from "react";
import { useAppStore } from "../../store/appStore";
import type { PlateMapping } from "../../types/models";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"];
const COLS = Array.from({ length: 12 }, (_, i) => i + 1);

function wellName(indexInPlate: number): string {
  const col = Math.floor(indexInPlate / 8) + 1;
  const row = indexInPlate % 8;
  return `${ROWS[row]}${col}`;
}

interface WellEntry {
  well: string;
  label: string;
  sequence: string;
  mutation: string;
  shared?: boolean;
}

interface PlatePair {
  fwd: Map<string, WellEntry>;
  rev: Map<string, WellEntry>;
  fwdCount: number;
  revCount: number;
}

function toWellEntry(m: PlateMapping, shared: boolean): WellEntry {
  return {
    well: m.well,
    label: m.primer_name,
    sequence: m.sequence,
    mutation: m.mutation,
    shared,
  };
}

function buildPairsFromStore(
  mappings: PlateMapping[],
  dedupInfo: Record<string, string[]>,
  sortedMutations: string[] | null,
): PlatePair[] {
  const fwdAll = mappings.filter((m) => m.primer_type === "forward");
  const revAll = mappings.filter((m) => m.primer_type === "reverse");

  // Reorder fwd by sorted mutation order if provided
  let orderedFwd = fwdAll;
  if (sortedMutations && sortedMutations.length > 0) {
    const fwdByMut = new Map<string, PlateMapping>();
    for (const m of fwdAll) fwdByMut.set(m.mutation, m);
    const reordered: PlateMapping[] = [];
    for (const mut of sortedMutations) {
      const m = fwdByMut.get(mut);
      if (m) reordered.push(m);
    }
    // Reassign well names based on new order
    orderedFwd = reordered.map((m, i) => ({ ...m, well: wellName(i) }));
  }

  // Reorder rev: deduplicate in order of first occurrence in orderedFwd
  let orderedRev = revAll;
  if (sortedMutations && sortedMutations.length > 0) {
    const seenRevSeq = new Map<string, PlateMapping>();
    for (const fwd of orderedFwd) {
      // Find the rev mapping with the same mutation
      const rev = revAll.find((r) => dedupInfo[r.sequence]?.includes(fwd.mutation));
      if (rev && !seenRevSeq.has(rev.sequence)) {
        seenRevSeq.set(rev.sequence, rev);
      }
    }
    let revIdx = 0;
    orderedRev = [...seenRevSeq.values()].map((m) => ({ ...m, well: wellName(revIdx++) }));
  }

  // Determine shared reverse sequences
  const sharedSeqs = new Set<string>();
  for (const [seq, muts] of Object.entries(dedupInfo)) {
    if (muts.length > 1) sharedSeqs.add(seq);
  }

  function chunkByPlate(items: PlateMapping[]): PlateMapping[][] {
    const plates: PlateMapping[][] = [];
    let current: PlateMapping[] = [];
    for (const m of items) {
      current.push(m);
      if (current.length >= 96) {
        plates.push(current);
        current = [];
      }
    }
    if (current.length > 0) plates.push(current);
    return plates.length > 0 ? plates : [[]];
  }

  const fwdPlates = chunkByPlate(orderedFwd);

  // Build mutation → rev sequence lookup from dedupInfo
  const mutToRevSeq = new Map<string, string>();
  for (const [seq, muts] of Object.entries(dedupInfo)) {
    for (const mut of muts) mutToRevSeq.set(mut, seq);
  }
  const revBySeq = new Map<string, PlateMapping>();
  for (const r of orderedRev) revBySeq.set(r.sequence, r);

  const pairs: PlatePair[] = [];
  for (let i = 0; i < fwdPlates.length; i++) {
    const fwdChunk = fwdPlates[i] ?? [];

    // Collect rev primers paired with this plate's fwd mutations (deduplicated, fwd order)
    const seenRevSeq = new Set<string>();
    const revChunk: PlateMapping[] = [];
    for (const fwd of fwdChunk) {
      const revSeq = mutToRevSeq.get(fwd.mutation);
      if (revSeq && !seenRevSeq.has(revSeq)) {
        seenRevSeq.add(revSeq);
        const revEntry = revBySeq.get(revSeq);
        if (revEntry) revChunk.push(revEntry);
      }
    }

    const fwdGrid = new Map<string, WellEntry>();
    fwdChunk.forEach((m, idx) => {
      const key = wellName(idx);
      fwdGrid.set(key, toWellEntry({ ...m, well: key }, false));
    });

    const revGrid = new Map<string, WellEntry>();
    revChunk.forEach((m, idx) => {
      const key = wellName(idx);
      revGrid.set(key, toWellEntry({ ...m, well: key }, sharedSeqs.has(m.sequence)));
    });

    pairs.push({ fwd: fwdGrid, rev: revGrid, fwdCount: fwdChunk.length, revCount: revChunk.length });
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
                      {entry.label}
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

function useSortedMutations(): string[] | null {
  const designResults = useAppStore((s) => s.designResults);
  const tableSorting = useAppStore((s) => s.tableSorting);

  return useMemo(() => {
    if (tableSorting.length === 0) return null;
    const sort = tableSorting[0];
    if (sort.id !== "mutation") return null;
    const sorted = [...designResults].sort((a, b) => {
      const posA = a.aa_position ?? 0;
      const posB = b.aa_position ?? 0;
      return posA - posB;
    });
    const ordered = sort.desc ? sorted.reverse() : sorted;
    return ordered.map((r) => r.mutation);
  }, [designResults, tableSorting]);
}

export function PlateMap() {
  const plateMappings = useAppStore((s) => s.plateMappings);
  const dedupInfo = useAppStore((s) => s.dedupInfo);
  const sortedMutations = useSortedMutations();
  const [activeTab, setActiveTab] = useState<"fwd" | "rev">("fwd");
  const [page, setPage] = useState(0);

  const pairs = useMemo(() => buildPairsFromStore(plateMappings, dedupInfo, sortedMutations), [plateMappings, dedupInfo, sortedMutations]);
  const safeIdx = Math.min(page, Math.max(0, pairs.length - 1));
  const pair = pairs[safeIdx];

  // Reset page when mappings change
  useEffect(() => setPage(0), [plateMappings]);

  if (plateMappings.length === 0 || !pair) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-xs">
        Plate map will appear after primer design
      </div>
    );
  }

  const totalFwd = pairs.reduce((s, p) => s + p.fwdCount, 0);
  const totalRev = pairs.reduce((s, p) => s + p.revCount, 0);

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

      {activeTab === "fwd" ? (
        <PlateGrid grid={pair.fwd} color="green" />
      ) : (
        <PlateGrid grid={pair.rev} color="orange" />
      )}

      <div className="flex items-center gap-3 text-[10px] text-gray-400 mt-1">
        <span>Total: {totalFwd} fwd / {totalRev} rev</span>
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
