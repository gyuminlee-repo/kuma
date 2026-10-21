import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalyzeResult, DistributionStats } from "@/types/mame/models";
import { sampleReplicates, sampleSummary, sampleVerdicts, sampleWells } from "@/lib/mame/sampleData";
import { MameRunStoreContext, resequenceStore, useMameAppStore } from "./mameAppStore";
import { useRoundStore } from "@/store/round/roundSlice";
import { InputPanel } from "@/components/mame/panels/InputPanel";
import { ProjectProvider } from "@/state/projectContext";
import { buildMameSnapshot } from "@/lib/mame/autosaveSnapshot";
import { ResequenceEvidencePanel } from "@/components/mame/panels/ResequenceEvidencePanel";
import i18next from "@/lib/i18n";

const mocks = vi.hoisted(() => ({
  request: vi.fn(), cancel: vi.fn(), write: vi.fn(), open: vi.fn(), detect: vi.fn(),
}));
vi.mock("@/lib/ipc-mame", () => ({ sendRequest: mocks.request, cancelAndRespawn: mocks.cancel }));
vi.mock("@/lib/mame/resultSnapshot", () => ({
  writeMameResultSnapshot: mocks.write, updateMameResultSelection: vi.fn(),
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mocks.open, save: vi.fn() }));
vi.mock("@/hooks/useAutosaveHydration", () => ({ applyMameAutoDetect: vi.fn() }));
vi.mock("@/lib/mame/detectProjectFiles", () => ({ detectFromInputDir: mocks.detect }));
vi.mock("@/lib/overwriteConfirm", () => ({ fileExists: vi.fn(), requestOverwriteConfirm: vi.fn() }));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));

const distribution: DistributionStats = {
  n_files: 1, file_size_kb: { min: 1, p05: 1, p25: 1, median: 1, p75: 1, p95: 1, max: 1, mean: 1, std: 0 },
  suggested_cutoff_kb: 0, suggested_method: "fixed_50", bimodal: false,
};
const result = (folder: string): AnalyzeResult => ({
  verdicts: sampleVerdicts(), replicates: sampleReplicates(),
  summary: sampleSummary(), distribution_stats: distribution, output_path: `${folder}/run.xlsx`,
});

function pending<T>() {
  let finish: (value: T) => void = () => { throw new Error("Promise not initialized"); };
  const promise = new Promise<T>((resolve) => { finish = resolve; });
  return { promise, finish };
}

beforeEach(() => {
  vi.clearAllMocks();
  for (const store of [useMameAppStore, resequenceStore]) {
    store.getState().resetInput();
    store.getState().resetAnalysis();
    store.setState({ resequenceSnapshot: null });
  }
  useRoundStore.setState({ rounds: [], active_round_id: null });
  resequenceStore.setState({
    inputDir: "/repeat/raw", expectedPath: "/repeat/expected.xlsx", referencePath: "/repeat/ref.fa",
    outputPath: "/repeat/output", projectPath: "/project", inputMode: "consensus",
  });
  mocks.request.mockImplementation(async (method: string) => {
    if (method === "analyze") return result("/repeat/output");
    if (method === "get_plate_data") return { wells: sampleWells() };
    if (method === "get_run_health") return null;
    return {};
  });
});
afterEach(cleanup);

