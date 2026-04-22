import { useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import { reorderMappings, getSortedMutations, wellName } from "../../lib/plate-utils";
import type { PlateMapping } from "../../types/models";
import { Button } from "../ui/button";
import { MappingExportDialog } from "../dialogs/MappingExportDialog";
import { handleExportMappingWithParams } from "../layout/export-handlers";

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
  sortedMutations: string[] | null,
): PlatePair[] {
  // Apply sort + well reassignment via shared utility
  const ordered = reorderMappings(mappings, dedupInfo, sortedMutations);
  const orderedFwd: PlateMapping[] = [];
  const orderedRev: PlateMapping[] = [];
  for (const mapping of ordered) {
    if (mapping.primer_type === "forward") {
      orderedFwd.push(mapping);
    } else {
      orderedRev.push(mapping);
    }
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
    <table className="border-separate border-spacing-1 text-[9px]">
      <thead>
        <tr>
          <th className="w-4 h-5" />
          {COLS.map((c) => (
            <th key={c} className="h-5 w-14 text-center text-[10px] font-semibold text-slate-500">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ROWS.map((row) => (
          <tr key={row} className="h-6">
            <td className="pr-0.5 text-center text-[10px] font-semibold text-slate-500">{row}</td>
            {COLS.map((col) => {
              const well = `${row}${col}`;
              const entry = grid.get(well);
              const isShared = entry?.shared;

              let cellClass: string;
              if (!entry) {
                cellClass = "border-slate-200 bg-white/80 text-slate-200";
              } else if (isShared) {
                cellClass = "border-blue-200 bg-blue-50 text-blue-800 shadow-sm";
              } else if (color === "green") {
                cellClass = "border-emerald-200 bg-emerald-50 text-emerald-800 shadow-sm";
              } else {
                cellClass = "border-amber-200 bg-amber-50 text-amber-900 shadow-sm";
              }

              return (
                <td
                  key={well}
                  className={`rounded-lg border px-0.5 py-1 text-center ${cellClass}`}
                  title={entry ? `${entry.label}\n${entry.mutation}\n${entry.sequence}` : well}
                  aria-label={entry ? `${well}: ${entry.label}` : well}
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
  const { designResults, tableSorting, yPredMap, customCandidates } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      tableSorting: s.tableSorting,
      yPredMap: s.yPredMap,
      customCandidates: s.customCandidates,
    })),
  );
  return useMemo(
    () => getSortedMutations(designResults, tableSorting, { yPredMap, customCandidates }),
    [customCandidates, designResults, tableSorting, yPredMap],
  );
}

export function PlateMap() {
  const { plateMappings, dedupInfo } = useAppStore(
    useShallow((s) => ({
      plateMappings: s.plateMappings,
      dedupInfo: s.dedupInfo,
    })),
  );
  const sortedMutations = useSortedMutations();
  const [activeTab, setActiveTab] = useState<"fwd" | "rev">("fwd");
  const [page, setPage] = useState(0);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);

  const pairs = useMemo(() => buildPairsFromStore(plateMappings, dedupInfo, sortedMutations), [plateMappings, dedupInfo, sortedMutations]);
  const safeIdx = Math.min(page, Math.max(0, pairs.length - 1));
  const pair = pairs[safeIdx];

  // Reset page when mappings change
  useEffect(() => setPage(0), [plateMappings]);

  if (plateMappings.length === 0 || !pair) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-sm rounded-[24px] border border-dashed border-slate-300 bg-[linear-gradient(180deg,rgba(255,251,235,0.92),rgba(248,250,252,0.92))] px-6 py-8 text-center shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">Plate Layout</div>
          <div className="mt-3 text-lg font-semibold text-slate-900">Forward and reverse plate assignment appears after design.</div>
          <div className="mt-2 text-sm leading-6 text-slate-500">This surface is optimized for export handoff, duplicate reverse reuse, and machine-mapping review.</div>
        </div>
      </div>
    );
  }

  const totalFwd = pairs.reduce((s, p) => s + p.fwdCount, 0);
  const totalRev = pairs.reduce((s, p) => s + p.revCount, 0);

  return (
    <div className="h-full overflow-auto p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">Plate Pair Review</div>
          <div className="mt-1 text-sm text-slate-600">Each page shows one forward plate and its deduplicated reverse partner.</div>
        </div>
        <div className="flex flex-wrap gap-2 text-[11px]">
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 font-medium text-emerald-800">Forward {totalFwd}</span>
          <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 font-medium text-amber-900">Reverse {totalRev}</span>
          <span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 font-medium text-blue-800">
            Shared reverse {Object.values(dedupInfo).filter((muts) => muts.length > 1).length}
          </span>
        </div>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <button
          className={`rounded-full border px-3 py-1.5 text-[11px] font-semibold transition-colors ${
            activeTab === "fwd"
              ? "border-emerald-300 bg-emerald-50 text-emerald-800"
              : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
          }`}
          onClick={() => setActiveTab("fwd")}
        >
          Forward ({pair.fwdCount})
        </button>
        <button
          className={`rounded-full border px-3 py-1.5 text-[11px] font-semibold transition-colors ${
            activeTab === "rev"
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
          }`}
          onClick={() => setActiveTab("rev")}
        >
          Reverse ({pair.revCount})
        </button>

        {pairs.length > 1 && (
          <div className="ml-2 flex items-center gap-1 text-[10px]">
            <button
              className="rounded-full border border-slate-300 px-2 py-0.5 hover:bg-slate-100 disabled:opacity-30"
              disabled={safeIdx === 0}
              onClick={() => setPage(safeIdx - 1)}
            >
              ‹
            </button>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-slate-600">
              Plate {safeIdx + 1}/{pairs.length}
            </span>
            <button
              className="rounded-full border border-slate-300 px-2 py-0.5 hover:bg-slate-100 disabled:opacity-30"
              disabled={safeIdx >= pairs.length - 1}
              onClick={() => setPage(safeIdx + 1)}
            >
              ›
            </button>
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <span className="text-[10px] text-slate-400">
            Blue wells indicate reused reverse primers across mutations.
          </span>
          <Button
            size="sm"
            variant="outline"
            className="h-8 rounded-full border-slate-300 bg-white px-3 text-[11px]"
            onClick={() => setExportDialogOpen(true)}
          >
            Export Mapping...
          </Button>
        </div>
      </div>

      <div className="inline-block rounded-[24px] border border-slate-200 bg-white/90 p-3 shadow-[0_14px_34px_rgba(15,23,42,0.08)]">
        {activeTab === "fwd" ? (
          <PlateGrid grid={pair.fwd} color="green" />
        ) : (
          <PlateGrid grid={pair.rev} color="orange" />
        )}
      </div>

      <div className="mt-3 flex items-center gap-3 text-[10px] text-slate-500">
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border border-emerald-300 bg-emerald-100 align-middle" />Forward primer</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border border-amber-300 bg-amber-100 align-middle" />Reverse primer</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border border-blue-300 bg-blue-100 align-middle" />Shared reverse</span>
      </div>

      <MappingExportDialog
        open={exportDialogOpen}
        onOpenChange={setExportDialogOpen}
        onExport={({ format, transferVol }) => {
          setExportDialogOpen(false);
          handleExportMappingWithParams(format, { transferVol });
        }}
      />
    </div>
  );
}
