import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useAppStore } from "../../store/appStore";
import type { FailedMutation, SdmPrimerResult } from "../../types/models";
import { FailedMutationList } from "./FailedMutationList";
import {
  buildGroupColorMap,
  HEADER_TOOLTIPS,
  makeResultTableColumns,
  type RankedPrimerResult,
} from "./resultTableColumns";

const LazyCandidatePopover = lazy(async () => import("./popovers/CandidatePopover").then((m) => ({ default: m.CandidatePopover })));
const LazyHairpinDetail = lazy(async () => import("./popovers/HairpinDetail").then((m) => ({ default: m.HairpinDetail })));
const LazyOffTargetDetail = lazy(async () => import("./popovers/OffTargetDetail").then((m) => ({ default: m.OffTargetDetail })));
const LazyFailedMutationPopover = lazy(async () => import("./popovers/FailedMutationPopover").then((m) => ({ default: m.FailedMutationPopover })));

export function ResultTable() {
  const designResults = useAppStore((s) => s.designResults);
  const failedMutations = useAppStore((s) => s.failedMutations);
  const successCount = useAppStore((s) => s.successCount);
  const totalCount = useAppStore((s) => s.totalCount);
  const sorting = useAppStore((s) => s.tableSorting);
  const setSorting = useAppStore((s) => s.setTableSorting);
  const codonStrategy = useAppStore((s) => s.codonStrategy);
  const manuallySwapped = useAppStore((s) => s.manuallySwapped);
  const customCandidatesAll = useAppStore((s) => s.customCandidates);
  const rescuedMutations = useAppStore((s) => s.rescuedMutations);
  const rescuedMutationDetails = useAppStore((s) => s.rescuedMutationDetails);
  const removeDesignResult = useAppStore((s) => s.removeDesignResult);
  const yPredMap = useAppStore((s) => s.yPredMap);

  const [popover, setPopover] = useState<{ mutation: string; current: SdmPrimerResult } | null>(null);
  const [hpDetail, setHpDetail] = useState<SdmPrimerResult | null>(null);
  const [otDetail, setOtDetail] = useState<SdmPrimerResult | null>(null);
  const [failedPopover, setFailedPopover] = useState<FailedMutation | null>(null);

  const rankedData = useMemo<RankedPrimerResult[]>(
    () => designResults.map((r, i) => ({ ...r, rank: i + 1 })),
    [designResults],
  );

  const groupColorMap = useMemo(() => buildGroupColorMap(designResults), [designResults]);
  const rescueDetailMap = useMemo(
    () => new Map(rescuedMutationDetails.map((r) => [r.rescued_by, r])),
    [rescuedMutationDetails],
  );

  const columns = useMemo(
    () =>
      makeResultTableColumns({
        groupColorMap,
        codonStrategy,
        swapped: manuallySwapped,
        customCandidates: customCandidatesAll,
        rescuedMutations,
        rescueDetailMap,
        removeDesignResult,
        yPredMap,
      }),
    [
      groupColorMap,
      codonStrategy,
      manuallySwapped,
      customCandidatesAll,
      rescuedMutations,
      rescueDetailMap,
      removeDesignResult,
      yPredMap,
    ],
  );

  const table = useReactTable({
    data: rankedData,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const handleCellClick = useCallback((row: RankedPrimerResult, columnId: string) => {
    if (columnId === "forward_seq" || columnId === "reverse_seq") {
      setPopover({ mutation: row.mutation, current: row });
      return;
    }
    if (columnId === "hairpin") {
      const worst = Math.max(
        row.hairpin_tm_fwd ?? 0,
        row.hairpin_tm_rev ?? 0,
        row.homodimer_tm_fwd ?? 0,
        row.homodimer_tm_rev ?? 0,
      );
      if (worst > 0) setHpDetail(row);
      return;
    }
    if (columnId === "has_offtarget" && row.has_offtarget) {
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
          <FailedMutationList failedMutations={failedMutations} onSelect={setFailedPopover} />
          <Suspense fallback={null}>
            {failedPopover && (
              <LazyFailedMutationPopover
                failed={failedPopover}
                onClose={() => setFailedPopover(null)}
              />
            )}
          </Suspense>
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
                  {flexRender(header.column.columnDef.header, header.getContext())}
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
          <FailedMutationList failedMutations={failedMutations} onSelect={setFailedPopover} />
        </div>
      )}

      <div className="border-t border-gray-200 bg-gray-50 px-3 py-1.5 text-[10px] text-gray-400">
        {successCount}/{totalCount} designed
        {failedMutations.length > 0 && ` | ${failedMutations.length} failed`}
      </div>

      <Suspense fallback={null}>
        {popover && (
          <LazyCandidatePopover
            mutation={popover.mutation}
            current={popover.current}
            onClose={() => setPopover(null)}
          />
        )}

        {hpDetail && (
          <LazyHairpinDetail
            result={hpDetail}
            onClose={() => setHpDetail(null)}
          />
        )}

        {otDetail && (
          <LazyOffTargetDetail
            result={otDetail}
            onClose={() => setOtDetail(null)}
          />
        )}

        {failedPopover && (
          <LazyFailedMutationPopover
            failed={failedPopover}
            onClose={() => setFailedPopover(null)}
          />
        )}
      </Suspense>
    </div>
  );
}
