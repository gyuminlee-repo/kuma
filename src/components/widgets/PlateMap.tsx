import { useAppStore } from "../../store/appStore";
import type { PlateMapping } from "../../types/models";

const ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"];
const COLS = Array.from({ length: 12 }, (_, i) => i + 1);

function buildGrid(
  mappings: PlateMapping[],
): Record<string, PlateMapping | undefined> {
  const grid: Record<string, PlateMapping | undefined> = {};
  for (const m of mappings) {
    grid[m.well] = m;
  }
  return grid;
}

export function PlateMap() {
  const plateMappings = useAppStore((s) => s.plateMappings);

  if (plateMappings.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-xs">
        Plate map will appear after primer design
      </div>
    );
  }

  const grid = buildGrid(plateMappings);

  return (
    <div className="h-full overflow-auto p-2">
      <h3 className="text-xs font-semibold text-gray-600 mb-1">
        96-Well Plate Map
      </h3>
      <div className="inline-block">
        <table className="border-collapse text-[10px]">
          <thead>
            <tr>
              <th className="w-6" />
              {COLS.map((c) => (
                <th
                  key={c}
                  className="w-16 text-center font-semibold text-gray-500 pb-1"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row}>
                <td className="font-semibold text-gray-500 text-center pr-1">
                  {row}
                </td>
                {COLS.map((col) => {
                  const well = `${row}${col}`;
                  const mapping = grid[well];
                  const isFwd = mapping?.primer_type === "forward";
                  const isRev = mapping?.primer_type === "reverse";

                  return (
                    <td
                      key={well}
                      className={`border border-gray-300 text-center px-0.5 py-1 rounded-sm ${
                        isFwd
                          ? "bg-green-100 text-green-800"
                          : isRev
                            ? "bg-orange-100 text-orange-800"
                            : "bg-white text-gray-300"
                      }`}
                      title={
                        mapping
                          ? `${mapping.primer_name}\n${mapping.sequence}`
                          : well
                      }
                    >
                      {mapping ? (
                        <span className="font-mono truncate block">
                          {mapping.primer_name}
                        </span>
                      ) : (
                        <span className="text-gray-200">&middot;</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex gap-4 mt-2 text-[10px] text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-green-100 border border-green-300 rounded-sm inline-block" />
            Forward
          </span>
          <span className="flex items-center gap-1">
            <span className="w-3 h-3 bg-orange-100 border border-orange-300 rounded-sm inline-block" />
            Reverse
          </span>
        </div>
      </div>
    </div>
  );
}
