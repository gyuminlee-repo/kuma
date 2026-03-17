import { useEffect, useMemo, useRef } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { useAppStore } from "../../store/appStore";
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
  const setMutationInputMode = useAppStore((s) => s.setMutationInputMode);
  const setMutationText = useAppStore((s) => s.setMutationText);
  const parseMutations = useAppStore((s) => s.parseMutations);
  const loadSequence = useAppStore((s) => s.loadSequence);
  const evolveproCsvPath = useAppStore((s) => s.evolveproCsvPath);
  const loadEvolveproCsv = useAppStore((s) => s.loadEvolveproCsv);

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
    () => mutationText.split("\n").filter((l) => l.trim()).length,
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
                { name: "Sequence (GenBank/FASTA/SnapGene)", extensions: ["gb", "gbff", "gbk", "fa", "fasta", "fna", "fas", "dna"] },
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
              ? fastaPath.split(/[\\/]/).pop()
              : "No file selected (.gb / .fasta / .dna)"}
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
                  ? evolveproCsvPath.split(/[\\/]/).pop()
                  : "No file selected"}
              </span>
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
          </div>
        )}
      </div>
    </div>
  );
}
