import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { AlertTriangle, Search } from "lucide-react";
import { useMemo } from "react";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { VerdictRecord } from "@/types/mame/models";
import { VerdictBadge } from "./VerdictBadge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { StateView } from "@/components/ui/StateView";

type VerdictRow = VerdictRecord & {
  mutant_id: string;
  is_fallback: boolean;
  fallback_reason: string | null;
};

function extractNbGroup(record: VerdictRecord): "NB01" | "NB02" | "NB03" | "UNKNOWN" {
  const match = record.source_path.match(/NB0(\d)/i);
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
  const verdicts = useMameAppStore((state) => state.verdicts);
  const replicates = useMameAppStore((state) => state.replicates);
  const plateFilter = useMameAppStore((state) => state.plateFilter);
  const searchQuery = useMameAppStore((state) => state.searchQuery);
  const sorting = useMameAppStore((state) => state.sorting);
  const setPlateFilter = useMameAppStore((state) => state.setPlateFilter);
  const setSearchQuery = useMameAppStore((state) => state.setSearchQuery);
  const setSorting = useMameAppStore((state) => state.setSorting);

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
        return {
          ...record,
          mutant_id: mid,
          is_fallback: fb?.is_fallback ?? false,
          fallback_reason: fb?.fallback_reason ?? null,
        };
      });
  }, [plateFilter, replicates, verdicts]);

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
        header: "Barcode",
        cell: ({ getValue }) => (
          <span className="font-mono text-xs text-foreground">{getValue<string>()}</span>
        ),
      },
      {
        accessorKey: "mutant_id",
        header: "Mutant ID",
        cell: ({ row }) => (
          <span className="flex items-center gap-1">
            {row.original.is_fallback && (
              <span
                className="inline-flex cursor-help items-center text-warning"
                aria-label={row.original.fallback_reason ?? "Fallback replicate"}
                title={row.original.fallback_reason ?? "Fallback replicate"}
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
        header: "Verdict",
        cell: ({ row }) => <VerdictBadge verdict={row.original.verdict} />,
      },
      {
        id: "observed_aa_changes",
        header: "AA Changes",
        accessorFn: (row) => row.observed_aa_changes.join(", "),
        cell: ({ getValue }) => (
          <span className="font-mono text-xs text-muted-foreground">{getValue<string>() || "—"}</span>
        ),
      },
      {
        id: "reads",
        header: "Reads",
        accessorFn: (row) =>
          row.read_count !== null ? row.read_count : row.file_size_kb,
        cell: ({ row }) => {
          const rc = row.original.read_count;
          if (rc !== null) {
            return (
              <span className="font-mono text-xs text-foreground">
                {rc.toLocaleString()}
              </span>
            );
          }
          return (
            <span className="font-mono text-xs text-muted-foreground">
              {row.original.file_size_kb.toFixed(1)} KB
            </span>
          );
        },
      },
      {
        accessorKey: "verdict_notes",
        header: "Notes",
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
    ],
    [],
  );

  const table = useReactTable({
    data: filteredRows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div className="flex min-h-0 flex-col overflow-hidden">
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
        <div className="relative w-full sm:max-w-xs">
          <Search
            size={12}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search barcode / mutant ID…"
            className="h-7 pl-6 text-xs"
            aria-label="Search results"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <Table>
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
            {table.getRowModel().rows.length > 0 ? (
              table.getRowModel().rows.map((row) => (
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
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="py-0">
                  {verdicts.length === 0 ? (
                    <StateView
                      variant="empty"
                      title="No results yet"
                      description="Run analysis to populate the verdict table."
                    />
                  ) : (
                    <StateView
                      variant="empty"
                      title="No matches"
                      description="No results match the current search or filter."
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
            {filteredRows.length} result(s)
            {searchQuery && ` (search: "${searchQuery}")`}
          </p>
        </div>
      )}
    </div>
  );
}
