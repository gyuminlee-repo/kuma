import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type VisibilityState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AlertTriangle, Search, SlidersHorizontal } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import type { VerdictRecord } from "@/types/mame/models";
import type { MergedRow } from "@/types/mame/activity";
import { VerdictBadge } from "./VerdictBadge";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { StateView } from "@/components/ui/StateView";

type ActivityColumns = {
  activity_log2fc: number | null;
  fold_change: number | null;
  activity_raw_mean: number | null;
  activity_raw_sd: number | null;
  replicate_n: number | null;
  ngs_success: boolean | null;
  mutation: string | null;
};

type EvolveproExportStatus = {
  included: boolean;
  reasonKey: string | null;
};

function deriveEvolveproExport(row: ActivityColumns): EvolveproExportStatus {
  if (row.ngs_success === false) {
    return { included: false, reasonKey: "mame.verdictTable.evolveproExport.reasonNgsFail" };
  }
  if (row.mutation === "WT") {
    return { included: false, reasonKey: "mame.verdictTable.evolveproExport.reasonWt" };
  }
  if (row.activity_log2fc === null) {
    return { included: false, reasonKey: "mame.verdictTable.evolveproExport.reasonNoLog2fc" };
  }
  if (row.ngs_success === null && row.mutation === null && row.activity_log2fc === null) {
    return { included: false, reasonKey: "mame.verdictTable.evolveproExport.reasonNoActivity" };
  }
  return { included: true, reasonKey: null };
}

type VerdictRow = VerdictRecord &
  ActivityColumns & {
    mutant_id: string;
    is_fallback: boolean;
    fallback_reason: string | null;
  };

/** 컬럼 토글 ID 목록 */
const ACTIVITY_COLUMN_IDS = [
  "activity_log2fc",
  "fold_change",
  "raw_mean_sd",
  "replicate_n",
  "ngs_success",
  "evolvepro_export",
] as const;

const ACTIVITY_COLUMN_LABELS: Record<(typeof ACTIVITY_COLUMN_IDS)[number], string> = {
  activity_log2fc: "log₂FC",
  fold_change: "Fold Change",
  raw_mean_sd: "Raw Mean ± SD",
  replicate_n: "Replicates",
  ngs_success: "NGS",
  evolvepro_export: "EVOLVEpro Export",
};

const VIRTUAL_THRESHOLD = 1000;

function extractNbGroup(record: VerdictRecord): "NB01" | "NB02" | "NB03" | "UNKNOWN" {
  const match = (record.source_path ?? "").match(/NB0(\d)/i);
  if (!match) return "UNKNOWN";
  return `NB0${match[1]}` as "NB01" | "NB02" | "NB03";
}

function getVerdictRowTone(verdict: VerdictRow["verdict"]): string {
  switch (verdict) {
    case "PASS":
      return "border-l-2 border-l-primary";
    case "AMBIGUOUS":
      return "border-l-2 border-l-accent bg-accent/5";
    case "LOWDEPTH":
      return "border-l-2 border-l-border bg-muted/20";
    default:
      return "border-l-2 border-l-destructive bg-destructive/5";
  }
}

export function VerdictTable() {
  const { t } = useTranslation();
  const verdicts = useMameAppStore((state) => state.verdicts);

  if (verdicts.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        <StateView
          variant="empty"
          title={t("mame.verdictTable.emptyTitle")}
          description={t("mame.verdictTable.emptyDesc")}
        />
      </div>
    );
  }

  return <VerdictTableContent verdicts={verdicts} />;
}

