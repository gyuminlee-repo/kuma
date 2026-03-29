import { useEffect, useMemo, useRef } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { useAppStore } from "../../../store/appStore";
import { basename } from "../../../lib/utils";
import { Button } from "../../ui/button";
import { DiversityOptions } from "./DiversityOptions";

async function browseFile(
  filters: { name: string; extensions: string[] }[],
  onSelect: (path: string) => Promise<void> | void,
) {
  const path = await open({ filters, multiple: false });
  if (path) await onSelect(path as string);
}

export function MutationInput() {
  const mutationInputMode = useAppStore((s) => s.mutationInputMode);
  const mutationText = useAppStore((s) => s.mutationText);
  const parsedMutations = useAppStore((s) => s.parsedMutations);
  const parseErrors = useAppStore((s) => s.parseErrors);
  const setMutationInputMode = useAppStore((s) => s.setMutationInputMode);
  const setMutationText = useAppStore((s) => s.setMutationText);
  const parseMutations = useAppStore((s) => s.parseMutations);
  const evolveproCsvPath = useAppStore((s) => s.evolveproCsvPath);
  const loadEvolveproCsv = useAppStore((s) => s.loadEvolveproCsv);
  const pipelineMode = useAppStore((s) => s.pipelineMode);
  const setPipelineMode = useAppStore((s) => s.setPipelineMode);
  const evolveproTotalCount = useAppStore((s) => s.evolveproTotalCount);

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
    () =>
      mutationText
        .split("\n")
        .filter((l) => l.trim() && !l.trim().startsWith("#")).length,
    [mutationText],
  );

  return (
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
              onClick={() =>
                browseFile(
                  [
                    {
                      name:
                        mutationInputMode === "multi-evolve"
                          ? "MULTI-evolve CSV"
                          : "EVOLVEpro CSV",
                      extensions: ["csv"],
                    },
                  ],
                  loadEvolveproCsv,
                )
              }
              className="flex-shrink-0"
            >
              Browse
            </Button>
            <span className="text-xs text-gray-500 truncate self-center">
              {evolveproCsvPath ? basename(evolveproCsvPath) : "No file selected"}
            </span>
          </div>

          {/* Variant count summary */}
          {evolveproTotalCount > 0 && (
            <div className="text-xs font-medium text-gray-700 bg-gray-50 rounded px-2 py-1.5">
              {mutationInputMode === "multi-evolve" ? "MULTI-evolve" : "EVOLVEpro"}:{" "}
              {evolveproTotalCount} variants loaded
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
                <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">
                  Selection mode
                </div>
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

              {pipelineMode && <DiversityOptions />}
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
            <span className="text-red-500 ml-1">({parseErrors.length} failed)</span>
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
  );
}
