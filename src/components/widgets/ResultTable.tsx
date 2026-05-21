import { lazy, Suspense, useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useShallow } from "zustand/react/shallow";
import { useAppStore } from "../../store/appStore";
import type { FailedMutation, SdmPrimerResult } from "../../types/models";
import { FailedMutationList } from "./FailedMutationList";
import {
  buildGroupColorMap,
  HEADER_TOOLTIPS,
  makeResultTableColumns,
} from "./resultTableColumns";
import { sortPrimersCanonical } from "../../lib/plate-utils";
import { StateView } from "../ui/StateView";
import { useColorblindMode } from "../../hooks/useColorblindMode";

const VIRTUAL_THRESHOLD = 1000;

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
    evolveproMode,
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
      evolveproMode: s.evolveproMode,
      fillOnFailure: s.fillOnFailure,
    })),
  );

  const { t } = useTranslation();
  const failedRetryDisabled = evolveproMode !== "topN" && fillOnFailure;
  const failedRetryDisabledHint = t("resultTable.pipelineFillHint");

  const [popover, setPopover] = useState<{ mutation: string; current: SdmPrimerResult } | null>(null);
  const [hpDetail, setHpDetail] = useState<SdmPrimerResult | null>(null);
  const [otDetail, setOtDetail] = useState<SdmPrimerResult | null>(null);
  const [failedPopover, setFailedPopover] = useState<FailedMutation | null>(null);

  // §8 A11y: colorblind mode for rescue badge shape prefix
  const colorblindMode = useColorblindMode();

  const groupColorMap = useMemo(() => buildGroupColorMap(designResults), [designResults]);
  const rescueDetailMap = useMemo(
    () => new Map(rescuedMutationDetails.map((r) => [r.rescued_by, r])),
    [rescuedMutationDetails],
  );
  const rescuedMutationSet = useMemo(
    () => new Set(rescuedMutations),
    [rescuedMutations],
  );

  // Canonical order index map: row object → position in sortPrimersCanonical output.
  // Used as the single source of truth for Mutation column ordering so ResultTable
  // matches Plate/Mapping views. Null when no sort is active (react-table uses input order).
  //
  // IMPORTANT: build the index map using ASC direction regardless of the active
  // sort.desc. TanStack Table inverts the sortingFn return value when desc=true,
  // so if we baked direction into canonicalOrder here, the direction would be
  // applied twice and the Mutation column would render opposite to its ▼/▲
  // indicator (observed bug: low aa_position first while indicator shows ▼).
  const canonicalOrder = useMemo(() => {
    const ascSorting = sorting.length > 0
      ? [{ id: sorting[0].id, desc: false }]
      : sorting;
    const sorted = sortPrimersCanonical(designResults, ascSorting, {
      yPredMap,
      customCandidates: customCandidatesAll,
    });
    if (!sorted) return undefined;
    return new Map<SdmPrimerResult, number>(sorted.map((r, i) => [r, i]));
  }, [designResults, sorting, yPredMap, customCandidatesAll]);

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
        canonicalOrder,
        colorblindMode,
        t,
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
      canonicalOrder,
      colorblindMode,
      t,
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

  const tableRows = table.getRowModel().rows;
  const isVirtual = tableRows.length >= VIRTUAL_THRESHOLD;

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const rowVirtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 36,
    overscan: 10,
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
            title={t("resultTable.allFailedTitle", { count: totalCount })}
            description={t("resultTable.allFailedDesc")}
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
          title={t("resultTable.noResultsTitle")}
          description={t("resultTable.noResultsDesc")}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {isVirtual && (
        <p className="bg-primary/10 px-3 py-0.5 text-caption text-primary" aria-live="polite">
          Virtual scroll active ({tableRows.length.toLocaleString()} rows)
        </p>
      )}
      <div ref={scrollRef} className="flex-1 overflow-auto">
      <table className="w-full text-caption border-collapse" aria-rowcount={tableRows.length}>
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
                  aria-sort={
                    header.column.getIsSorted() === "asc"
                      ? "ascending"
                      : header.column.getIsSorted() === "desc"
                        ? "descending"
                        : header.column.getCanSort()
                          ? "none"
                          : undefined
                  }
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
          {isVirtual ? (() => {
            const virtualRows = rowVirtualizer.getVirtualItems();
            const totalSize = rowVirtualizer.getTotalSize();
            const paddingTop = virtualRows[0]?.start ?? 0;
            const paddingBottom = totalSize - (virtualRows.at(-1)?.end ?? 0);
            return (
              <>
                {paddingTop > 0 && <tr aria-hidden="true" style={{ height: paddingTop }} />}
                {virtualRows.map((vRow) => {
                  const row = tableRows[vRow.index];
                  if (!row) return null;
                  const isSwapped = !!manuallySwapped[row.original.mutation];
                  return (
                    <tr
                      key={row.id}
                      data-index={vRow.index}
                      ref={rowVirtualizer.measureElement}
                      className={`h-control border-b border-border/50 hover:bg-muted/30 ${isSwapped ? "border-l-2 border-l-warning bg-warning/5" : ""}`}
                      aria-rowindex={vRow.index + 1}
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
                {paddingBottom > 0 && <tr aria-hidden="true" style={{ height: paddingBottom }} />}
              </>
            );
          })() : (
            tableRows.map((row) => {
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
            })
          )}
        </tbody>
      </table>
      </div>

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
              {t("resultTable.pipelineFillNote")}
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
