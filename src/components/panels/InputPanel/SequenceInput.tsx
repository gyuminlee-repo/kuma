import { open } from "@tauri-apps/plugin-dialog";
import { useAppStore } from "../../../store/appStore";
import { basename } from "../../../lib/utils";
import { Button } from "../../ui/button";

async function browseFile(
  filters: { name: string; extensions: string[] }[],
  onSelect: (path: string) => Promise<void> | void,
) {
  const path = await open({ filters, multiple: false });
  if (path) await onSelect(path as string);
}

export function SequenceInput() {
  const fastaPath = useAppStore((s) => s.fastaPath);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const selectedGene = useAppStore((s) => s.selectedGene);
  const setSelectedGene = useAppStore((s) => s.setSelectedGene);
  const organism = useAppStore((s) => s.organism);
  const setOrganism = useAppStore((s) => s.setOrganism);
  const loadSequence = useAppStore((s) => s.loadSequence);

  return (
    <>
      {/* Sequence File */}
      <div className="space-y-1">
        <label className="text-xs text-gray-600 font-medium">Sequence File</label>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              browseFile(
                [
                  { name: "Sequence (GenBank/SnapGene)", extensions: ["gb", "gbff", "gbk", "dna"] },
                  { name: "FASTA", extensions: ["fa", "fasta", "fna"] },
                  { name: "All Files", extensions: ["*"] },
                ],
                loadSequence,
              )
            }
            className="flex-shrink-0"
          >
            Browse
          </Button>
          <span className="text-xs text-gray-500 truncate self-center">
            {fastaPath ? basename(fastaPath) : "No file selected (.gb / .dna)"}
          </span>
        </div>
        {seqInfo && (
          <div className="text-xs text-gray-500 space-y-0.5 bg-gray-50 rounded p-2">
            <div className="truncate" title={seqInfo.header}>
              {seqInfo.header}
            </div>
            <div>
              {seqInfo.seq_length.toLocaleString()} bp | {seqInfo.genes.length} gene(s)
            </div>
          </div>
        )}
      </div>

      {/* Target Gene */}
      <div className="space-y-1">
        <label
          className="text-xs text-gray-600 font-medium"
          title="CDS region to design primers for. Auto-selected by longest coding sequence."
        >
          Target Gene
        </label>
        {seqInfo && seqInfo.genes.length > 0 ? (
          <select
            className="w-full h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
            value={selectedGene}
            onChange={(e) => setSelectedGene(e.target.value)}
          >
            {[...seqInfo.genes]
              .sort((a, b) => a.cds_start - b.cds_start)
              .map((g) => {
                const isNamed = g.gene !== "ORF1" && g.gene !== "unknown";
                const label = isNamed ? `[${g.gene}]` : `(${g.gene})`;
                return (
                  <option key={g.cds_start} value={String(g.cds_start)}>
                    {label} {g.cds_start}-{g.cds_end} ({g.aa_length} aa)
                    {g.product ? ` ${g.product}` : ""}
                  </option>
                );
              })}
          </select>
        ) : (
          <span className="text-xs text-gray-400 italic block">
            Load a sequence file first
          </span>
        )}
      </div>

      {/* Organism */}
      <div className="space-y-1">
        <label
          className="text-xs text-gray-600 font-medium"
          title="Organism codon usage table for mutant codon selection."
        >
          Organism
        </label>
        <select
          className="w-full h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
          value={organism}
          onChange={(e) => setOrganism(e.target.value)}
        >
          <option value="ecoli">E. coli K-12</option>
          <option value="bsubtilis">B. subtilis 168</option>
          <option value="scerevisiae">S. cerevisiae</option>
        </select>
      </div>
    </>
  );
}
