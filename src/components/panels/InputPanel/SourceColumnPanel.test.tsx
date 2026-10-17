/**
 * SourceColumnPanel.test.tsx, Step 2 manual column mapping.
 *
 * Locks the behaviour that a file selection alone (no "Preview" click) makes the
 * column dropdowns usable, that auto-detect failure keeps them usable, that the
 * options come only from the preview headers, and that a failing preview RPC is
 * surfaced to the user.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mocks = vi.hoisted(() => ({
  sendRequest: vi.fn(),
}));

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: mocks.sendRequest,
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));

import { SourceColumnPanel } from "./SourceColumnPanel";
import { useAppStore } from "@/store/appStore";

const PREVIEW = {
  headers: ["Variant", "fitness", "notes"],
  rows: [["A1V", "1.2", "x"]],
  sheets: ["Sheet1"],
};

// Radix Select relies on pointer-capture / scrollIntoView APIs jsdom lacks.
// Patched here (not in test-setup) so the shared baseline is untouched.
const proto = Element.prototype as unknown as Record<string, unknown>;
const saved: Record<string, unknown> = {};
function installSelectShims() {
  for (const name of ["hasPointerCapture", "setPointerCapture", "releasePointerCapture", "scrollIntoView"]) {
    saved[name] = proto[name];
    proto[name] = function () {};
  }
}
function removeSelectShims() {
  for (const [name, value] of Object.entries(saved)) {
    if (value === undefined) delete proto[name];
    else proto[name] = value;
  }
}

// Captured before any test swaps it for a spy, so the stale-override tests can
// drive the real slice and read the request it sends.
const realLoadEvolveproCsv = useAppStore.getState().loadEvolveproCsv;

function loadParams(): Record<string, unknown>[] {
  return mocks.sendRequest.mock.calls
    .filter((c) => c[0] === "load_evolvepro_csv")
    .map((c) => c[1] as Record<string, unknown>);
}

const LOAD_RESULT = {
  variants: ["A10G"],
  y_preds: [0.9],
  total_count: 1,
  selected_count: 1,
  used_variant_column: "Variant",
  used_score_column: "fitness",
};

function resetStore(path: string) {
  useAppStore.setState({
    evolveproCsvPath: path,
    evolveproPreview: null,
    evolveproVariantColumn: null,
    evolveproScoreColumn: null,
    evolveproSheetName: null,
    evolveproUsedVariantColumn: null,
    evolveproUsedScoreColumn: null,
  });
}

describe("SourceColumnPanel, manual column mapping", () => {
  beforeEach(() => {
    installSelectShims();
    mocks.sendRequest.mockReset();
  });

  afterEach(() => {
    removeSelectShims();
  });

  it("auto-previews on file selection so the column dropdowns become enabled", async () => {
    mocks.sendRequest.mockResolvedValue(PREVIEW);
    resetStore("/tmp/variants.csv");

    render(<SourceColumnPanel />);

    await waitFor(() => {
      expect(mocks.sendRequest).toHaveBeenCalledWith(
        "preview_evolvepro_source",
        expect.objectContaining({ filepath: "/tmp/variants.csv" }),
      );
    });

    const variantTrigger = await screen.findByLabelText("Mutation column");
    const scoreTrigger = screen.getByLabelText("Ranking column");
    await waitFor(() => {
      expect(variantTrigger).not.toBeDisabled();
      expect(scoreTrigger).not.toBeDisabled();
    });
  });

  it("keeps the dropdowns usable after auto-detect failed, and Apply sends the picked column", async () => {
    mocks.sendRequest.mockResolvedValue(PREVIEW);
    const loadEvolveproCsv = vi.fn().mockResolvedValue(undefined);
    resetStore("/tmp/variants.csv");
    // Auto-detect failure state: the load reset the counters and left a message.
    useAppStore.setState({
      loadEvolveproCsv,
      evolveproTotalCount: 0,
      statusMessage: "EVOLVEpro file load failed: no variant column",
    });

    render(<SourceColumnPanel />);

    const variantTrigger = await screen.findByLabelText("Mutation column");
    await waitFor(() => expect(variantTrigger).not.toBeDisabled());

    const user = userEvent.setup();
    await user.click(variantTrigger);
    await user.click(await screen.findByRole("option", { name: "Variant" }));

    expect(useAppStore.getState().evolveproVariantColumn).toBe("Variant");

    await user.click(screen.getByRole("button", { name: "Apply selected columns" }));
    await waitFor(() => expect(loadEvolveproCsv).toHaveBeenCalledWith("/tmp/variants.csv"));
  });

  it("offers only the preview headers as column options", async () => {
    mocks.sendRequest.mockResolvedValue(PREVIEW);
    resetStore("/tmp/variants.csv");

    render(<SourceColumnPanel />);

    const variantTrigger = await screen.findByLabelText("Mutation column");
    await waitFor(() => expect(variantTrigger).not.toBeDisabled());

    const user = userEvent.setup();
    await user.click(variantTrigger);

    const listbox = await screen.findByRole("listbox");
    const labels = within(listbox)
      .getAllByRole("option")
      .map((o) => o.textContent);
    // "Auto-detect" is the explicit delegate-to-backend entry; everything else
    // must come from the preview headers, so no free-form column name is possible.
    expect(labels).toEqual(["Auto-detect", "Variant", "fitness", "notes"]);
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("reports a failing preview RPC to the user", async () => {
    mocks.sendRequest.mockRejectedValue(new Error("sidecar unavailable"));
    resetStore("/tmp/variants.csv");

    render(<SourceColumnPanel />);

    expect(
      await screen.findByText("Preview failed: sidecar unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Mutation column")).toBeDisabled();
  });
});

describe("SourceColumnPanel, the request carries what the dropdowns show", () => {
  beforeEach(() => {
    installSelectShims();
    mocks.sendRequest.mockReset();
    useAppStore.setState({ loadEvolveproCsv: realLoadEvolveproCsv });
  });

  afterEach(() => {
    removeSelectShims();
  });

  it("drops overrides the previewed file lacks before Apply sends the request", async () => {
    mocks.sendRequest.mockImplementation(async (method: string) =>
      method === "preview_evolvepro_source" ? PREVIEW : LOAD_RESULT,
    );
    resetStore("/tmp/variants.csv");
    // Left over from a file with other headers (restored project, edited file).
    useAppStore.setState({
      evolveproVariantColumn: "old_variant",
      evolveproScoreColumn: "old_score",
    });

    render(<SourceColumnPanel />);

    const variantTrigger = await screen.findByLabelText("Mutation column");
    const scoreTrigger = screen.getByLabelText("Ranking column");
    await waitFor(() => expect(variantTrigger).not.toBeDisabled());
    // Neither name is among the headers, so both dropdowns read as auto.
    expect(variantTrigger).toHaveTextContent("Auto-detect");
    expect(scoreTrigger).toHaveTextContent("Auto-detect");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Apply selected columns" }));

    await waitFor(() => expect(loadParams()).toHaveLength(1));
    expect(loadParams()[0]).not.toHaveProperty("variant_column");
    expect(loadParams()[0]).not.toHaveProperty("score_column");
    expect(useAppStore.getState().evolveproVariantColumn).toBeNull();
    expect(useAppStore.getState().evolveproScoreColumn).toBeNull();
  });

  it("still sends an override that the previewed file has", async () => {
    mocks.sendRequest.mockImplementation(async (method: string) =>
      method === "preview_evolvepro_source" ? PREVIEW : LOAD_RESULT,
    );
    resetStore("/tmp/variants.csv");
    useAppStore.setState({
      evolveproVariantColumn: "Variant",
      evolveproScoreColumn: "old_score",
    });

    render(<SourceColumnPanel />);

    const variantTrigger = await screen.findByLabelText("Mutation column");
    await waitFor(() => expect(variantTrigger).not.toBeDisabled());
    expect(variantTrigger).toHaveTextContent("Variant");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Apply selected columns" }));

    await waitFor(() => expect(loadParams()).toHaveLength(1));
    expect(loadParams()[0].variant_column).toBe("Variant");
    expect(loadParams()[0]).not.toHaveProperty("score_column");
  });

  it("keeps restored overrides while the preview has not arrived", async () => {
    // The preview never resolves: the panel has no headers to compare against.
    mocks.sendRequest.mockImplementation((method: string) =>
      method === "preview_evolvepro_source"
        ? new Promise(() => {})
        : Promise.resolve(LOAD_RESULT),
    );
    resetStore("/tmp/variants.csv");
    useAppStore.setState({
      evolveproVariantColumn: "mutation_id",
      evolveproScoreColumn: "ranking_score",
    });

    render(<SourceColumnPanel />);

    await waitFor(() =>
      expect(mocks.sendRequest).toHaveBeenCalledWith(
        "preview_evolvepro_source",
        expect.anything(),
      ),
    );
    expect(useAppStore.getState().evolveproVariantColumn).toBe("mutation_id");
    expect(useAppStore.getState().evolveproScoreColumn).toBe("ranking_score");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Apply selected columns" }));

    await waitFor(() => expect(loadParams()).toHaveLength(1));
    expect(loadParams()[0].variant_column).toBe("mutation_id");
    expect(loadParams()[0].score_column).toBe("ranking_score");
    expect(useAppStore.getState().evolveproVariantColumn).toBe("mutation_id");
    expect(useAppStore.getState().evolveproScoreColumn).toBe("ranking_score");
  });
});
