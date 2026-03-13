import { useAppStore } from "../../store/appStore";
import { Input } from "../ui/input";

export function ParameterPanel() {
  const cdsStart = useAppStore((s) => s.cdsStart);
  const selectedPolymerase = useAppStore((s) => s.selectedPolymerase);
  const overlapLen = useAppStore((s) => s.overlapLen);
  const polymerases = useAppStore((s) => s.polymerases);
  const fastaInfo = useAppStore((s) => s.fastaInfo);
  const setCdsStart = useAppStore((s) => s.setCdsStart);
  const setSelectedPolymerase = useAppStore((s) => s.setSelectedPolymerase);
  const setOverlapLen = useAppStore((s) => s.setOverlapLen);

  return (
    <div className="border border-gray-300 rounded p-3 space-y-2">
      <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
        Parameters
      </h3>

      <label className="flex items-center gap-2 text-xs">
        <span className="w-24 text-gray-600">CDS Start:</span>
        <Input
          type="number"
          min={0}
          value={cdsStart}
          onChange={(e) => setCdsStart(Number(e.target.value))}
          className="w-24 h-7 text-xs"
          title="0-based position of ATG start codon"
        />
        {fastaInfo && fastaInfo.atg_positions.length > 1 && (
          <select
            className="text-xs border border-gray-300 rounded px-1 py-0.5"
            value={cdsStart}
            onChange={(e) => setCdsStart(Number(e.target.value))}
          >
            {fastaInfo.atg_positions.map((pos) => (
              <option key={pos} value={pos}>
                ATG @ {pos}
              </option>
            ))}
          </select>
        )}
      </label>

      <label className="flex items-center gap-2 text-xs">
        <span className="w-24 text-gray-600">Polymerase:</span>
        <select
          className="flex-1 h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
          value={selectedPolymerase}
          onChange={(e) => setSelectedPolymerase(e.target.value)}
        >
          {polymerases.length > 0 ? (
            polymerases.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} ({p.manufacturer})
              </option>
            ))
          ) : (
            <option value={selectedPolymerase}>{selectedPolymerase}</option>
          )}
        </select>
      </label>

      <label className="flex items-center gap-2 text-xs">
        <span className="w-24 text-gray-600">Overlap (bp):</span>
        <Input
          type="number"
          min={15}
          max={40}
          value={overlapLen}
          onChange={(e) => setOverlapLen(Number(e.target.value))}
          className="w-20 h-7 text-xs"
          title="Overlap window length (15-40 bp)"
        />
      </label>
    </div>
  );
}
