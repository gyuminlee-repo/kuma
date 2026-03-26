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
  const selectionStrategy = useAppStore((s) => s.selectionStrategy);
  const setSelectionStrategy = useAppStore((s) => s.setSelectionStrategy);
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

  return (
    <div className="border border-gray-300 rounded p-3 space-y-3">
      <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
        Input
      </h3>

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
        </div>

        {mutationInputMode === "text" && (
          <textarea
            className="w-full h-32 text-xs font-mono border border-gray-300 rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-green-500"
            placeholder={"Q232A\nY233A\nE335A\n..."}
            value={mutationText}
            onChange={(e) => setMutationText(e.target.value)}
          />
        )}

        {mutationInputMode === "evolvepro" && (
          <div className="space-y-1">
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => browseFile(
                  [{ name: "EVOLVEpro CSV", extensions: ["csv"] }],
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
            <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Selection Strategy</div>
            <div className="space-y-1">
              <label className="flex items-center gap-1 cursor-pointer text-xs"
                title="Select top-N variants by predicted fitness score (y_pred descending). Base ranking method.">
                <input type="checkbox" className="h-3 w-3 accent-green-600"
                  checked={selectionStrategy !== "none"}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectionStrategy("topn");
                    } else {
                      setSelectionStrategy("none");
                      setPositionDiversityEnabled(false);
                      setDomainDiversityEnabled(false);
                      setParetoDiversityEnabled(false);
                    }
                  }} />
                <span className="text-gray-600">Top-N by y_pred</span>
              </label>
              <label className="flex items-center gap-1 cursor-pointer text-xs"
                title="Limit mutations per amino acid position to avoid over-sampling at hot spots. Combinable with other diversity options.">
                <input type="checkbox" className="h-3 w-3 accent-green-600"
                  checked={positionDiversityEnabled}
                  onChange={(e) => setPositionDiversityEnabled(e.target.checked)} />
                <span className="text-gray-600">Position diversity</span>
              </label>
              {positionDiversityEnabled && (
                <div className="flex items-center gap-1 pl-5 text-xs">
                  <span className="text-gray-400">max</span>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    className="w-12 h-5 text-xs border border-gray-300 rounded px-1 text-center focus:outline-none focus:ring-1 focus:ring-green-500"
                    value={maxPerPosStr}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setMaxPerPosStr(e.target.value)}
                    onBlur={commitMaxPerPos}
                    onKeyDown={onMaxPerPosKeyDown}
                  />
                  <span className="text-gray-400">per position</span>
                </div>
              )}
              <label className="flex items-center gap-1 cursor-pointer text-xs"
                title="Allocate mutation quota per protein domain (proportional to length or equal). Requires UniProt domain info. Combinable with other options.">
                <input type="checkbox" className="h-3 w-3 accent-blue-600"
                  checked={domainDiversityEnabled}
                  onChange={(e) => setDomainDiversityEnabled(e.target.checked)} />
                <span className="text-gray-600">Domain diversity</span>
              </label>
              {domainDiversityEnabled && (
                <div className="space-y-1.5 pl-4">
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
                      onClick={() => accessionInput && fetchDomains(accessionInput)}
                      disabled={domainLoading || !accessionInput}
                    >
                      {domainLoading ? "..." : "Fetch"}
                    </Button>
                  </div>
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
                  {domains.length > 0 && (
                    <div className="space-y-0.5">
                      {domains.map((d) => {
                        const key = `${d.name}-${d.start}`;
                        const disabled = disabledDomains.has(key);
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
                          </label>
                        );
                      })}
                    </div>
                  )}
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
              )}
              {/* Pareto Diversity */}
              <label className="flex items-center gap-1 cursor-pointer text-xs"
                title="Greedy maximin selection: maximize minimum position distance between selected mutations. Prevents clustering at nearby positions. Combinable with Domain diversity.">
                <input type="checkbox" className="h-3 w-3 accent-purple-600"
                  checked={paretoDiversityEnabled}
                  onChange={(e) => setParetoDiversityEnabled(e.target.checked)} />
                <span className="text-gray-600">Pareto diversity</span>
                <span className="text-[10px] text-gray-400">(position spread)</span>
              </label>
            </div>
            {mutationText && (
              <textarea
                className="w-full h-32 text-xs font-mono border border-gray-300 rounded p-2 resize-none bg-gray-50"
                value={mutationText}
                onChange={(e) => setMutationText(e.target.value)}
                title="Top-96 variants by y_pred (editable)"
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
