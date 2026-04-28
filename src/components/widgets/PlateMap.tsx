import { useEffect, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import { reorderMappings, getSortedMutations, wellName } from "../../lib/plate-utils";
import type { PlateMapping } from "../../types/models";
import { Button } from "../ui/button";
import { MappingExportDialog } from "../dialogs/MappingExportDialog";
import { handleExportMappingWithParams } from "../layout/export-handlers";
import { StateView } from "../ui/StateView";

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
    <table className="border-separate border-spacing-1 text-caption">
      <thead>
        <tr>
          <th className="w-4 h-5" />
          {COLS.map((c) => (
            <th key={c} className="h-5 w-14 text-center text-caption font-semibold text-muted-foreground">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ROWS.map((row) => (
          <tr key={row} className="h-control">
            <td className="pr-0.5 text-center text-caption font-semibold text-muted-foreground">{row}</td>
            {COLS.map((col) => {
              const well = `${row}${col}`;
              const entry = grid.get(well);
              const isShared = entry?.shared;

              let cellClass: string;
              if (!entry) {
                cellClass = "border-border bg-muted/30 text-border";
              } else if (isShared) {
                cellClass = "border-info/30 bg-info/10 text-info";
              } else if (color === "green") {
                cellClass = "border-success/30 bg-success/10 text-success";
              } else {
                cellClass = "border-warning/30 bg-warning/10 text-warning";
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
        <StateView
          variant="empty"
          title="No plate layout yet"
          description="Run design to assign primers to plate wells."
        />
      </div>
    );
  }

  const totalFwd = pairs.reduce((s, p) => s + p.fwdCount, 0);
  const totalRev = pairs.reduce((s, p) => s + p.revCount, 0);
  const sharedReverseCount = Object.values(dedupInfo).filter((muts) => muts.length > 1).length;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden p-3">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-caption font-semibold text-muted-foreground">Plate pair review</div>
          <div className="mt-1 text-caption text-muted-foreground">Each page shows one forward plate and its deduplicated reverse partner.</div>
        </div>
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2">
          <button
            className={`h-control rounded-full border px-3 text-caption font-semibold transition-colors ${
              activeTab === "fwd"
                ? "border-success/40 bg-success/10 text-success"
                : "border-border bg-card text-muted-foreground hover:bg-muted/60"
            }`}
            onClick={() => setActiveTab("fwd")}
          >
            Forward ({pair.fwdCount})
          </button>
          <button
            className={`h-control rounded-full border px-3 text-caption font-semibold transition-colors ${
              activeTab === "rev"
                ? "border-warning/40 bg-warning/10 text-warning"
                : "border-border bg-card text-muted-foreground hover:bg-muted/60"
            }`}
            onClick={() => setActiveTab("rev")}
          >
            Reverse ({pair.revCount})
          </button>
        </div>

        {pairs.length > 1 && (
          <div className="flex items-center gap-1 text-caption">
            <button
              className="h-control rounded-full border border-border px-2 hover:bg-muted/60 disabled:opacity-30"
              disabled={safeIdx === 0}
              onClick={() => setPage(safeIdx - 1)}
            >
              ‹
            </button>
            <span className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-muted-foreground">
              Plate {safeIdx + 1}/{pairs.length}
            </span>
            <button
              className="h-control rounded-full border border-border px-2 hover:bg-muted/60 disabled:opacity-30"
              disabled={safeIdx >= pairs.length - 1}
              onClick={() => setPage(safeIdx + 1)}
            >
              ›
            </button>
          </div>
        )}

        <div className="ml-auto">
          <Button
            size="sm"
            variant="outline"
            className="h-control rounded-full border-border px-3 text-caption"
            onClick={() => setExportDialogOpen(true)}
          >
            Export Mapping...
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-x-auto overflow-y-hidden">
        <div className="inline-block rounded-container border border-border bg-card p-3">
          {activeTab === "fwd" ? (
            <PlateGrid grid={pair.fwd} color="green" />
          ) : (
            <PlateGrid grid={pair.rev} color="orange" />
          )}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 text-caption text-muted-foreground">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-success/30 bg-success/8 px-3 py-1 font-medium text-success">Forward {totalFwd}</span>
          <span className="rounded-full border border-warning/30 bg-warning/8 px-3 py-1 font-medium text-warning">Reverse {totalRev}</span>
          <span className="rounded-full border border-info/30 bg-info/8 px-3 py-1 font-medium text-info">Shared reverse {sharedReverseCount}</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border border-success/30 bg-success/10 align-middle" />Forward primer</span>
          <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border border-warning/30 bg-warning/10 align-middle" />Reverse primer</span>
          <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm border border-info/30 bg-info/10 align-middle" />Shared reverse</span>
        </div>
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
