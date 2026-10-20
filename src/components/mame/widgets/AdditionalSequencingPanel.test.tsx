/**
 * Step 2.3, manual plate-copy confirmation.
 *
 * What is pinned is behaviour a wrong wiring would break: which wells are
 * offered, that the RPC always carries the FULL override list (the sidecar
 * recomputes from it, so a partial list silently undoes the others), that an
 * override is not an analyze input (the run outputs survive it), and that what
 * the sidecar reports as dropped reaches the screen and leaves the store.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sendRequest = vi.fn();
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: (...args: unknown[]) => sendRequest(...args),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

const updateResultFile = vi.fn();
vi.mock("@/lib/mame/resultSnapshot", () => ({
  updateMameResultSelection: (...args: unknown[]) => updateResultFile(...args),
}));

import {
  needsConfirmation,
  overridesFromReplicates,
} from "@/lib/mame/selectionOverrides";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type {
  AnalyzeSummary,
  ApplySelectionOverridesResult,
  ReplicateResult,
  VerdictClass,
  VerdictRecord,
} from "@/types/mame/models";
import { AdditionalSequencingPanel } from "./AdditionalSequencingPanel";

function verdictRecord(nb: string, verdict: VerdictClass): VerdictRecord {
  return { native_barcode: nb, custom_barcode: "1_1", verdict } as unknown as VerdictRecord;
}

function replicate(
  mutant: string,
  copies: Record<string, VerdictClass>,
  selected: string | null,
  extra: Partial<ReplicateResult> = {},
): ReplicateResult {
  return {
    mutant_id: mutant,
    selected_plate: selected,
    selection_reason: "auto",
    failed: selected === null,
    plate_keys: Object.keys(copies),
    plate_verdicts: Object.fromEntries(
      Object.entries(copies).map(([nb, v]) => [nb, verdictRecord(nb, v)]),
    ),
    is_fallback: false,
    fallback_reason: null,
    ...extra,
  };
}

const MANUAL = {
  note: "Sanger OK",
  auto_selected_plate: "NB07",
  auto_verdict: "LOWDEPTH",
  auto_failed: false,
  auto_is_fallback: false,
  auto_selection_reason: "auto",
  auto_fallback_reason: null,
};

const OK = replicate("A1MUT", { NB07: "PASS" }, "NB07");
const SHALLOW = replicate("B1MUT", { NB07: "LOWDEPTH", NB08: "PASS" }, "NB07");
const CONFIRMED = replicate("B1MUT", { NB07: "LOWDEPTH", NB08: "PASS" }, "NB08", {
  manual: MANUAL,
});

function reply(
  patch: Partial<ApplySelectionOverridesResult>,
): ApplySelectionOverridesResult {
  return {
    applied: [],
    dropped: [],
    replicates: [],
    picks_autosave: null,
    workbook_autosave: { status: "saved", output_path: null, error: null },
    ...patch,
  };
}

function mockRpc(result: ApplySelectionOverridesResult) {
  sendRequest.mockImplementation(async (method: string) =>
    method === "apply_selection_overrides" ? result : { wells: [] },
  );
}

function overrideCalls(): { overrides: unknown }[] {
  return sendRequest.mock.calls
    .filter(([method]) => method === "apply_selection_overrides")
    .map(([, params]) => params as { overrides: unknown });
}

describe("overridesFromReplicates / needsConfirmation", () => {
  it("reads the overrides off the replicates and settles a confirmed well", () => {
    expect(overridesFromReplicates([OK, CONFIRMED])).toEqual([
      { mutant_id: "B1MUT", plate: "NB08", note: "Sanger OK" },
    ]);
    expect([OK, SHALLOW, CONFIRMED].map(needsConfirmation)).toEqual([false, true, false]);
  });

  it("flags a fallback pick and a well with no copy even when the verdict reads PASS", () => {
    const fallback = replicate("F", { NB07: "PASS" }, "NB07", { is_fallback: true });
    expect(needsConfirmation(fallback)).toBe(true);
    expect(needsConfirmation(replicate("N", { NB07: "NO_CALL" }, null))).toBe(true);
  });
});

describe("AdditionalSequencingPanel", () => {
  beforeEach(() => {
    sendRequest.mockReset();
    updateResultFile.mockReset();
    useMameAppStore.setState({
      projectPath: "/proj",
      selectionOverrideWorkbookError: null,
      selectionOverrideResultFileError: null,
      verdicts: [verdictRecord("NB07", "PASS")],
      replicates: [OK, SHALLOW],
      summary: { total: 1 } as unknown as AnalyzeSummary,
      wells: [],
      selectionOverrideNotice: null,
      selectionOverrideError: null,
      isApplyingSelectionOverride: false,
    });
  });

  it("offers only the wells without a usable selected copy", () => {
    render(<AdditionalSequencingPanel />);

    const section = screen.getByRole("region");
    expect(section).toHaveTextContent("B1MUT");
    expect(screen.getAllByRole("button", { name: "Choose copy" })).toHaveLength(1);
    expect(section.textContent).not.toContain("{{");
  });

  it("sends the full override list for the copy and note the user chose", async () => {
    mockRpc(reply({ replicates: [OK, CONFIRMED] }));
    render(<AdditionalSequencingPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Choose copy" }));
    fireEvent.click(screen.getByRole("radio", { name: /NB08/ }));
    fireEvent.change(screen.getByLabelText("Confirmation note"), {
      target: { value: "Sanger OK" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm copy" }));

    await waitFor(() => expect(screen.getByText("Manually confirmed")).toBeInTheDocument());
    expect(overrideCalls()[0].overrides).toEqual([
      { mutant_id: "B1MUT", plate: "NB08", note: "Sanger OK" },
    ]);
    expect(screen.getByText("Sanger OK")).toBeInTheDocument();
    expect(screen.getByText(/LOWDEPTH/)).toBeInTheDocument();
    expect(useMameAppStore.getState().summary).not.toBeNull();
    expect(useMameAppStore.getState().verdicts).toHaveLength(1);
  });

  it("writes the confirmed selection back to the result file so a restore keeps it", async () => {
    mockRpc(reply({ replicates: [OK, CONFIRMED] }));

    await useMameAppStore.getState().applySelectionOverride("B1MUT", "NB08", "Sanger OK");

    expect(updateResultFile).toHaveBeenCalledWith("/proj", [OK, CONFIRMED], null);
  });

  it("says so when the result workbook could not be rewritten, and keeps the confirmation", async () => {
    mockRpc(
      reply({
        replicates: [OK, CONFIRMED],
        workbook_autosave: { status: "failed", output_path: "/x.xlsx", error: "file is open" },
      }),
    );

    await useMameAppStore.getState().applySelectionOverride("B1MUT", "NB08", "Sanger OK");
    render(<AdditionalSequencingPanel />);

    expect(screen.getByRole("alert")).toHaveTextContent("file is open");
    expect(overridesFromReplicates(useMameAppStore.getState().replicates)).toHaveLength(1);
  });

  it("undo sends an empty list and restores the automatic pick", async () => {
    useMameAppStore.setState({ replicates: [OK, CONFIRMED] });
    mockRpc(reply({ replicates: [OK, SHALLOW] }));
    render(<AdditionalSequencingPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));

    await waitFor(() =>
      expect(useMameAppStore.getState().replicates[1].manual).toBeUndefined(),
    );
    expect(overrideCalls()[0].overrides).toEqual([]);
  });

  it("reports an entry the sidecar dropped and leaves it out of the store", async () => {
    useMameAppStore.setState({ replicates: [OK, CONFIRMED] });
    mockRpc(
      reply({
        replicates: [OK, SHALLOW],
        dropped: [
          { mutant_id: "B1MUT", plate: "NB08", note: "", reason: "unknown_copy" },
        ],
      }),
    );

    await useMameAppStore.getState().reapplySelectionOverrides();
    render(<AdditionalSequencingPanel />);

    expect(screen.getByRole("alert")).toHaveTextContent("B1MUT");
    expect(overridesFromReplicates(useMameAppStore.getState().replicates)).toEqual([]);
  });

  it("restores nothing and calls nothing when no override is in force", async () => {
    await useMameAppStore.getState().reapplySelectionOverrides();

    expect(overrideCalls()).toEqual([]);
  });

  it("says the result file was not updated, not that the apply failed, when only that write throws", async () => {
    mockRpc(reply({ replicates: [OK, CONFIRMED] }));
    updateResultFile.mockRejectedValue(new Error("disk full"));

    await useMameAppStore.getState().applySelectionOverride("B1MUT", "NB08", "Sanger OK");
    render(<AdditionalSequencingPanel />);

    const state = useMameAppStore.getState();
    expect(state.selectionOverrideError).toBeNull();
    expect(state.selectionOverrideResultFileError).toBe("disk full");
    expect(overridesFromReplicates(state.replicates)).toHaveLength(1);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("disk full");
    expect(alert).not.toHaveTextContent("Could not apply");
  });

  it("refreshes run health after an apply and after an undo", async () => {
    const healthCalls = () =>
      sendRequest.mock.calls.filter(([method]) => method === "get_run_health").length;
    mockRpc(reply({ replicates: [OK, CONFIRMED] }));

    await useMameAppStore.getState().applySelectionOverride("B1MUT", "NB08", "Sanger OK");
    expect(healthCalls()).toBe(1);

    mockRpc(reply({ replicates: [OK, SHALLOW] }));
    await useMameAppStore.getState().undoSelectionOverride("B1MUT");
    expect(healthCalls()).toBe(2);
  });

  it("discards a response that arrives after the results it was computed for were replaced", async () => {
    let release: (value: ApplySelectionOverridesResult) => void = () => undefined;
    const pending = new Promise<ApplySelectionOverridesResult>((resolve) => {
      release = resolve;
    });
    sendRequest.mockImplementation(async (method: string) =>
      method === "apply_selection_overrides" ? pending : { wells: [] },
    );

    const inFlight = useMameAppStore
      .getState()
      .applySelectionOverride("B1MUT", "NB08", "Sanger OK");
    // A new analyze run replaces the verdicts array while the call is pending.
    useMameAppStore.setState({
      verdicts: [verdictRecord("NB09", "PASS")],
      replicates: [OK],
    });
    release(reply({ replicates: [OK, CONFIRMED] }));
    await inFlight;

    const state = useMameAppStore.getState();
    expect(state.replicates).toEqual([OK]);
    expect(updateResultFile).not.toHaveBeenCalled();
    expect(state.selectionOverrideError).toBeNull();
    expect(state.selectionOverrideNotice).toBeNull();
  });

  it("drops the confirmations together with the results they describe", () => {
    useMameAppStore.setState({
      replicates: [OK, CONFIRMED],
      selectionOverrideNotice: [
        { mutant_id: "B1MUT", plate: "NB08", note: "", reason: "unknown_copy" },
      ],
    });

    useMameAppStore.getState().clearResults();

    const state = useMameAppStore.getState();
    expect(overridesFromReplicates(state.replicates)).toEqual([]);
    expect(state.selectionOverrideNotice).toBeNull();
  });
});
