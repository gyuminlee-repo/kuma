import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import type { FailedMutation, SdmPrimerResult } from "../../types/models";
import { FailedMutationList } from "./FailedMutationList";
import {
  buildGroupColorMap,
  HEADER_TOOLTIPS,
  makeResultTableColumns,
} from "./resultTableColumns";

const LazyCandidatePopover = lazy(async () => import("./popovers/CandidatePopover").then((m) => ({ default: m.CandidatePopover })));
const LazyHairpinDetail = lazy(async () => import("./popovers/HairpinDetail").then((m) => ({ default: m.HairpinDetail })));
const LazyOffTargetDetail = lazy(async () => import("./popovers/OffTargetDetail").then((m) => ({ default: m.OffTargetDetail })));
const LazyFailedMutationPopover = lazy(async () => import("./popovers/FailedMutationPopover").then((m) => ({ default: m.FailedMutationPopover })));

export function ResultTable() {
  const {
    designResults,
    failedMutations,
    successCount,
    totalCount,
    sorting,
    setSorting,
    codonStrategy,
    manuallySwapped,
    customCandidatesAll,
    rescuedMutations,
    rescuedMutationDetails,
    removeDesignResult,
    yPredMap,
  } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      failedMutations: s.failedMutations,
      successCount: s.successCount,
      totalCount: s.totalCount,
      sorting: s.tableSorting,
      setSorting: s.setTableSorting,
      codonStrategy: s.codonStrategy,
      manuallySwapped: s.manuallySwapped,
      customCandidatesAll: s.customCandidates,
      rescuedMutations: s.rescuedMutations,
      rescuedMutationDetails: s.rescuedMutationDetails,
      removeDesignResult: s.removeDesignResult,
      yPredMap: s.yPredMap,
    })),
  );

  const [popover, setPopover] = useState<{ mutation: string; current: SdmPrimerResult } | null>(null);
  const [hpDetail, setHpDetail] = useState<SdmPrimerResult | null>(null);
  const [otDetail, setOtDetail] = useState<SdmPrimerResult | null>(null);
  const [failedPopover, setFailedPopover] = useState<FailedMutation | null>(null);

  const groupColorMap = useMemo(() => buildGroupColorMap(designResults), [designResults]);
  const rescueDetailMap = useMemo(
    () => new Map(rescuedMutationDetails.map((r) => [r.rescued_by, r])),
    [rescuedMutationDetails],
  );
  const rescuedMutationSet = useMemo(
    () => new Set(rescuedMutations),
    [rescuedMutations],
  );

  const columns = useMemo(
    () =>
      makeResultTableColumns({
        groupColorMap,
        codonStrategy,
        swapped: manuallySwapped,
        customCandidates: customCandidatesAll,
        rescuedMutations: rescuedMutationSet,
        rescueDetailMap,
        removeDesignResult,
        yPredMap,
      }),
    [
      groupColorMap,
      codonStrategy,
      manuallySwapped,
      customCandidatesAll,
      rescuedMutationSet,
      rescueDetailMap,
      removeDesignResult,
      yPredMap,
    ],
  );

  const table = useReactTable({
    data: designResults,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const handleCellClick = useCallback((row: SdmPrimerResult, columnId: string) => {
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
        <div className="h-full overflow-auto p-5">
          <div className="mb-2 text-sm font-semibold text-red-600">
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
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-md rounded-[24px] border border-dashed border-slate-300 bg-[linear-gradient(180deg,rgba(255,251,235,0.9),rgba(248,250,252,0.9))] px-6 py-8 text-center shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">No Design Yet</div>
          <div className="mt-3 text-lg font-semibold text-slate-900">
            Load a sequence, define mutations, then run a batch design.
          </div>
          <div className="mt-2 text-sm leading-6 text-slate-500">
            This view becomes the central review surface for ranked primers, rescue candidates, and failure diagnostics.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 z-10 bg-slate-50/95 backdrop-blur">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className={`border-b border-slate-200 px-2 py-2 text-left font-semibold text-slate-600 ${
                    header.column.getCanSort() ? "cursor-pointer select-none hover:bg-amber-50" : ""
                  }`}
                  style={{ width: header.getSize() }}
                  title={header.column.columnDef.meta?.tooltip ?? HEADER_TOOLTIPS[header.column.id] ?? ""}
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
                className={`border-b border-slate-100 hover:bg-slate-50 ${isSwapped ? "border-l-3 border-l-amber-400 bg-amber-50/30" : ""}`}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta;
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
        <div className="border-t border-red-200 bg-red-50 px-3 py-2">
          <div className="mb-1 text-xs font-semibold text-red-700">
            Failed ({failedMutations.length}/{totalCount})
          </div>
          <FailedMutationList failedMutations={failedMutations} onSelect={setFailedPopover} />
        </div>
      )}

      <div className="border-t border-slate-200 bg-slate-50 px-3 py-2 text-[10px] text-slate-500">
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
