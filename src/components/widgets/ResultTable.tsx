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
import { StateView } from "../ui/StateView";

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
    overlapMode,
    manuallySwapped,
    customCandidatesAll,
    rescuedMutations,
    rescuedMutationDetails,
    removeDesignResult,
    yPredMap,
    pipelineMode,
    fillOnFailure,
  } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      failedMutations: s.failedMutations,
      successCount: s.successCount,
      totalCount: s.totalCount,
      sorting: s.tableSorting,
      setSorting: s.setTableSorting,
      codonStrategy: s.codonStrategy,
      overlapMode: s.overlapMode,
      manuallySwapped: s.manuallySwapped,
      customCandidatesAll: s.customCandidates,
      rescuedMutations: s.rescuedMutations,
      rescuedMutationDetails: s.rescuedMutationDetails,
      removeDesignResult: s.removeDesignResult,
      yPredMap: s.yPredMap,
      pipelineMode: s.pipelineMode,
      fillOnFailure: s.fillOnFailure,
    })),
  );

  const failedRetryDisabled = pipelineMode && fillOnFailure;
  const failedRetryDisabledHint = "Pipeline + Fill on failure already substituted these positions; retry is disabled.";

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
        overlapMode,
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
      overlapMode,
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
          <StateView
            variant="error"
            title={`All ${totalCount} mutations failed`}
            description="Review failure reasons below, then adjust parameters and retry."
            className="pb-4"
          />
          <FailedMutationList
            failedMutations={failedMutations}
            onSelect={setFailedPopover}
            disabled={failedRetryDisabled}
            disabledHint={failedRetryDisabledHint}
          />
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
        <StateView
          variant="empty"
          title="No results yet"
          description="Load a sequence, define mutations, then run design."
        />
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-caption border-collapse">
        <thead className="sticky top-0 z-10 bg-background/95 backdrop-blur">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className={`h-control border-b border-border px-2 text-left font-semibold text-muted-foreground ${
                    header.column.getCanSort() ? "cursor-pointer select-none hover:bg-muted/60" : ""
                  }`}
                  style={{ width: header.getSize() }}
                  title={header.column.columnDef.meta?.tooltip ?? HEADER_TOOLTIPS[header.column.id] ?? ""}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {header.column.getIsSorted() === "asc" ? " ▲" : ""}
                  {header.column.getIsSorted() === "desc" ? " ▼" : ""}
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
                className={`h-control border-b border-border/50 hover:bg-muted/30 ${isSwapped ? "border-l-2 border-l-warning bg-warning/5" : ""}`}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta;
                  const showClickable = !!meta?.clickable;
                  return (
                    <td
                      key={cell.id}
                      className={`px-2 py-1 tabular-nums ${showClickable ? "cursor-pointer hover:bg-muted/60" : ""}`}
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
        <div className="border-t border-error/20 bg-error/5 px-3 py-2">
          <div className="mb-1 text-caption font-semibold text-error">
            ▲ Failed ({failedMutations.length}/{totalCount})
          </div>
          <FailedMutationList
            failedMutations={failedMutations}
            onSelect={setFailedPopover}
            disabled={failedRetryDisabled}
            disabledHint={failedRetryDisabledHint}
          />
          {failedRetryDisabled && (
            <p className="mt-1 text-[11px] text-muted-foreground">
              Pipeline + Fill on failure substituted these positions; retry is unnecessary.
            </p>
          )}
        </div>
      )}

      <div className="border-t border-border bg-muted/30 px-3 py-1.5 text-caption text-muted-foreground tabular-nums">
        ● {successCount}/{totalCount} designed
        {failedMutations.length > 0 && ` · ▲ ${failedMutations.length} failed`}
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
