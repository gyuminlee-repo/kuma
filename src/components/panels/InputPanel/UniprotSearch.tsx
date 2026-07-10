import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../../store/appStore";
import { Button } from "../../ui/button";

export function UniprotSearch() {
  const { t } = useTranslation();
  const uniprotAccession = useAppStore((s) => s.uniprotAccession);
  const uniprotCandidates = useAppStore((s) => s.uniprotCandidates);
  const uniprotSearching = useAppStore((s) => s.uniprotSearching);
  const searchUniprot = useAppStore((s) => s.searchUniprot);
  const fetchDomains = useAppStore((s) => s.fetchDomains);
  const domainLoading = useAppStore((s) => s.domainLoading);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const selectedGene = useAppStore((s) => s.selectedGene);
  const refDomainsLoading = useAppStore((s) => s.refDomainsLoading);
  const domains = useAppStore((s) => s.domains);
  const refDomains = useAppStore((s) => s.refDomains);
  const annotateReferenceDomains = useAppStore((s) => s.annotateReferenceDomains);

  const visibleCandidates = uniprotCandidates.slice(0, 10);
  const selectedGeneTranslation =
    seqInfo?.genes.find((g) => String(g.cds_start) === selectedGene)?.translation
    ?? seqInfo?.genes[0]?.translation;
  const hasTranslation = Boolean(selectedGeneTranslation);


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
      <div className="flex flex-wrap gap-1 items-center">
        <input
          type="text"
          className="w-24 h-6 text-xs border border-border rounded px-1 focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder={t("uniprotSearchExtra.placeholder")}
          value={accessionInput}
          onChange={(e) => setAccessionInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleManualFetch(true);
          }}
        />
        <Button
          variant="outline"
          size="sm"
          className="h-6 text-caption px-2"
          onClick={() => handleManualFetch(true)}
          disabled={domainLoading || uniprotSearching || !accessionInput}
          aria-busy={domainLoading}
          aria-label={t("uniprotSearch.fetchBtn")}
        >
          {domainLoading || uniprotSearching ? "..." : t("uniprotSearch.fetchBtn")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-6 text-caption px-2"
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
          aria-busy={uniprotSearching}
          aria-label={t("uniprotSearch.autoSearchBtn")}
          title={t("uniprotSearch.autoSearchTitle")}
        >
          {uniprotSearching ? "..." : t("uniprotSearch.autoSearchBtn")}
        </Button>
        <Button
          variant="default"
          size="sm"
          className="h-6 text-caption px-2"
          onClick={() => void annotateReferenceDomains()}
          disabled={!hasTranslation || refDomainsLoading || uniprotSearching || domainLoading}
          aria-busy={refDomainsLoading}
          aria-label={t("uniprotSearch.scanSequenceBtn")}
          title={t("uniprotSearch.scanSequenceTitle")}
        >
          {refDomainsLoading ? "..." : t("uniprotSearch.scanSequenceBtn")}
        </Button>
      </div>
      {refDomains.length > 0 ? (
        <p className="text-plate-tiny text-success">
          {t("uniprotSearch.referenceDomainsReady", { count: refDomains.length })}
        </p>
      ) : domains.length > 0 ? (
        <p className="text-plate-tiny text-warning">
          {t("uniprotSearch.accessionDomainsOnly")}
        </p>
      ) : null}
      {uniprotCandidates.length > 0 && (
        <div className="space-y-1">
          <div className="px-1 text-[11px] font-medium text-muted-foreground">
            {t("uniprotSearch.topCandidates", {
              shown: visibleCandidates.length,
              total: uniprotCandidates.length > visibleCandidates.length ? ` / ${uniprotCandidates.length}` : "",
            })}
          </div>
          <div className="space-y-0.5 max-h-40 overflow-auto rounded border border-border/70 bg-muted/20 p-1">
            {visibleCandidates.map((c) => (
            <button
              key={c.accession}
              className={`flex items-center gap-1 text-caption w-full text-left px-1 py-0.5 rounded hover:bg-info/5 ${
                accessionInput === c.accession ? "bg-info/10" : ""
              }`}
              onClick={() => {
                setAccessionInput(c.accession);
                fetchDomains(c.accession);
              }}
              title={`${c.organism} | ${c.length} aa | ${c.identity}% identity${c.has_structure ? " | AlphaFold structure available" : ""}${c.oligomeric === "multimer" && c.subunit ? ` | ${c.subunit}` : ""}`}
            >
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  c.identity === 100
                    ? "bg-success"
                    : c.identity >= 90
                      ? "bg-warning"
                      : "bg-muted-foreground/50"
                }`}
              />
              <span className="font-mono text-info">{c.accession}</span>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{c.name}</span>
              {c.has_structure && (
                <span className="flex-shrink-0 inline-flex items-center rounded bg-info/10 px-1 py-0.5 text-plate-tiny font-medium text-info" title={t("uniprotSearchExtra.afStructureTitle")}>
                  AF
                </span>
              )}
              {c.oligomeric === "multimer" && (
                <span className="flex-shrink-0 inline-flex items-center rounded bg-info/10 px-1 py-0.5 text-plate-tiny font-medium text-info" title={c.subunit ? `${c.subunit} · consider biological unit` : "Multimer · consider biological unit"}>
                  ⬡ {c.subunit ? c.subunit.split(/[.;(]/)[0].trim() : "Multimer"}
                </span>
              )}
              <span
                className={`ml-auto flex-shrink-0 ${
                  c.identity === 100 ? "text-success font-semibold" : "text-muted-foreground"
                }`}
              >
                {c.identity}%
              </span>
            </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
