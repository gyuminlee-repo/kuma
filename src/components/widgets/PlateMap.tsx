import { useEffect, useMemo, useState } from "react";
import { useAppStore } from "../../store/appStore";
import type { PlateMapping } from "../../types/models";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"];
const COLS = Array.from({ length: 12 }, (_, i) => i + 1);

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
): PlatePair[] {
  const fwdAll = mappings.filter((m) => m.primer_type === "forward");
  const revAll = mappings.filter((m) => m.primer_type === "reverse");

  // Determine shared reverse sequences
  const sharedSeqs = new Set<string>();
  for (const [seq, muts] of Object.entries(dedupInfo)) {
    if (muts.length > 1) sharedSeqs.add(seq);
  }

  // Split into 96-well plates by well prefix (P2- etc.)
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

  const fwdPlates = chunkByPlate(fwdAll);
  const revPlates = chunkByPlate(revAll);
  const plateCount = Math.max(fwdPlates.length, revPlates.length);

  const pairs: PlatePair[] = [];
  for (let i = 0; i < plateCount; i++) {
    const fwdChunk = fwdPlates[i] ?? [];
    const revChunk = revPlates[i] ?? [];

    const fwdGrid = new Map<string, WellEntry>();
    for (const m of fwdChunk) {
      fwdGrid.set(m.well, toWellEntry(m, false));
    }

    const revGrid = new Map<string, WellEntry>();
    for (const m of revChunk) {
      revGrid.set(m.well, toWellEntry(m, sharedSeqs.has(m.sequence)));
    }

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
  const plateMappings = useAppStore((s) => s.plateMappings);
  const dedupInfo = useAppStore((s) => s.dedupInfo);
  const [activeTab, setActiveTab] = useState<"fwd" | "rev">("fwd");
  const [page, setPage] = useState(0);

  const pairs = useMemo(() => buildPairsFromStore(plateMappings, dedupInfo), [plateMappings, dedupInfo]);
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
