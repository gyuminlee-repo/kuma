import { useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { useAppStore } from "../../store/appStore";
import { basename } from "../../lib/utils";
import { Button } from "../ui/button";

async function browseFile(
  filters: { name: string; extensions: string[] }[],
  onSelect: (path: string) => Promise<void> | void,
) {
  const path = await open({ filters, multiple: false });
  if (path) await onSelect(path as string);
}

export function InputPanel() {
  const fastaPath = useAppStore((s) => s.fastaPath);
  const seqInfo = useAppStore((s) => s.seqInfo);
  const selectedGene = useAppStore((s) => s.selectedGene);
  const setSelectedGene = useAppStore((s) => s.setSelectedGene);
  const organism = useAppStore((s) => s.organism);
  const setOrganism = useAppStore((s) => s.setOrganism);
  const mutationInputMode = useAppStore((s) => s.mutationInputMode);
  const mutationText = useAppStore((s) => s.mutationText);
  const parsedMutations = useAppStore((s) => s.parsedMutations);
  const parseErrors = useAppStore((s) => s.parseErrors);
  const setMutationInputMode = useAppStore((s) => s.setMutationInputMode);
  const setMutationText = useAppStore((s) => s.setMutationText);
  const parseMutations = useAppStore((s) => s.parseMutations);
  const loadSequence = useAppStore((s) => s.loadSequence);
  const evolveproCsvPath = useAppStore((s) => s.evolveproCsvPath);
  const loadEvolveproCsv = useAppStore((s) => s.loadEvolveproCsv);
  const pipelineMode = useAppStore((s) => s.pipelineMode);
  const setPipelineMode = useAppStore((s) => s.setPipelineMode);
  const positionDiversityEnabled = useAppStore((s) => s.positionDiversityEnabled);
  const setPositionDiversityEnabled = useAppStore((s) => s.setPositionDiversityEnabled);
  const maxPerPosition = useAppStore((s) => s.maxPerPosition);
  const setMaxPerPosition = useAppStore((s) => s.setMaxPerPosition);
  const domainDiversityEnabled = useAppStore((s) => s.domainDiversityEnabled);
  const setDomainDiversityEnabled = useAppStore((s) => s.setDomainDiversityEnabled);
  const domainStrategy = useAppStore((s) => s.domainStrategy);
  const setDomainStrategy = useAppStore((s) => s.setDomainStrategy);
  const domains = useAppStore((s) => s.domains);
  const setDomains = useAppStore((s) => s.setDomains);
  const toggleDomain = useAppStore((s) => s.toggleDomain);
  const disabledDomains = useAppStore((s) => s.disabledDomains);
  const fetchDomains = useAppStore((s) => s.fetchDomains);
  const domainLoading = useAppStore((s) => s.domainLoading);
  const uniprotAccession = useAppStore((s) => s.uniprotAccession);
  const paretoDiversityEnabled = useAppStore((s) => s.paretoDiversityEnabled);
  const setParetoDiversityEnabled = useAppStore((s) => s.setParetoDiversityEnabled);
  const entropyWeightEnabled = useAppStore((s) => s.entropyWeightEnabled);
  const setEntropyWeightEnabled = useAppStore((s) => s.setEntropyWeightEnabled);
  const esmEmbeddingLoaded = useAppStore((s) => s.esmEmbeddingLoaded);
  const esmEmbeddingLoading = useAppStore((s) => s.esmEmbeddingLoading);
  const uniprotCandidates = useAppStore((s) => s.uniprotCandidates);
  const uniprotSearching = useAppStore((s) => s.uniprotSearching);
  const searchUniprot = useAppStore((s) => s.searchUniprot);
  const domainStats = useAppStore((s) => s.domainStats);
  const evolveproTotalCount = useAppStore((s) => s.evolveproTotalCount);
  const loadSampleData = useAppStore((s) => s.loadSampleData);

  // Local state for UniProt accession input
  const [accessionInput, setAccessionInput] = useState(uniprotAccession);
  useEffect(() => setAccessionInput(uniprotAccession), [uniprotAccession]);
  const [addingDomain, setAddingDomain] = useState(false);
  const [newDomainName, setNewDomainName] = useState("");
  const [newDomainStart, setNewDomainStart] = useState("");
  const [newDomainEnd, setNewDomainEnd] = useState("");

  // Local string state for maxPerPosition input
  const [maxPerPosStr, setMaxPerPosStr] = useState(String(maxPerPosition));
  useEffect(() => setMaxPerPosStr(String(maxPerPosition)), [maxPerPosition]);
  const commitMaxPerPos = () => { const n = parseInt(maxPerPosStr); if (isFinite(n) && n >= 1) setMaxPerPosition(n); };
  const onMaxPerPosKeyDown = (e: KeyboardEvent<HTMLInputElement>) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); };

  // Debounced mutation validation
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (mutationInputMode !== "text" || !mutationText.trim()) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      parseMutations();
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [mutationText, mutationInputMode, parseMutations]);

  const mutationCount = useMemo(
    () => mutationText.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).length,
    [mutationText],
  );

  const selectedCount = mutationCount;

  return (
    <div className="border border-gray-300 rounded p-3 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
          Input
        </h3>
        <button
          className="text-[10px] text-blue-500 hover:text-blue-700 underline underline-offset-2"
          onClick={loadSampleData}
          title="Load sample GenBank + EVOLVEpro CSV to see an example result"
        >
          Try sample →
        </button>
      </div>

      {/* Sequence File */}
      <div className="space-y-1">
        <label className="text-xs text-gray-600 font-medium">Sequence File</label>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={() => browseFile(
              [
                { name: "Sequence (GenBank/SnapGene)", extensions: ["gb", "gbff", "gbk", "dna"] },
                { name: "FASTA", extensions: ["fa", "fasta", "fna"] },
                { name: "All Files", extensions: ["*"] },
              ],
              loadSequence,
            )}
            className="flex-shrink-0"
          >
            Browse
          </Button>
          <span className="text-xs text-gray-500 truncate self-center">
            {fastaPath
              ? basename(fastaPath)
              : "No file selected (.gb / .dna)"}
          </span>
        </div>
        {seqInfo && (
          <div className="text-xs text-gray-500 space-y-0.5 bg-gray-50 rounded p-2">
            <div className="truncate" title={seqInfo.header}>
              {seqInfo.header}
            </div>
            <div>{seqInfo.seq_length.toLocaleString()} bp | {seqInfo.genes.length} gene(s)</div>
          </div>
        )}
      </div>

      {/* Target Gene */}
      <div className="space-y-1">
        <label className="text-xs text-gray-600 font-medium" title="CDS region to design primers for. Auto-selected by longest coding sequence.">
          Target Gene
        </label>
        {seqInfo && seqInfo.genes.length > 0 ? (
          <select
            className="w-full h-7 text-xs border border-gray-300 rounded px-2 focus:outline-none focus:ring-1 focus:ring-green-500"
            value={selectedGene}
            onChange={(e) => setSelectedGene(e.target.value)}
          >
            {[...seqInfo.genes].sort((a, b) => a.cds_start - b.cds_start).map((g) => {
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
          <span className="text-xs text-gray-400 italic block">Load a sequence file first</span>
        )}
      </div>

      {/* Organism */}
      <div className="space-y-1">
        <label className="text-xs text-gray-600 font-medium" title="Organism codon usage table for mutant codon selection.">
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

      {/* Mutations */}
      <div className="space-y-1">
        <label className="text-xs text-gray-600 font-medium">Mutations</label>
        <div className="flex gap-2 text-xs">
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="mutInput"
              checked={mutationInputMode === "text"}
              onChange={() => setMutationInputMode("text")}
              className="w-3 h-3"
            />
            Text
          </label>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="mutInput"
              checked={mutationInputMode === "evolvepro"}
              onChange={() => setMutationInputMode("evolvepro")}
              className="w-3 h-3"
            />
            EVOLVEpro
          </label>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="mutInput"
              checked={mutationInputMode === "multi-evolve"}
              onChange={() => setMutationInputMode("multi-evolve")}
              className="w-3 h-3"
            />
            MULTI-evolve
          </label>
        </div>

        {mutationInputMode === "text" && (
          <textarea
            className="w-full h-32 text-xs font-mono border border-gray-300 rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-green-500"
            placeholder={"Q232A\nY233A\nE335A\nA40P/E61Y\n..."}
            value={mutationText}
            onChange={(e) => setMutationText(e.target.value)}
          />
        )}

        {(mutationInputMode === "evolvepro" || mutationInputMode === "multi-evolve") && (
          <div className="space-y-2">
            {/* CSV file loader */}
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => browseFile(
                  [{ name: mutationInputMode === "multi-evolve" ? "MULTI-evolve CSV" : "EVOLVEpro CSV", extensions: ["csv"] }],
                  loadEvolveproCsv,
                )}
                className="flex-shrink-0"
              >
                Browse
              </Button>
              <span className="text-xs text-gray-500 truncate self-center">
                {evolveproCsvPath
                  ? basename(evolveproCsvPath)
                  : "No file selected"}
              </span>
            </div>

            {/* Variant count summary */}
            {evolveproTotalCount > 0 && (
              <div className="text-xs font-medium text-gray-700 bg-gray-50 rounded px-2 py-1.5">
                {mutationInputMode === "multi-evolve" ? "MULTI-evolve" : "EVOLVEpro"}: {evolveproTotalCount} variants loaded
              </div>
            )}

            {/* Selection mode / Pipeline UI — only for evolvepro (multi-evolve uses all combinations) */}
            {mutationInputMode === "multi-evolve" ? (
              <div className="text-xs text-gray-500 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
                MULTI-evolve: all combinations selected (no filtering)
              </div>
            ) : (
            <>
            <div className="space-y-1">
              <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Selection mode</div>
              <div className="space-y-0.5">
                <label className="flex items-center gap-1.5 cursor-pointer text-xs">
                  <input
                    type="radio"
                    name="selectionMode"
                    className="w-3 h-3"
                    checked={!pipelineMode}
                    onChange={() => setPipelineMode(false)}
                  />
                  <span className="text-gray-600">Top-N only</span>
                  <span className="text-[10px] text-gray-400">(y_pred descending)</span>
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer text-xs">
                  <input
                    type="radio"
                    name="selectionMode"
                    className="w-3 h-3"
                    checked={pipelineMode}
                    onChange={() => setPipelineMode(true)}
                  />
                  <span className="text-gray-600">Pipeline</span>
                  <span className="text-[10px] text-gray-400">(step-by-step filtering)</span>
                </label>
              </div>
            </div>

            {/* Pipeline UI */}
            {pipelineMode && (
              <div className="relative ml-1">
                {/* Pipeline header */}
                <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Pipeline</div>

                {/* Pipeline vertical connector */}
                <div className="border-l-2 border-gray-300 ml-2 pl-3 space-y-2">

                  {/* Step 1: Pre-filter */}
                  <PipelineStep
                    step={1}
                    label="Pre-filter"
                    enabled={positionDiversityEnabled}
                    onToggle={setPositionDiversityEnabled}
                  >
                    <div className="flex items-center gap-1 text-xs">
                      <span className="text-gray-500">Position cap: max</span>
                      <input
                        type="number"
                        min={1}
                        max={20}
                        className="w-10 h-5 text-xs border border-gray-300 rounded px-1 text-center focus:outline-none focus:ring-1 focus:ring-green-500"
                        value={maxPerPosStr}
                        onChange={(e: ChangeEvent<HTMLInputElement>) => setMaxPerPosStr(e.target.value)}
                        onBlur={commitMaxPerPos}
                        onKeyDown={onMaxPerPosKeyDown}
                      />
                      <span className="text-gray-500">/position</span>
                    </div>
                  </PipelineStep>

                  {/* Step connector arrow */}
                  <PipelineArrow active={positionDiversityEnabled} />

                  {/* Step 2: Domain allocation */}
                  <PipelineStep
                    step={2}
                    label="Domain allocation"
                    enabled={domainDiversityEnabled}
                    onToggle={setDomainDiversityEnabled}
                  >
                    <div className="space-y-1.5">
                      {/* Domain strategy radio */}
                      <div className="flex gap-2 text-[10px] text-gray-500">
                        <label className="flex items-center gap-0.5 cursor-pointer">
                          <input type="radio" name="domainStrategy" className="w-2.5 h-2.5"
                            checked={domainStrategy === "proportional"} onChange={() => setDomainStrategy("proportional")} />
                          Proportional
                        </label>
                        <label className="flex items-center gap-0.5 cursor-pointer">
                          <input type="radio" name="domainStrategy" className="w-2.5 h-2.5"
                            checked={domainStrategy === "equal"} onChange={() => setDomainStrategy("equal")} />
                          Equal
                        </label>
                      </div>

                      {/* UniProt lookup */}
                      <div className="space-y-1">
                        <div className="flex gap-1 items-center">
                          <input
                            type="text"
                            className="w-24 h-5 text-xs border border-gray-300 rounded px-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
                            placeholder="UniProt ID"
                            value={accessionInput}
                            onChange={(e) => setAccessionInput(e.target.value.trim())}
                            onKeyDown={(e) => { if (e.key === "Enter" && accessionInput) fetchDomains(accessionInput); }}
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-5 text-[10px] px-2"
                            onClick={() => accessionInput && fetchDomains(accessionInput, true)}
                            disabled={domainLoading || !accessionInput}
                          >
                            {domainLoading ? "..." : "Fetch"}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-5 text-[10px] px-2"
                            onClick={() => {
                              if (!seqInfo?.genes.length) return;
                              const gene = seqInfo.genes.find((g) => String(g.cds_start) === useAppStore.getState().selectedGene) ?? seqInfo.genes[0];
                              searchUniprot(gene.gene, gene.organism ?? "", gene.translation ?? "", gene.uniprot_accession ?? "");
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
                                className={`flex items-center gap-1 text-[10px] w-full text-left px-1 py-0.5 rounded hover:bg-blue-50 ${accessionInput === c.accession ? "bg-blue-100" : ""}`}
                                onClick={() => {
                                  setAccessionInput(c.accession);
                                  fetchDomains(c.accession);
                                }}
                                title={`${c.organism} | ${c.length} aa | ${c.identity}% identity`}
                              >
                                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${c.identity === 100 ? "bg-green-500" : c.identity >= 90 ? "bg-yellow-500" : "bg-gray-400"}`} />
                                <span className="font-mono text-blue-700">{c.accession}</span>
                                <span className="text-gray-500 truncate">{c.name}</span>
                                <span className={`ml-auto flex-shrink-0 ${c.identity === 100 ? "text-green-600 font-semibold" : "text-gray-400"}`}>
                                  {c.identity}%
                                </span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Domain list */}
                      {domains.length > 0 && (
                        <div className="space-y-0.5">
                          {domains.map((d) => {
                            const key = `${d.name}-${d.start}`;
                            const disabled = disabledDomains.has(key);
                            const stat = domainStats[d.name];
                            return (
                              <label key={key} className={`flex items-center gap-1 text-[10px] cursor-pointer ${disabled ? "opacity-40" : ""}`}
                                title={`${d.id} (${d.db})`}>
                                <input type="checkbox" className="w-2.5 h-2.5"
                                  checked={!disabled}
                                  onChange={() => toggleDomain(key)} />
                                <span className="w-2 h-2 rounded-sm bg-blue-400 inline-block flex-shrink-0" />
                                <span className="text-gray-600 truncate">
                                  {d.name} ({d.start}-{d.end})
                                </span>
                                {stat && !disabled && (
                                  <span className={`ml-auto flex-shrink-0 tabular-nums ${stat.selected < stat.quota ? "text-amber-600" : "text-gray-400"}`}>
                                    {stat.selected}/{stat.quota}
                                    {stat.selected < stat.quota && " \u26A0"}
                                  </span>
                                )}
                              </label>
                            );
                          })}
                        </div>
                      )}

                      {/* Add manually */}
                      {!addingDomain ? (
                        <button
                          className="text-[10px] text-blue-500 hover:text-blue-700"
                          onClick={() => setAddingDomain(true)}
                        >
                          + Add manually
                        </button>
                      ) : (
                        <div className="flex gap-1 items-center text-[10px]">
                          <input type="text" placeholder="Name" className="w-16 h-4 border border-gray-300 rounded px-1 text-[10px]"
                            value={newDomainName} onChange={(e) => setNewDomainName(e.target.value)} />
                          <input type="number" placeholder="Start" className="w-10 h-4 border border-gray-300 rounded px-0.5 text-[10px] text-center"
                            value={newDomainStart} onChange={(e) => setNewDomainStart(e.target.value)} />
                          <span className="text-gray-400">-</span>
                          <input type="number" placeholder="End" className="w-10 h-4 border border-gray-300 rounded px-0.5 text-[10px] text-center"
                            value={newDomainEnd} onChange={(e) => setNewDomainEnd(e.target.value)} />
                          <button className="text-green-600 hover:text-green-800 font-bold"
                            onClick={() => {
                              const s = parseInt(newDomainStart), e = parseInt(newDomainEnd);
                              if (newDomainName && isFinite(s) && isFinite(e) && s < e) {
                                setDomains([...domains, { name: newDomainName, id: "manual", start: s, end: e, db: "manual" }]);
                                setNewDomainName(""); setNewDomainStart(""); setNewDomainEnd(""); setAddingDomain(false);
                              }
                            }}>
                            &#10003;
                          </button>
                          <button className="text-gray-400 hover:text-gray-600" onClick={() => setAddingDomain(false)}>&times;</button>
                        </div>
                      )}
                    </div>
                  </PipelineStep>

                  {/* Step connector arrow */}
                  <PipelineArrow active={domainDiversityEnabled} />

                  {/* Step 3: Optimization */}
                  <PipelineStep
                    step={3}
                    label="Optimization"
                    enabled={paretoDiversityEnabled}
                    onToggle={setParetoDiversityEnabled}
                  >
                    <div className="space-y-1.5">
                      <div className="text-xs text-gray-500">
                        {esmEmbeddingLoaded
                          ? "ESM-2 structural distance"
                          : "Pareto spread (maximize position distance)"}
                        {esmEmbeddingLoading && (
                          <span className="ml-1.5 text-amber-600">(loading ESM-2...)</span>
                        )}
                        {esmEmbeddingLoaded && (
                          <span className="ml-1.5 inline-flex items-center rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-medium text-indigo-700">
                            ESM-2
                          </span>
                        )}
                      </div>
                      <label
                        className="flex items-center gap-1.5 cursor-pointer text-[10px] text-gray-500"
                        title="Blend position entropy into selection score (weight 0.3). Positions where many mutations score similarly are prioritised — helps escape local optima."
                      >
                        <input
                          type="checkbox"
                          className="h-2.5 w-2.5 accent-purple-600"
                          checked={entropyWeightEnabled}
                          onChange={(e) => setEntropyWeightEnabled(e.target.checked)}
                        />
                        Entropy-guided
                        <span className="ml-0.5 inline-flex items-center rounded bg-purple-100 px-1 py-0.5 text-[9px] font-medium text-purple-700">
                          β
                        </span>
                      </label>
                    </div>
                  </PipelineStep>
                </div>

                {/* Final count */}
                <div className="ml-2 pl-3 mt-2 text-xs font-medium text-gray-700 border-l-2 border-transparent">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 mr-1.5 -translate-y-px" />
                  {selectedCount} variants selected
                </div>
              </div>
            )}
            </>
            )}

            {/* Editable variant textarea */}
            {mutationText && (
              <textarea
                className="w-full h-32 text-xs font-mono border border-gray-300 rounded p-2 resize-none bg-gray-50"
                value={mutationText}
                onChange={(e) => setMutationText(e.target.value)}
                title="Top-N variants by y_pred (editable)"
              />
            )}
          </div>
        )}

        {mutationText.trim() && (
          <div className="text-xs text-gray-400">
            {mutationCount} mutations entered
            {parsedMutations.length > 0 && (
              <span className="text-green-600 ml-1">
                ({parsedMutations.length} validated)
              </span>
            )}
            {parseErrors.length > 0 && (
              <span className="text-red-500 ml-1">
                ({parseErrors.length} failed)
              </span>
            )}
          </div>
        )}
        {parseErrors.length > 0 && (
          <div className="text-[10px] text-red-500 bg-red-50 rounded px-2 py-1 space-y-0.5 max-h-16 overflow-auto">
            {parseErrors.map((e) => (
              <div key={e.line}>
                L{e.line}: <span className="font-mono">{e.raw}</span> — {e.reason}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Pipeline sub-components ──────────────────────────────── */

function PipelineStep({
  step,
  label,
  enabled,
  onToggle,
  children,
}: {
  step: number;
  label: string;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <div className={`relative transition-opacity ${enabled ? "opacity-100" : "opacity-50"}`}>
      {/* Step dot on the vertical line */}
      <div className={`absolute -left-[calc(0.75rem+5px)] top-0.5 w-2 h-2 rounded-full border-2 ${enabled ? "bg-blue-500 border-blue-500" : "bg-white border-gray-300"}`} />

      <label className="flex items-center gap-1.5 cursor-pointer text-xs font-medium mb-1">
        <input
          type="checkbox"
          className="h-3 w-3 accent-blue-600"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
        />
        <span className="text-gray-600">
          Step {step}: {label}
        </span>
      </label>
      {enabled && (
        <div className="pl-4 space-y-1">
          {children}
        </div>
      )}
    </div>
  );
}

function PipelineArrow({ active }: { active: boolean }) {
  return (
    <div className={`flex items-center -ml-0.5 text-[10px] transition-opacity ${active ? "opacity-60" : "opacity-20"}`}>
      <span className="text-gray-400 select-none leading-none">{"\u25BC"}</span>
    </div>
  );
}
