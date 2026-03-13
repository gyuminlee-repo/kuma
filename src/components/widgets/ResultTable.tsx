import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useAppStore } from "../../store/appStore";
import type { SdmPrimerResult } from "../../types/models";

const col = createColumnHelper<SdmPrimerResult>();

const columns = [
  col.accessor("mutation", {
    header: "Mutation",
    size: 80,
    cell: (info) => (
      <span className="font-mono font-medium">{info.getValue()}</span>
    ),
  }),
  col.accessor("forward_seq", {
    header: "Forward Primer",
    size: 200,
    cell: (info) => (
      <span className="font-mono text-[10px] break-all">{info.getValue()}</span>
    ),
  }),
  col.accessor("reverse_seq", {
    header: "Reverse Primer",
    size: 200,
    cell: (info) => (
      <span className="font-mono text-[10px] break-all">{info.getValue()}</span>
    ),
  }),
  col.accessor("fwd_len", {
    header: "Fwd",
    size: 40,
  }),
  col.accessor("rev_len", {
    header: "Rev",
    size: 40,
  }),
  col.accessor("tm_no_fwd", {
    header: "Tm_no F",
    size: 65,
    cell: (info) => info.getValue().toFixed(1),
  }),
  col.accessor("tm_no_rev", {
    header: "Tm_no R",
    size: 65,
    cell: (info) => info.getValue().toFixed(1),
  }),
  col.accessor("tm_overlap", {
    header: "Tm_ov",
    size: 60,
    cell: (info) => info.getValue().toFixed(1),
  }),
  col.accessor("tm_condition_met", {
    header: "Tm OK",
    size: 55,
    cell: (info) => (
      <span
        className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
          info.getValue()
            ? "bg-green-100 text-green-700"
            : "bg-red-100 text-red-700"
        }`}
      >
        {info.getValue() ? "OK" : "FAIL"}
      </span>
    ),
  }),
  col.accessor("gc_fwd", {
    header: "GC% F",
    size: 55,
    cell: (info) => info.getValue().toFixed(1),
  }),
  col.accessor("gc_rev", {
    header: "GC% R",
    size: 55,
    cell: (info) => info.getValue().toFixed(1),
  }),
  col.accessor("wt_codon", {
    header: "WT",
    size: 45,
    cell: (info) => <span className="font-mono">{info.getValue()}</span>,
  }),
  col.accessor("mt_codon", {
    header: "MT",
    size: 45,
    cell: (info) => <span className="font-mono">{info.getValue()}</span>,
  }),
];

export function ResultTable() {
  const designResults = useAppStore((s) => s.designResults);

  const table = useReactTable({
    data: designResults,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (designResults.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Load a FASTA file and enter mutations to design SDM primers
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
                  className="px-2 py-1.5 text-left font-semibold text-gray-600 border-b border-gray-300"
                  style={{ width: header.getSize() }}
                >
                  {flexRender(
                    header.column.columnDef.header,
                    header.getContext(),
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className="hover:bg-green-50 border-b border-gray-100"
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-2 py-1">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
