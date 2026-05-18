import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { useAppStore } from "../../../store/appStore";
import { basename } from "../../../lib/utils";
import { browseFile } from "../../../lib/file-utils";
import { Button } from "../../ui/button";
import { InlineHelp } from "../../ui/InlineHelp";

const SEQUENCE_DROP_EXTENSIONS = new Set([".gb", ".gbk", ".gbff", ".dna", ".fa", ".fasta"]);

export function SequenceInput() {
  const { t } = useTranslation();
  const [isDragOver, setIsDragOver] = useState(false);
  const fastaPath = useAppStore((s) => s.fastaPath);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const selectedGene = useAppStore((s) => s.selectedGene);
  const setSelectedGene = useAppStore((s) => s.setSelectedGene);
  const organism = useAppStore((s) => s.organism);
  const setOrganism = useAppStore((s) => s.setOrganism);
  const loadSequence = useAppStore((s) => s.loadSequence);
  const uniprotSearching = useAppStore((s) => s.uniprotSearching);

  // Item 3: Drag-and-drop visual feedback via Tauri webview event
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    getCurrentWebview()
      .onDragDropEvent((event) => {
        if (event.payload.type === "enter" || event.payload.type === "over") {
          const paths = "paths" in event.payload ? event.payload.paths : [];
          const hasSeqFile = paths.some((p) => {
            const ext = p.slice(p.lastIndexOf(".")).toLowerCase();
            return SEQUENCE_DROP_EXTENSIONS.has(ext);
          });
          if (hasSeqFile) setIsDragOver(true);
        } else if (event.payload.type === "leave" || event.payload.type === "drop") {
          setIsDragOver(false);
        }
      })
      .then((fn) => { unlisten = fn; })
      .catch(() => { /* webview API not available in test env */ });
    return () => { unlisten?.(); };
  }, []);

  return (
    <>
      {/* Sequence File */}
      <div
        className={`space-y-1 rounded-control border transition-colors duration-fast ${isDragOver ? "border-dashed border-info bg-info/5" : "border-transparent"}`}
        aria-label={t("sequenceInput.dropAriaLabel")}
      >
        <label className="text-xs font-medium text-foreground inline-flex items-center gap-1.5">
          {t("sequenceInput.sequenceFile")}
          <InlineHelp text={t("sequenceInput.sequenceFileHelp")} />
        </label>
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
            {t("sequenceInput.browse")}
          </Button>
          <span className="self-center truncate text-xs text-muted-foreground">
            {fastaPath ? basename(fastaPath) : t("sequenceInput.noFileSelected")}
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
          <div className="flex items-center gap-1.5 rounded-control border border-info/20 bg-info/10 px-2 py-1 text-xs text-info">
            <svg className="animate-spin w-3 h-3 flex-shrink-0" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            {t("sequenceInput.uniprotBlastInProgress")}
          </div>
        )}
      </div>

      {/* Target Gene */}
      <div className="space-y-1">
        <label
          className="text-xs font-medium text-foreground"
          title={t("sequenceInput.targetGeneTitle")}
        >
          {t("sequenceInput.targetGene")}
        </label>
        {seqInfo && seqInfo.genes.length > 0 ? (
          <select
            className="h-8 w-full rounded-control border border-border bg-card px-3 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
            value={selectedGene}
            onChange={(e) => setSelectedGene(e.target.value)}
          >
            {[...seqInfo.genes]
              .sort((a, b) => a.cds_start - b.cds_start)
              .map((g) => {
                const isNamed = g.gene !== "ORF1" && g.gene !== "unknown";
                const label = isNamed ? `[${g.gene}]` : `(${g.gene})`;
                const tooltip = [
                  `Gene: ${g.gene}`,
                  `CDS: ${g.cds_start}-${g.cds_end} (${g.aa_length} aa)`,
                  g.product ? `Product: ${g.product}` : "",
                ]
                  .filter(Boolean)
                  .join("\n");
                return (
                  <option key={g.cds_start} value={String(g.cds_start)} title={tooltip}>
                    {label} {g.cds_start}-{g.cds_end} ({g.aa_length} aa)
                    {g.product ? ` ${g.product}` : ""}
                  </option>
                );
              })}
          </select>
        ) : (
          <span className="block text-xs italic text-muted-foreground">
            {t("sequenceInput.loadFirst")}
          </span>
        )}
      </div>

      {/* Organism */}
      <div className="space-y-1">
        <label
          className="text-xs font-medium text-foreground"
          title={t("sequenceInput.organismTitle")}
        >
          {t("sequenceInput.organism")}
        </label>
        <select
          className="h-8 w-full rounded-control border border-border bg-card px-3 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
          value={organism}
          onChange={(e) => setOrganism(e.target.value)}
        >
          <option value="ecoli" title={t("sequenceInput.ecoliTitle")}>E. coli K-12</option>
          <option value="bsubtilis" title={t("sequenceInput.bsubtilisTitle")}>B. subtilis 168</option>
          <option value="scerevisiae" title={t("sequenceInput.scerevisiaeTitle")}>S. cerevisiae</option>
        </select>
      </div>
    </>
  );
}
