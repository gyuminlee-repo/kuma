import { useEffect, useRef } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { useAppStore } from "../../store/appStore";
import { Button } from "../ui/button";

export function InputPanel() {
  const fastaPath = useAppStore((s) => s.fastaPath);
  const fastaInfo = useAppStore((s) => s.fastaInfo);
  const mutationInputMode = useAppStore((s) => s.mutationInputMode);
  const mutationText = useAppStore((s) => s.mutationText);
  const parsedMutations = useAppStore((s) => s.parsedMutations);
  const setMutationInputMode = useAppStore((s) => s.setMutationInputMode);
  const setMutationText = useAppStore((s) => s.setMutationText);
  const parseMutations = useAppStore((s) => s.parseMutations);
  const loadFasta = useAppStore((s) => s.loadFasta);

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

  async function handleBrowseFasta() {
    const path = await open({
      filters: [
        {
          name: "FASTA",
          extensions: ["fa", "fasta", "fna", "fas"],
        },
      ],
      multiple: false,
    });
    if (path) {
      await loadFasta(path as string);
    }
  }

  async function handleBrowseCsv() {
    const path = await open({
      filters: [{ name: "CSV", extensions: ["csv"] }],
      multiple: false,
    });
    if (path) {
      useAppStore.getState().setMutationCsvPath(path as string);
    }
  }

  const mutationCsvPath = useAppStore((s) => s.mutationCsvPath);

  return (
    <div className="border border-gray-300 rounded p-3 space-y-3">
      <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
        Input
      </h3>

      {/* FASTA */}
      <div className="space-y-1">
        <label className="text-xs text-gray-600 font-medium">FASTA File</label>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={handleBrowseFasta}
            className="flex-shrink-0"
          >
            Browse
          </Button>
          <span className="text-xs text-gray-500 truncate self-center">
            {fastaPath
              ? fastaPath.split(/[\\/]/).pop()
              : "No file selected"}
          </span>
        </div>
        {fastaInfo && (
          <div className="text-xs text-gray-500 space-y-0.5 bg-gray-50 rounded p-2">
            <div className="truncate" title={fastaInfo.header}>
              {fastaInfo.header}
            </div>
            <div>{fastaInfo.seq_length.toLocaleString()} bp</div>
            {fastaInfo.atg_positions.length > 0 && (
              <div>
                ATG @{" "}
                {fastaInfo.atg_positions
                  .slice(0, 5)
                  .map((p) => p.toLocaleString())
                  .join(", ")}
                {fastaInfo.atg_positions.length > 5 && " ..."}
              </div>
            )}
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
              checked={mutationInputMode === "csv"}
              onChange={() => setMutationInputMode("csv")}
              className="w-3 h-3"
            />
            CSV
          </label>
        </div>

        {mutationInputMode === "text" ? (
          <textarea
            className="w-full h-32 text-xs font-mono border border-gray-300 rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-green-500"
            placeholder={"Q232A\nY233A\nE335A\n..."}
            value={mutationText}
            onChange={(e) => setMutationText(e.target.value)}
          />
        ) : (
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={handleBrowseCsv}
              className="flex-shrink-0"
            >
              Browse CSV
            </Button>
            <span className="text-xs text-gray-500 truncate self-center">
              {mutationCsvPath
                ? mutationCsvPath.split(/[\\/]/).pop()
                : "No file selected"}
            </span>
          </div>
        )}

        {mutationInputMode === "text" && mutationText.trim() && (
          <div className="text-xs text-gray-400">
            {
              mutationText
                .split("\n")
                .filter((l) => l.trim()).length
            }{" "}
            mutations entered
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
