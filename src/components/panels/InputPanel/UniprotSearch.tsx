import { useState, useEffect } from "react";
import { useAppStore } from "../../../store/appStore";
import { Button } from "../../ui/button";

export function UniprotSearch() {
  const uniprotAccession = useAppStore((s) => s.uniprotAccession);
  const uniprotCandidates = useAppStore((s) => s.uniprotCandidates);
  const uniprotSearching = useAppStore((s) => s.uniprotSearching);
  const searchUniprot = useAppStore((s) => s.searchUniprot);
  const fetchDomains = useAppStore((s) => s.fetchDomains);
  const domainLoading = useAppStore((s) => s.domainLoading);
  const seqInfo = useAppStore((s) => s.seqInfo);

  const [accessionInput, setAccessionInput] = useState(uniprotAccession);
  useEffect(() => setAccessionInput(uniprotAccession), [uniprotAccession]);

  function handleManualFetch(clearCandidates = false) {
    const normalizedAccession = accessionInput.trim();
    if (!normalizedAccession) return;
    setAccessionInput(normalizedAccession);
    fetchDomains(normalizedAccession, clearCandidates);
  }

  return (
    <div className="space-y-1">
      <div className="flex gap-1 items-center">
        <input
          type="text"
          className="w-24 h-5 text-xs border border-gray-300 rounded px-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
          placeholder="UniProt ID"
          value={accessionInput}
          onChange={(e) => setAccessionInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleManualFetch(true);
          }}
        />
        <Button
          variant="outline"
          size="sm"
          className="h-5 text-[10px] px-2"
          onClick={() => handleManualFetch(true)}
          disabled={domainLoading || uniprotSearching || !accessionInput}
        >
          {domainLoading || uniprotSearching ? "..." : "Fetch"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-5 text-[10px] px-2"
          onClick={() => {
            if (!seqInfo?.genes.length) return;
            const gene =
              seqInfo.genes.find(
                (g) => String(g.cds_start) === useAppStore.getState().selectedGene,
              ) ?? seqInfo.genes[0];
            searchUniprot(
              gene.gene,
              gene.organism ?? "",
              gene.translation ?? "",
              gene.uniprot_accession ?? "",
            );
          }}
          disabled={uniprotSearching || !seqInfo?.genes.length}
          title="Search UniProt using gene info from the loaded sequence file"
        >
          {uniprotSearching ? "..." : "Auto Search"}
        </Button>
      </div>
      {uniprotCandidates.length > 0 && (
        <div className="space-y-0.5 max-h-24 overflow-auto">
          {uniprotCandidates.map((c) => (
            <button
              key={c.accession}
              className={`flex items-center gap-1 text-[10px] w-full text-left px-1 py-0.5 rounded hover:bg-blue-50 ${
                accessionInput === c.accession ? "bg-blue-100" : ""
              }`}
              onClick={() => {
                setAccessionInput(c.accession);
                fetchDomains(c.accession);
              }}
              title={`${c.organism} | ${c.length} aa | ${c.identity}% identity${c.has_structure ? " | AlphaFold structure available" : ""}`}
            >
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  c.identity === 100
                    ? "bg-green-500"
                    : c.identity >= 90
                      ? "bg-yellow-500"
                      : "bg-gray-400"
                }`}
              />
              <span className="font-mono text-blue-700">{c.accession}</span>
              <span className="text-gray-500 truncate">{c.name}</span>
              {c.has_structure && (
                <span className="flex-shrink-0 inline-flex items-center rounded bg-indigo-100 px-1 py-0.5 text-[9px] font-medium text-indigo-700" title="AlphaFold structure available">
                  AF
                </span>
              )}
              <span
                className={`ml-auto flex-shrink-0 ${
                  c.identity === 100 ? "text-green-600 font-semibold" : "text-gray-400"
                }`}
              >
                {c.identity}%
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
