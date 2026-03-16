import { useMemo } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { useAppStore } from "../../store/appStore";
import type { SdmPrimerResult } from "../../types/models";

const col = createColumnHelper<SdmPrimerResult>();

const GROUP_COLORS = [
  "#3b82f6", "#ef4444", "#f59e0b", "#10b981",
  "#8b5cf6", "#ec4899", "#06b6d4", "#f97316",
];

function buildGroupColorMap(results: SdmPrimerResult[]): Map<number, string> {
  const posCount = new Map<number, number>();
  for (const r of results) {
    const pos = r.codon_pos;
    if (pos != null) {
      posCount.set(pos, (posCount.get(pos) ?? 0) + 1);
    }
  }
  const colorMap = new Map<number, string>();
  let idx = 0;
  for (const [pos, count] of posCount) {
    if (count >= 2) {
      colorMap.set(pos, GROUP_COLORS[idx % GROUP_COLORS.length]);
      idx++;
    }
  }
  return colorMap;
}

/** Forward primer with overlap(blue) + mutation(red) + downstream(black) coloring */
function ColoredFwdSeq({ seq, overlapLen, mtCodon }: {
  seq: string;
  overlapLen: number;
  mtCodon: string;
}) {
  const overlap = seq.slice(0, overlapLen);
  const codon = seq.slice(overlapLen, overlapLen + 3);
  const rest = seq.slice(overlapLen + 3);

  return (
    <span className="font-mono text-[10px] break-all cursor-pointer"
      title="Click to copy"
      onClick={() => navigator.clipboard.writeText(seq)}
    >
      <span style={{ color: "#3b82f6" }}>{overlap}</span>
      <span style={{ color: "#ef4444", fontWeight: 600 }}>{codon}</span>
      <span>{rest}</span>
    </span>
  );
}

function makeColumns(groupColorMap: Map<number, string>) {
  return [
    col.accessor("mutation", {
      header: "Mutation",
      size: 90,
      cell: (info) => {
        const row = info.row.original;
        const color = row.codon_pos != null ? groupColorMap.get(row.codon_pos) : undefined;
        const aaPos = row.codon_pos != null ? Math.floor(row.codon_pos / 3) + 1 : null;
        return (
          <span className="font-mono font-medium">
            {info.getValue()}
            {color && aaPos && (
              <span
                className="inline-block ml-1 px-1 rounded text-[8px] font-semibold text-white align-middle"
                style={{ backgroundColor: color }}
              >
                Pos{aaPos}
              </span>
            )}
          </span>
        );
      },
    }),
    col.accessor("forward_seq", {
      header: "Forward Primer",
      size: 220,
      cell: (info) => {
        const row = info.row.original;
        return (
          <ColoredFwdSeq
            seq={info.getValue()}
            overlapLen={row.overlap_len ?? 0}
            mtCodon={row.mt_codon}
          />
        );
      },
    }),
    col.accessor("reverse_seq", {
      header: "Reverse Primer",
      size: 200,
      cell: (info) => (
        <span
          className="font-mono text-[10px] break-all cursor-pointer"
          title="Click to copy"
          onClick={() => navigator.clipboard.writeText(info.getValue())}
        >
          {info.getValue()}
        </span>
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
      header: "Tm F",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("tm_no_rev", {
      header: "Tm R",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("tm_overlap", {
      header: "Tm Ov",
      size: 55,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("tolerance_used", {
      header: "Tol",
      size: 50,
      cell: (info) => {
        const val = info.getValue();
        return val != null ? `±${val.toFixed(1)}` : "—";
      },
    }),
    col.accessor("penalty", {
      header: "Pen",
      size: 45,
      cell: (info) => {
        const val = info.getValue();
        return val != null ? val.toFixed(1) : "—";
      },
    }),
    col.accessor("has_offtarget", {
      header: "OT",
      size: 40,
      cell: (info) => {
        const val = info.getValue();
        if (val == null) return "—";
        return val ? (
          <span className="inline-block px-1 py-0.5 rounded text-[10px] font-medium bg-red-100 text-red-700">!!</span>
        ) : (
          <span className="inline-block px-1 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700">OK</span>
        );
      },
    }),
    col.accessor("gc_fwd", {
      header: "GC% F",
      size: 50,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("gc_rev", {
      header: "GC% R",
      size: 50,
      cell: (info) => info.getValue().toFixed(1),
    }),
    col.accessor("wt_codon", {
      header: "WT",
      size: 40,
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
    col.accessor("mt_codon", {
      header: "MT",
      size: 40,
      cell: (info) => <span className="font-mono">{info.getValue()}</span>,
    }),
  ];
}

export function ResultTable() {
  const designResults = useAppStore((s) => s.designResults);

  const groupColorMap = useMemo(
    () => buildGroupColorMap(designResults),
    [designResults],
  );

  const columns = useMemo(
    () => makeColumns(groupColorMap),
    [groupColorMap],
  );

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
