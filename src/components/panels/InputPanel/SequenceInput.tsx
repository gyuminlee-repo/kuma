import { useAppStore } from "../../../store/appStore";
import { basename } from "../../../lib/utils";
import { browseFile } from "../../../lib/file-utils";
import { Button } from "../../ui/button";

export function SequenceInput() {
  const fastaPath = useAppStore((s) => s.fastaPath);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const selectedGene = useAppStore((s) => s.selectedGene);
  const setSelectedGene = useAppStore((s) => s.setSelectedGene);
  const organism = useAppStore((s) => s.organism);
  const setOrganism = useAppStore((s) => s.setOrganism);
  const loadSequence = useAppStore((s) => s.loadSequence);
  const uniprotSearching = useAppStore((s) => s.uniprotSearching);

  return (
    <>
      {/* Sequence File */}
      <div className="space-y-1">
        <label className="text-xs font-medium text-slate-700">Sequence File</label>
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
          <span className="self-center truncate text-xs text-slate-500">
            {fastaPath ? basename(fastaPath) : "No file selected (.gb / .dna)"}
          </span>
        </div>
        {seqInfo && (
          <div className="space-y-0.5 rounded-md border border-border bg-muted/50 p-2 text-xs text-muted-foreground">
            <div className="truncate" title={seqInfo.header}>
              {seqInfo.header}
            </div>
            <div>
              {seqInfo.seq_length.toLocaleString()} bp | {seqInfo.genes.length} gene(s)
            </div>
          </div>
        )}
        {seqInfo && uniprotSearching && (
          <div className="flex items-center gap-1.5 rounded-xl border border-blue-200 bg-blue-50 px-2 py-1 text-xs text-blue-700">
            <svg className="animate-spin w-3 h-3 flex-shrink-0" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            UniProt BLAST search in progress… (Step 2 available after)
          </div>
        )}
      </div>

      {/* Target Gene */}
      <div className="space-y-1">
        <label
          className="text-xs font-medium text-slate-700"
          title="CDS region to design primers for. Auto-selected by longest coding sequence."
        >
          Target Gene
        </label>
        {seqInfo && seqInfo.genes.length > 0 ? (
          <select
            className="h-8 w-full rounded-xl border border-slate-300 bg-white px-3 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
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
          <span className="block text-xs italic text-slate-400">
            Load a sequence file first
          </span>
        )}
      </div>

      {/* Organism */}
      <div className="space-y-1">
        <label
          className="text-xs font-medium text-slate-700"
          title="Organism codon usage table for mutant codon selection."
        >
          Organism
        </label>
        <select
          className="h-8 w-full rounded-xl border border-slate-300 bg-white px-3 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
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