function VerdictTableContent({ verdicts }: { verdicts: VerdictRecord[] }) {
  const { t } = useTranslation();
  const replicates = useMameAppStore((state) => state.replicates);
  const plateFilter = useMameAppStore((state) => state.plateFilter);
  const searchQuery = useMameAppStore((state) => state.searchQuery);
  const sorting = useMameAppStore((state) => state.sorting);
  const setPlateFilter = useMameAppStore((state) => state.setPlateFilter);
  const setSearchQuery = useMameAppStore((state) => state.setSearchQuery);
  const setSorting = useMameAppStore((state) => state.setSorting);

  // Activity data from the active round merged_table
  // Join key: well_id == custom_barcode (MAME barcode label = well position)
  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const mergedTable = useRoundStore((s) => {
    const round = s.rounds.find((r) => r.id === activeRoundId);
    return round?.merged_table ?? [];
  });

  // Build a lookup map for O(1) activity join
  const mergedByWell = useMemo<Map<string, MergedRow>>(() => {
    const map = new Map<string, MergedRow>();
    for (const row of mergedTable) {
      map.set(row.well_id, row);
    }
    return map;
  }, [mergedTable]);

  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(
    () =>
      Object.fromEntries(ACTIVITY_COLUMN_IDS.map((id) => [id, true])) as VisibilityState
  );

  const rows = useMemo<VerdictRow[]>(() => {
    const mutantMap = new Map<string, string>();
    const fallbackMap = new Map<string, { is_fallback: boolean; fallback_reason: string | null }>();
    for (const replicate of replicates) {
      if (replicate.selected_plate) {
        mutantMap.set(replicate.selected_plate, replicate.mutant_id);
        fallbackMap.set(replicate.mutant_id, {
          is_fallback: replicate.is_fallback,
          fallback_reason: replicate.fallback_reason,
        });
      }
    }
    return verdicts
      .filter((record) => plateFilter === "ALL" || extractNbGroup(record) === plateFilter)
      .map((record) => {
        const mid = mutantMap.get(record.native_barcode) ?? "—";
        const fb = fallbackMap.get(mid);
        // Join activity data by well_id == custom_barcode
        const merged = mergedByWell.get(record.custom_barcode);
        return {
          ...record,
          mutant_id: mid,
          is_fallback: fb?.is_fallback ?? false,
          fallback_reason: fb?.fallback_reason ?? null,
          activity_log2fc: merged?.log2_fc ?? null,
          fold_change: merged?.fold_change ?? null,
          activity_raw_mean: merged?.activity_raw_mean ?? null,
          activity_raw_sd: merged?.activity_raw_sd ?? null,
          replicate_n: merged?.replicate_n ?? null,
          ngs_success: merged?.ngs_success ?? null,
          mutation: merged?.mutation ?? null,
        };
      });
  }, [plateFilter, replicates, verdicts, mergedByWell]);

  const filteredRows = useMemo(() => {
    if (!searchQuery.trim()) return rows;
    const query = searchQuery.trim().toLowerCase();
    return rows.filter((row) =>
      [row.custom_barcode, row.native_barcode, row.mutant_id, row.verdict_notes, row.observed_aa_changes.join(",")]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [rows, searchQuery]);

  const columns = useMemo<ColumnDef<VerdictRow>[]>(
    () => [
      {
        accessorKey: "custom_barcode",
        header: t("mame.verdictTable.colBarcode"),
        cell: ({ getValue }) => (
          <span className="font-mono text-xs text-foreground">{getValue<string>()}</span>
        ),
      },
      {
        accessorKey: "mutant_id",
        header: t("mame.verdictTable.colMutantId"),
        cell: ({ row }) => (
          <span className="flex items-center gap-1">
            {row.original.is_fallback && (
              <span
                className="inline-flex cursor-help items-center text-warning"
                aria-label={row.original.fallback_reason ?? t("mame.verdictTable.fallbackAriaLabel")}
                title={row.original.fallback_reason ?? t("mame.verdictTable.fallbackAriaLabel")}
                role="img"
              >
                <AlertTriangle size={11} aria-hidden="true" />
              </span>
            )}
            <span className="text-xs font-medium">{row.original.mutant_id}</span>
          </span>
        ),
      },
      {
        accessorKey: "verdict",
        header: t("mame.verdictTable.colVerdict"),
        cell: ({ row }) => <VerdictBadge verdict={row.original.verdict} />,
      },
      {
        id: "observed_aa_changes",
        header: t("mame.verdictTable.colAaChanges"),
        accessorFn: (row) => row.observed_aa_changes.join(", "),
        cell: ({ getValue }) => (
          <span className="font-mono text-xs text-muted-foreground">{getValue<string>() || "—"}</span>
        ),
      },
      {
        id: "reads",
        header: t("mame.verdictTable.colDepth"),
        // Sort by read_count primary; fallback rows sort to bottom (0)
        accessorFn: (row) => row.read_count ?? 0,
        cell: ({ row }) => {
          const rc = row.original.read_count;
          const kb = row.original.file_size_kb;
          if (rc !== null) {
            return (
              <span className="flex flex-col gap-0.5">
                <span className="font-mono text-xs text-foreground">{rc.toLocaleString()}</span>
                <span
                  className="font-mono text-caption text-muted-foreground/60"
                  aria-label={t("mame.verdictTable.fileSizeAriaLabel", { kb: kb.toFixed(1) })}
                  title={t("mame.verdictTable.fileSizeAriaLabel", { kb: kb.toFixed(1) })}
                >
                  {kb.toFixed(1)} KB
                </span>
              </span>
            );
          }
          // Legacy: read_count unavailable — show KB as fallback proxy
          return (
            <span className="flex flex-col gap-0.5">
              <span className="font-mono text-xs text-muted-foreground">—</span>
              <span className="font-mono text-caption text-muted-foreground/60">
                {kb.toFixed(1)} KB
              </span>
            </span>
          );
        },
      },
      {
        id: "quality",
        header: t("mame.verdictTable.colQuality"),
        accessorFn: (row) => row.consensus_n_fraction,
        cell: ({ row }) => {
          const nPct = row.original.consensus_n_fraction * 100;
          const mixPct = row.original.max_minor_allele_fraction * 100;
          return (
            <span className="flex flex-col gap-0.5 font-mono text-caption text-muted-foreground">
              <span title="Consensus N fraction">
                N {nPct.toFixed(1)}% / low-depth {row.original.n_low_depth_positions}
              </span>
              <span title="Within-well minor allele signal">
                mix {row.original.n_mixed_positions} / {mixPct.toFixed(1)}%
              </span>
              <span title="Alignment drop counters">
                drop Q{row.original.n_mapq_failed} S{row.original.n_span_failed} BQ{row.original.n_low_quality_bases}
              </span>
            </span>
          );
        },
      },
      {
        accessorKey: "verdict_notes",
        header: t("mame.verdictTable.colNotes"),
        cell: ({ row }) => {
          const notes = row.original.verdict_notes;
          const fbReason = row.original.is_fallback ? row.original.fallback_reason : null;
          return (
            <span className="flex flex-col gap-0.5">
              {notes && (
                <span className="text-xs text-muted-foreground">{notes}</span>
              )}
              {fbReason && (
                <span className="text-xs text-warning">{fbReason}</span>
              )}
              {!notes && !fbReason && (
                <span className="text-xs text-muted-foreground">—</span>
              )}
            </span>
          );
        },
      },
      // ── Activity columns ─────────────────────────────────────────────────
      {
        id: "activity_log2fc",
        header: "log₂FC",
        accessorFn: (row) => row.activity_log2fc,
        cell: ({ getValue }) => {
          const v = getValue<number | null>();
          return (
            <span className="font-mono text-xs text-foreground min-w-0">
              {v !== null ? v.toFixed(2) : "—"}
            </span>
          );
        },
      },
      {
        id: "fold_change",
        header: "Fold Change",
        accessorFn: (row) => row.fold_change,
        cell: ({ getValue }) => {
          const v = getValue<number | null>();
          return (
            <span className="font-mono text-xs text-foreground min-w-0">
              {v !== null ? v.toFixed(2) : "—"}
            </span>
          );
        },
      },
      {
        id: "raw_mean_sd",
        header: "Raw Mean ± SD",
        accessorFn: (row) => row.activity_raw_mean,
        cell: ({ row }) => {
          const mean = row.original.activity_raw_mean;
          const sd = row.original.activity_raw_sd;
          if (mean === null) {
            return <span className="font-mono text-xs text-muted-foreground min-w-0">—</span>;
          }
          return (
            <span className="font-mono text-xs text-foreground min-w-0 whitespace-nowrap">
              {mean.toFixed(2)}
              {sd !== null && (
                <span className="text-muted-foreground"> ± {sd.toFixed(2)}</span>
              )}
            </span>
          );
        },
      },
      {
        id: "replicate_n",
        header: "Replicates",
        accessorFn: (row) => row.replicate_n,
        cell: ({ getValue }) => {
          const v = getValue<number | null>();
          return (
            <span className="font-mono text-xs text-foreground min-w-0">
              {v !== null ? v : "—"}
            </span>
          );
        },
      },
      {
        id: "ngs_success",
        header: "NGS",
        accessorFn: (row) => row.ngs_success,
        cell: ({ getValue }) => {
          const v = getValue<boolean | null>();
          if (v === null) {
            return <span className="text-xs text-muted-foreground min-w-0">—</span>;
          }
          return v ? (
            <Badge
              variant="outline"
              className="border-green-500 text-green-600 dark:text-green-400 text-[10px] px-1 py-0"
            >
              ✓
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="border-destructive text-destructive text-[10px] px-1 py-0"
            >
              ✗
            </Badge>
          );
        },
      },
      {
        id: "evolvepro_export",
        header: t("mame.verdictTable.evolveproExport.header"),
        accessorFn: (row) => deriveEvolveproExport(row).included,
        cell: ({ row }) => {
          const status = deriveEvolveproExport(row.original);
          if (status.included) {
            return (
              <Badge
                variant="outline"
                title={t("mame.verdictTable.evolveproExport.includedTitle")}
                className="border-green-500 text-green-600 dark:text-green-400 text-[10px] px-1 py-0"
              >
                ✓
              </Badge>
            );
          }
          return (
            <Badge
              variant="outline"
              title={status.reasonKey ? t(status.reasonKey) : undefined}
              className="border-muted-foreground/50 text-muted-foreground text-[10px] px-1 py-0"
            >
              ✗
            </Badge>
          );
        },
      },
    ],
    [t],
  );

  const table = useReactTable({
    data: filteredRows,
    columns,
    state: { sorting, columnVisibility },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
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

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex flex-col gap-2 border-b border-border px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
        <Tabs
          value={plateFilter}
          onValueChange={(value: string) => setPlateFilter(value as "NB01" | "NB02" | "NB03" | "ALL")}
        >
          <TabsList className="h-control gap-1 bg-muted/60 p-0.5">
            {(["ALL", "NB01", "NB02", "NB03"] as const).map((tab) => (
              <TabsTrigger
                key={tab}
                value={tab}
                className={cn(
                  "h-6 rounded-control px-2 text-caption font-medium transition-colors",
                  "data-[state=active]:bg-primary data-[state=active]:text-primary-foreground",
                  "data-[state=inactive]:text-muted-foreground data-[state=inactive]:hover:text-foreground",
                )}
              >
                {tab}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:max-w-sm">
          <div className="relative min-w-0 flex-1">
            <Search
              size={12}
              className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
              aria-hidden="true"
            />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("mame.verdictTable.searchPlaceholder")}
              className="h-7 min-w-0 pl-6 text-xs"
              aria-label={t("mame.verdictTable.searchAriaLabel")}
            />
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 shrink-0 px-2 text-xs"
                aria-label={t("mame.verdictTable.columnToggleAriaLabel")}
              >
                <SlidersHorizontal size={12} aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuLabel>{t("mame.verdictTable.activityColumnsLabel")}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {ACTIVITY_COLUMN_IDS.map((colId) => {
                const col = table.getColumn(colId);
                return (
                  <DropdownMenuCheckboxItem
                    key={colId}
                    checked={col?.getIsVisible() ?? true}
                    onCheckedChange={(checked) => col?.toggleVisibility(checked)}
                  >
                    {ACTIVITY_COLUMN_LABELS[colId]}
                  </DropdownMenuCheckboxItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {isVirtual && (
        <p className="bg-primary/10 px-3 py-0.5 text-caption text-primary" aria-live="polite">
          {t("mame.verdictTable.virtualScrollActive", { count: tableRows.length.toLocaleString() })}
        </p>
      )}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
        <Table aria-rowcount={tableRows.length}>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow
                key={headerGroup.id}
                className="border-b border-border bg-muted/30 hover:bg-muted/30"
              >
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    onClick={header.column.getToggleSortingHandler()}
                    className={cn(
                      "sticky top-0 z-10 h-control bg-background px-3 text-caption font-semibold text-muted-foreground",
                      header.column.getCanSort() && "cursor-pointer select-none hover:text-foreground",
                    )}
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
                    <div className="flex items-center gap-1">
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === "asc" && <span aria-hidden="true">↑</span>}
                      {header.column.getIsSorted() === "desc" && <span aria-hidden="true">↓</span>}
                    </div>
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {tableRows.length > 0 ? (
              isVirtual ? (() => {
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
                      return (
                        <TableRow
                          key={row.id}
                          data-index={vRow.index}
                          ref={rowVirtualizer.measureElement}
                          className={cn(
                            "border-b border-border/50 transition-colors hover:bg-muted/30",
                            getVerdictRowTone(row.original.verdict),
                            row.original.is_fallback && "border-l-warning bg-warning/5",
                          )}
                          aria-rowindex={vRow.index + 1}
                        >
                          {row.getVisibleCells().map((cell) => (
                            <TableCell key={cell.id} className="px-3 py-2">
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </TableCell>
                          ))}
                        </TableRow>
                      );
                    })}
                    {paddingBottom > 0 && <tr aria-hidden="true" style={{ height: paddingBottom }} />}
                  </>
                );
              })() : (
                tableRows.map((row) => (
                  <TableRow
                    key={row.id}
                    className={cn(
                      "border-b border-border/50 transition-colors hover:bg-muted/30",
                      getVerdictRowTone(row.original.verdict),
                      row.original.is_fallback && "border-l-warning bg-warning/5",
                    )}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id} className="px-3 py-2">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              )
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="py-0">
                  {verdicts.length === 0 ? (
                    <StateView
                      variant="empty"
                      title={t("mame.verdictTable.emptyTitle")}
                      description={t("mame.verdictTable.emptyDesc")}
                    />
                  ) : (
                    <StateView
                      variant="empty"
                      title={t("mame.verdictTable.noMatchTitle")}
                      description={t("mame.verdictTable.noMatchDesc")}
                    />
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {filteredRows.length > 0 && (
        <div className="border-t border-border px-3 py-1.5">
          <p className="text-caption text-muted-foreground">
            {searchQuery
              ? t("mame.verdictTable.resultCountWithSearch", { count: filteredRows.length, query: searchQuery })
              : t("mame.verdictTable.resultCount", { count: filteredRows.length })}
          </p>
        </div>
      )}
    </div>
  );
}