describe("independent resequencing", () => {
  it("runs selection in its scope without touching primary inputs, results or round genotype", async () => {
    const original = result("/original");
    useMameAppStore.setState({ inputDir: "/original/raw", analyzeResult: original, verdicts: original.verdicts });
    const roundId = useRoundStore.getState().addRound({ plate_meta: { plates: [] } });
    useRoundStore.getState().updateRoundField(roundId, "genotype", { run_id: "original" });
    const genotype = useRoundStore.getState().rounds.find((r) => r.id === roundId)?.genotype;
    const primary = useMameAppStore.getState();

    await resequenceStore.getState().runAnalysis();

    expect(useMameAppStore.getState()).toBe(primary);
    expect(useRoundStore.getState().rounds.find((r) => r.id === roundId)?.genotype).toEqual(genotype);
    expect(resequenceStore.getState().replicates).toEqual(result("/repeat/output").replicates);
    expect(mocks.request).toHaveBeenCalledWith("analyze", expect.objectContaining({ run_scope: "resequence", input_dir: "/repeat/raw" }), expect.any(Number));
    expect(mocks.write).toHaveBeenCalledWith("/project", expect.objectContaining({ output_path: "/repeat/output/run.xlsx" }), expect.any(String), "resequence");
  });

  it("rejects a concurrent run before detection or analysis reaches the sidecar", async () => {
    useMameAppStore.setState({ isAnalyzing: true });
    await resequenceStore.getState().runAnalysis();
    expect(mocks.request).not.toHaveBeenCalled();
    expect(resequenceStore.getState().validationErrors).toHaveLength(1);
    expect(useMameAppStore.getState().isAnalyzing).toBe(true);
  });

  it("cancellation restores completed primary evidence and rejects a late response", async () => {
    const original = result("/original");
    useMameAppStore.setState({ analyzeResult: original, verdicts: original.verdicts });
    const analysis = pending<AnalyzeResult>();
    const entered = pending<void>();
    mocks.request.mockImplementation(async (method: string) => {
      if (method === "analyze") { entered.finish(); return analysis.promise; }
      return {};
    });
    const run = resequenceStore.getState().runAnalysis();
    await entered.promise;

    await resequenceStore.getState().cancelAnalysis();
    analysis.finish(result("/cancelled"));
    await run;

    expect(resequenceStore.getState().analyzeResult).toBeNull();
    expect(useMameAppStore.getState().analyzeResult).toBe(original);
    expect(mocks.request).toHaveBeenCalledWith("load_analyze_result", { ...original, run_scope: "primary" });
    expect(mocks.write).not.toHaveBeenCalled();
  });

  it("failure leaves primary evidence untouched", async () => {
    const original = result("/original");
    useMameAppStore.setState({ analyzeResult: original });
    mocks.request.mockRejectedValue(new Error("synthetic failure"));
    await resequenceStore.getState().runAnalysis();
    expect(resequenceStore.getState().isAnalyzing).toBe(false);
    expect(resequenceStore.getState().validationErrors).toEqual(["synthetic failure"]);
    expect(useMameAppStore.getState().analyzeResult).toBe(original);
  });

  it("replays the current export destination rather than the prior workbook", async () => {
    const original = result("/original");
    useMameAppStore.setState({ analyzeResult: original });
    resequenceStore.setState({ analyzeResult: result("/repeat") });
    mocks.request.mockImplementation(async (method: string) => {
      if (method === "export_excel") return { output_path: "/repeat/new.xlsx" };
      if (method === "get_plate_data") return { wells: [] };
      return {};
    });
    await resequenceStore.getState().exportExcel("/repeat/new.xlsx");
    await resequenceStore.getState().loadPlateData();
    expect(mocks.request).toHaveBeenLastCalledWith("get_plate_data", expect.objectContaining({
      run_scope: "resequence",
      result_snapshot: expect.objectContaining({ output_path: "/repeat/new.xlsx" }),
    }));
    expect(useMameAppStore.getState().analyzeResult).toBe(original);
  });

  it("persists separate inputs and lossless selected replicate evidence", () => {
    const original = result("/original");
    const repeat = result("/repeat");
    useMameAppStore.setState({ inputDir: "/original/raw", analyzeResult: original });
    resequenceStore.setState({ analyzeResult: repeat, replicates: repeat.replicates });
    useMameAppStore.setState({ resequenceSnapshot: buildMameSnapshot(resequenceStore.getState()) });
    const saved = JSON.parse(JSON.stringify(buildMameSnapshot(useMameAppStore.getState())));
    expect(saved.input.input_dir).toBe("/original/raw");
    expect(saved.resequence.input.input_dir).toBe("/repeat/raw");
    expect(saved.resequence.run_result.replicates).toEqual(repeat.replicates);
    expect(saved.resequence.run_scope).toBe("resequence");
  });

  it("nested run-folder browse and asynchronous autofill write only the scoped store", async () => {
    useMameAppStore.setState({ inputDir: "/original/raw", referencePath: "/original/ref.fa" });
    resequenceStore.setState({ inputMode: "raw_run", inputDir: "", referencePath: "" });
    const detected = pending<{ referencePath: string; expectedPath: string; legacySampleMapPath: string; customBarcodesPath: string; sequencingSummaryPath: string }>();
    const entered = pending<void>();
    mocks.open.mockResolvedValue("/new/repeat");
    mocks.detect.mockImplementation(() => { entered.finish(); return detected.promise; });
    render(<ProjectProvider value={{ path: "/project", name: "P", scratch: false }}>
      <MameRunStoreContext.Provider value={resequenceStore}><InputPanel /></MameRunStoreContext.Provider>
    </ProjectProvider>);
    const browse = screen.getAllByRole("button").find((button) => /MinKNOW|run folder/i.test(button.getAttribute("aria-label") ?? ""));
    expect(browse).toBeDefined();
    if (!browse) throw new Error("Missing browse control");
    await act(async () => { fireEvent.click(browse); await entered.promise; });
    await act(async () => {
      detected.finish({ referencePath: "/new/ref.fa", expectedPath: "", legacySampleMapPath: "", customBarcodesPath: "", sequencingSummaryPath: "" });
      await detected.promise;
    });
    expect(resequenceStore.getState().inputDir).toBe("/new/repeat");
    expect(resequenceStore.getState().referencePath).toBe("/new/ref.fa");
    expect(useMameAppStore.getState().inputDir).toBe("/original/raw");
    expect(useMameAppStore.getState().referencePath).toBe("/original/ref.fa");
  });

  it("requires explicit final activity well and source confirmation for a different clone", () => {
    const onChange = vi.fn();
    const base = sampleWells()[0];
    useMameAppStore.setState({ analyzeResult: result("/original"), wells: [
      { ...base, well: "A1", native_barcode: "NB01", mutant_id: "G2A", verdict: "WRONG_AA" },
    ] });
    resequenceStore.setState({ analyzeResult: result("/repeat"), wells: [
      { ...base, well: "C1", native_barcode: "NB02", mutant_id: "G2A", verdict: "PASS", selected: true },
    ] });
    render(<ResequenceEvidencePanel value={null} verdictPath="/original/run.xlsx" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(i18next.t("mame.resequence.relationship")), { target: { value: "measured_resequence_clone" } });
    fireEvent.change(screen.getByLabelText(i18next.t("mame.resequence.repeatedClone")), { target: { value: "NB02:C1" } });
    const add = screen.getByRole("button", { name: i18next.t("mame.resequence.linkEvidence") });
    expect(add).toBeDisabled();
    fireEvent.change(screen.getByLabelText(i18next.t("mame.resequence.activityWell")), { target: { value: "D1" } });
    expect(add).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(add);
    expect(onChange).toHaveBeenCalledWith({
      original_verdict_xlsx: "/original/run.xlsx", verdict_xlsx: "/repeat/run.xlsx",
      links: [{
        relationship: "measured_resequence_clone", mutant_id: "G2A",
        original_well: "", original_plate: "", activity_well: "D1",
        resequence_well: "C1", resequence_plate: "NB02",
      }],
    });
    expect(useMameAppStore.getState().wells[0].verdict).toBe("WRONG_AA");
  });
});
