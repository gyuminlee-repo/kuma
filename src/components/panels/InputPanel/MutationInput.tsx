import { useEffect, useMemo, useRef } from "react";
import { useAppStore } from "../../../store/appStore";
import { basename } from "../../../lib/utils";
import { browseFile } from "../../../lib/file-utils";
import { Button } from "../../ui/button";
import { DiversityOptions } from "./DiversityOptions";

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
      <label className="text-xs font-medium text-foreground">Mutations</label>
      <div className="flex gap-2 text-xs" role="radiogroup" aria-label="Mutation input source">
        <label className="flex items-center gap-1 rounded-full border border-border bg-card px-2 py-1 text-muted-foreground">
          <input
            type="radio"
            name="mutInput"
            checked={mutationInputMode === "text"}
            onChange={() => setMutationInputMode("text")}
            className="w-3 h-3"
          />
          Text
        </label>
        <label className="flex items-center gap-1 rounded-full border border-border bg-card px-2 py-1 text-muted-foreground">
          <input
            type="radio"
            name="mutInput"
            checked={mutationInputMode === "evolvepro"}
            onChange={() => setMutationInputMode("evolvepro")}
            className="w-3 h-3"
          />
          EVOLVEpro
        </label>
        <label className="flex items-center gap-1 rounded-full border border-border bg-card px-2 py-1 text-muted-foreground">
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
          className="h-32 w-full resize-none rounded-2xl border border-border bg-card p-3 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring"
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
            <span className="self-center truncate text-xs text-muted-foreground">
              {evolveproCsvPath ? basename(evolveproCsvPath) : "No file selected"}
            </span>
          </div>

          {/* Variant count summary */}
          {evolveproTotalCount > 0 && (
            <div className="rounded-xl border border-border bg-muted px-3 py-2 text-xs font-medium text-foreground">
              {mutationInputMode === "multi-evolve" ? "MULTI-evolve" : "EVOLVEpro"}:{" "}
              {evolveproTotalCount} variants loaded
            </div>
          )}

          {/* Selection mode / Pipeline UI — only for evolvepro (multi-evolve uses all combinations) */}
          {mutationInputMode === "multi-evolve" ? (
            <div className="rounded-md border border-border bg-muted px-3 py-2 text-xs text-muted-foreground">
              MULTI-evolve: all combinations selected (no filtering)
            </div>
          ) : (
            <>
              <div className="space-y-1">
                <div className="text-caption font-semibold uppercase tracking-wide text-muted-foreground">
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
                    <span className="text-foreground">Top-N only</span>
                    <span className="text-caption text-muted-foreground">(y_pred descending)</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer text-xs">
                    <input
                      type="radio"
                      name="selectionMode"
                      className="w-3 h-3"
                      checked={pipelineMode}
                      onChange={() => setPipelineMode(true)}
                    />
                    <span className="text-foreground">Pipeline</span>
                    <span className="text-caption text-muted-foreground">(step-by-step filtering)</span>
                  </label>
                </div>
              </div>

              {pipelineMode && <DiversityOptions />}
            </>
          )}

          {/* Editable variant textarea */}
          {mutationText && (
            <textarea
              className="h-32 w-full resize-none rounded-2xl border border-border bg-muted p-3 font-mono text-xs"
              value={mutationText}
              onChange={(e) => setMutationText(e.target.value)}
              title="Top-N variants by y_pred (editable)"
            />
          )}
        </div>
      )}

      {mutationText.trim() && (
        <div className="text-xs text-muted-foreground">
          {mutationCount} mutations entered
          {parsedMutations.length > 0 && (
            <span className="ml-1 text-emerald-600">
              ({parsedMutations.length} validated)
            </span>
          )}
          {parseErrors.length > 0 && (
            <span className="text-destructive ml-1">({parseErrors.length} failed)</span>
          )}
        </div>
      )}
      {parseErrors.length > 0 && (
        <div className="max-h-16 space-y-0.5 overflow-auto rounded-md bg-destructive/10 px-2 py-1 text-caption text-destructive">
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
