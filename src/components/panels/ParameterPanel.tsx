import { useAppStore } from "../../store/appStore";

export function ParameterPanel() {
  const selectedGene = useAppStore((s) => s.selectedGene);
  const selectedPolymerase = useAppStore((s) => s.selectedPolymerase);
  const polymerases = useAppStore((s) => s.polymerases);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const setSelectedGene = useAppStore((s) => s.setSelectedGene);
  const setSelectedPolymerase = useAppStore((s) => s.setSelectedPolymerase);

  return (
    <div className="border border-gray-300 rounded p-3 space-y-2">
      <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
        Parameters
      </h3>

      <label className="flex items-center gap-2 text-xs">
        <span className="w-24 text-gray-600">Target Gene:</span>
        {seqInfo && seqInfo.genes.length > 0 ? (
          <select
            className="flex-1 h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
            value={selectedGene}
            onChange={(e) => setSelectedGene(e.target.value)}
          >
            {seqInfo.genes.map((g) => {
              const isNamed = g.gene !== "ORF1" && g.gene !== "unknown";
              const label = isNamed ? `[${g.gene}]` : `(${g.gene})`;
              return (
                <option key={g.cds_start} value={String(g.cds_start)}>
                  {label} {g.cds_start}-{g.cds_end} ({g.aa_length} aa){g.product ? ` ${g.product}` : ""}
                </option>
              );
            })}
          </select>
        ) : (
          <span className="text-xs text-gray-400 italic">Load a sequence file first</span>
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
    </div>
  );
}
