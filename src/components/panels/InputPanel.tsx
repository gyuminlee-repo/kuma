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
  const positionDiversityEnabled = useAppStore((s) => s.positionDiversityEnabled);
  const setPositionDiversityEnabled = useAppStore((s) => s.setPositionDiversityEnabled);
  const maxPerPosition = useAppStore((s) => s.maxPerPosition);
  const setMaxPerPosition = useAppStore((s) => s.setMaxPerPosition);

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
            <div className="flex items-center gap-2 text-xs">
              <label className="flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  className="h-3 w-3 accent-green-600"
                  checked={positionDiversityEnabled}
                  onChange={(e) => setPositionDiversityEnabled(e.target.checked)}
                />
                <span className="text-gray-500">Position diversity</span>
              </label>
              {positionDiversityEnabled && (
                <>
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
                </>
              )}
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
