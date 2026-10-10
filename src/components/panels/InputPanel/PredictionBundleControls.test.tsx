import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ open: vi.fn(), send: vi.fn(), openUrl: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mocks.open }));
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: mocks.openUrl }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: mocks.send, setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
import { useAppStore } from "@/store/appStore";
import { predictionBundleInventory } from "@/test-utils/predictionBundleFixture";
import { PredictionBundleControls } from "./PredictionBundleControls";

const initial = useAppStore.getState();
beforeEach(() => {
  vi.resetAllMocks();
  useAppStore.setState(initial, true);
  mocks.openUrl.mockResolvedValue(undefined);
});
afterEach(() => useAppStore.getState().cancelDiversityReload());

describe("saved prediction selection controls", () => {
  it("defaults to producer top rank and exposes other models only in advanced options", async () => {
    mocks.open.mockResolvedValue("/tmp/fold.zip");
    mocks.send.mockResolvedValue(predictionBundleInventory());
    render(<PredictionBundleControls />);
    expect(screen.getByRole("combobox", { name: "Structure source" })).toHaveValue("accession");
    fireEvent.change(screen.getByRole("combobox", { name: "Structure source" }), { target: { value: "prediction_bundle" } });
    expect(screen.getByText(/Reads saved results locally/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Browse prediction ZIP" }));
    const advanced = await screen.findByRole("button", { name: "Advanced: choose another model" });
    const chain = screen.getByRole("combobox", { name: "Protein chain" });
    expect(screen.queryByRole("combobox", { name: "Prediction model" })).not.toBeInTheDocument();
    expect(screen.getByText("Selected model: job_model_0.cif")).toBeInTheDocument();
    expect(chain).toHaveValue("");
    expect(chain).not.toBeDisabled();
    fireEvent.change(chain, { target: { value: JSON.stringify("B") } });
    expect(useAppStore.getState().predictionBundleChainId).toBe("B");
    fireEvent.click(advanced);
    const model = screen.getByRole("combobox", { name: "Prediction model" });
    expect(model).toHaveValue("job_model_0.cif");
    fireEvent.change(model, { target: { value: "job_model_1.cif" } });
    expect(chain).toHaveValue("");
    expect(screen.getByText("fold.zip")).toBeInTheDocument();
    expect(mocks.open).toHaveBeenCalledWith(expect.objectContaining({ multiple: false, filters: [{ name: "ZIP", extensions: ["zip"] }] }));
  });

  it("keeps prior configuration intact when the file picker is cancelled", async () => {
    useAppStore.setState({ strictStructureSource: "prediction_bundle", predictionBundlePath: "/tmp/previous.zip",
      predictionBundleInventory: predictionBundleInventory(), predictionBundleModelId: "job_model_0.cif", predictionBundleChainId: "A" });
    mocks.open.mockResolvedValue(null);
    render(<PredictionBundleControls />);
    fireEvent.click(screen.getByRole("button", { name: "Browse prediction ZIP" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Browse prediction ZIP" })).not.toBeDisabled());
    expect(mocks.send).not.toHaveBeenCalled();
    expect(useAppStore.getState().predictionBundlePath).toBe("/tmp/previous.zip");
    expect(screen.getByText("Selected model: job_model_0.cif")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Protein chain" })).toHaveValue(JSON.stringify("A"));
  });

  it.each(["missing_top_rank", "ambiguous_ranking"] as const)("shows the picker and explains %s without a hidden fallback", (reason) => {
    useAppStore.setState({ strictStructureSource: "prediction_bundle",
      predictionBundleInventory: { ...predictionBundleInventory(), recommended_model_id: null,
        recommendation_reason: reason } });
    render(<PredictionBundleControls />);
    expect(screen.getByRole("combobox", { name: "Prediction model" })).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "Protein chain" })).toBeDisabled();
    expect(screen.getByText(reason === "missing_top_rank"
      ? /top-ranked model is missing/ : /ranking is unknown or ambiguous/)).toBeInTheDocument();
  });

  it("ignores a picker response if the source changed while it was open", async () => {
    useAppStore.setState({ strictStructureSource: "prediction_bundle" });
    let finish: ((path: string) => void) | undefined;
    mocks.open.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    render(<PredictionBundleControls />);
    fireEvent.click(screen.getByRole("button", { name: "Browse prediction ZIP" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Structure source" }), { target: { value: "accession" } });
    await act(async () => finish?.("/tmp/old.zip"));
    expect(mocks.send).not.toHaveBeenCalled();
    expect(useAppStore.getState().strictStructureSource).toBe("accession");
  });

  it("offers readable output terms and opens only the reviewed link on request", async () => {
    useAppStore.setState({ strictStructureSource: "prediction_bundle", predictionBundleInventory: predictionBundleInventory() });
    render(<PredictionBundleControls />);
    expect(screen.getByText(/non-commercial use restrictions/)).toBeInTheDocument();
    expect(mocks.openUrl).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("link", { name: "AlphaFold Server output terms" }));
    expect(mocks.openUrl).toHaveBeenCalledWith(predictionBundleInventory().terms_url);
  });

  it("allows an explicitly selected blank chain ID without treating it as unselected", () => {
    const inventory = predictionBundleInventory();
    inventory.models[0].chains = [{ chain_id: "", author_chain_id: "", sequence: "MAAAA", length: 5 }];
    useAppStore.setState({ strictStructureSource: "prediction_bundle", predictionBundleInventory: inventory, predictionBundleModelId: inventory.models[0].model_id });
    render(<PredictionBundleControls />);
    fireEvent.change(screen.getByRole("combobox", { name: "Protein chain" }), { target: { value: JSON.stringify("") } });
    expect(useAppStore.getState().predictionBundleChainId).toBe("");
  });
});
