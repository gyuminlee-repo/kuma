import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ResequenceEvidencePanel } from "@/components/mame/panels/ResequenceEvidencePanel";
import { useRoundStore } from "@/store/round/roundSlice";
import i18next from "@/lib/i18n";
import { resequenceStore, useMameAppStore } from "./mameAppStore";
import fixture from "../../../src-tauri/samples/mame/sample_analysis_result.json";
import original from "../../../src-tauri/samples/mame/sample_analyze_response.json";
import repeated from "../../../src-tauri/samples/mame/sample_resequence_response.json";

vi.mock("@tauri-apps/api/path", () => ({
  resolveResource: vi.fn(async (path: string) => `/resolved/${path}`),
}));
vi.mock("@tauri-apps/plugin-fs", () => ({
  exists: vi.fn(async () => true),
  copyFile: vi.fn(async () => undefined),
  mkdir: vi.fn(async () => undefined),
  readTextFile: vi.fn(async (path: string) => {
    if (path.endsWith("sample_analyze_response.json")) return JSON.stringify(original);
    if (path.endsWith("sample_resequence_response.json")) return JSON.stringify(repeated);
    return JSON.stringify(fixture);
  }),
}));
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(async () => ({})), cancelAndRespawn: vi.fn(),
}));

beforeEach(async () => {
  for (const store of [useMameAppStore, resequenceStore]) {
    store.getState().resetInput();
    store.getState().resetAnalysis();
  }
  useRoundStore.setState({ rounds: [], active_round_id: null });
  useMameAppStore.setState({ formStoragePath: "/project" });
  await useMameAppStore.getState().loadSampleData();
});
afterEach(cleanup);

it.each(["same_clone", "measured_resequence_clone"])(
  "enables an explicit %s declaration from the loaded sample through the real evidence panel",
  (relationship) => {
    // Given the loaded runs and the operator's physical-source selections.
    const onChange = vi.fn();
    render(<ResequenceEvidencePanel value={null}
      verdictPath="/project/sample_data/mame/original/13_mame_verdict.xlsx" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(i18next.t("mame.resequence.relationship")),
      { target: { value: relationship } });
    if (relationship === "same_clone") {
      fireEvent.change(screen.getByLabelText(i18next.t("mame.resequence.originalClone")),
        { target: { value: "NB03:A1" } });
    } else {
      fireEvent.change(screen.getByLabelText(i18next.t("mame.resequence.activityWell")),
        { target: { value: "A3" } });
    }
    fireEvent.change(screen.getByLabelText(i18next.t("mame.resequence.repeatedClone")),
      { target: { value: "NB05:A1" } });
    const add = screen.getByRole("button", { name: i18next.t("mame.resequence.linkEvidence") });
    expect(add).toBeDisabled();
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(add).toBeEnabled();

    // When the operator explicitly records the link.
    fireEvent.click(add);

    // Then the panel names both run files and the chosen physical sources.
    expect(onChange).toHaveBeenCalledWith({
      original_verdict_xlsx: "/project/sample_data/mame/original/13_mame_verdict.xlsx",
      verdict_xlsx: "/project/sample_data/mame/resequence/18_mame_resequence_verdict.xlsx",
      links: [{
        relationship, mutant_id: "F28A",
        original_well: relationship === "same_clone" ? "A1" : "",
        original_plate: relationship === "same_clone" ? "NB03" : "",
        ...(relationship === "measured_resequence_clone" ? { activity_well: "A3" } : {}),
        resequence_well: "A1", resequence_plate: "NB05",
      }],
    });
  },
);
