import { webcrypto } from "node:crypto";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ send: vi.fn(), open: vi.fn() }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mocks.open }));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: mocks.send, setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));
import { useAppStore } from "@/store/appStore";
import { OptionalDomainAnnotationPanel } from "./OptionalDomainAnnotationPanel";
import { colabFoldDomainInventory, domainReferenceFixture, domainResultFixture, domainRuntimeFixture } from "@/test-utils/domainAnnotationFixture";
import { domainAnnotationContextKey } from "@/lib/domainAnnotation";
const initial = useAppStore.getState();
beforeEach(() => { vi.stubGlobal("crypto", webcrypto);
  vi.resetAllMocks(); useAppStore.setState(initial, true);
  useAppStore.setState({ strictStructureSource: "prediction_bundle", predictionBundlePath: "/tmp/saved.zip",
    predictionBundleInventory: colabFoldDomainInventory(), predictionBundleModelId: "job_model_0.cif", predictionBundleChainId: "A",
    seqInfo: domainReferenceFixture, selectedGene: "1", evolveproSelectedVariants: ["A2V", "A2G", "A4G"] });
});
afterEach(() => { vi.unstubAllGlobals(); cleanup(); useAppStore.setState(initial, true); });
function expand() { fireEvent.click(screen.getByRole("button", { name: "Optional structural domains" })); }
const blocked = () => domainRuntimeFixture({ state: "licensing_blocked", version: null, install_available: false, available_version: null });

describe("optional domain controls", () => {
  it("is opt-in and never implies a usable runtime with an empty catalog", async () => {
    mocks.send.mockResolvedValue(blocked()); render(<OptionalDomainAnnotationPanel />);
    expect(mocks.send).not.toHaveBeenCalled(); expand();
    await screen.findByText("Module package unavailable: distribution review pending");
    expect(screen.getByRole("button", { name: "Install approved module archive" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run optional domain analysis" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Import domain result JSON" })).not.toBeDisabled();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(/No installable module package is available/)).toBeInTheDocument();
    expect(mocks.send).toHaveBeenCalledOnce();
  });
  it("explains unsupported AF3 and disables both scientific input actions", () => {
    useAppStore.setState({ predictionBundleInventory: { ...colabFoldDomainInventory(), format: "af3_server" }, domainRuntimeStatus: domainRuntimeFixture() });
    render(<OptionalDomainAnnotationPanel />); expand();
    expect(screen.getByText(/AF3 structures can be viewed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run optional domain analysis" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Import domain result JSON" })).toBeDisabled();
  });
  it("renders discontinuous domains, unassigned residues and variant/site counts without selection changes", () => {
    useAppStore.setState({ domainRuntimeStatus: blocked(), domainAnnotationResult: domainResultFixture(),
      domainAnnotationContext: domainAnnotationContextKey(useAppStore.getState()) });
    const variants = useAppStore.getState().evolveproSelectedVariants;
    render(<OptionalDomainAnnotationPanel />); expand();
    expect(screen.getByText("Assigned residues: 3 / 5 (60% coverage).")).toBeInTheDocument();
    expect(screen.getByText("1–2, 4")).toBeInTheDocument(); expect(screen.getByText("3, 5")).toBeInTheDocument();
    expect(screen.getByText("3 (100%)")).toBeInTheDocument();
    expect(screen.getByText(/external producer and execution are self-declared, not authenticated/)).toBeInTheDocument();
    expect(useAppStore.getState().evolveproSelectedVariants).toBe(variants);
  });
  it("does not clear a valid annotation when the JSON picker is cancelled", async () => {
    useAppStore.setState({ domainRuntimeStatus: blocked(), domainAnnotationResult: domainResultFixture(),
      domainAnnotationContext: domainAnnotationContextKey(useAppStore.getState()) });
    mocks.open.mockResolvedValue(null); render(<OptionalDomainAnnotationPanel />); expand();
    fireEvent.click(screen.getByRole("button", { name: "Import domain result JSON" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Import domain result JSON" })).not.toBeDisabled());
    expect(mocks.send).not.toHaveBeenCalled(); expect(useAppStore.getState().domainAnnotationResult).not.toBeNull();
  });
  it("ignores a file picker result after the chain changes", async () => {
    useAppStore.setState({ domainRuntimeStatus: blocked() });
    let finish!: (file: string) => void;
    mocks.open.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    render(<OptionalDomainAnnotationPanel />); expand(); fireEvent.click(screen.getByRole("button", { name: "Import domain result JSON" }));
    act(() => useAppStore.getState().setPredictionBundleChainId("B"));
    await act(async () => finish("/tmp/old.json"));
    expect(mocks.send).not.toHaveBeenCalled(); expect(useAppStore.getState().domainAnnotationResult).toBeNull();
  });
  it("invalidates a picker even if the reference changes away and back in one render batch", async () => {
    useAppStore.setState({ domainRuntimeStatus: blocked() });
    let finish!: (file: string) => void;
    mocks.open.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    render(<OptionalDomainAnnotationPanel />); expand(); fireEvent.click(screen.getByRole("button", { name: "Import domain result JSON" }));
    act(() => { useAppStore.setState({ fastaPath: "/tmp/other.fasta" }); useAppStore.setState({ fastaPath: "" }); });
    await act(async () => finish("/tmp/old.json"));
    expect(mocks.send).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Import domain result JSON" })).not.toBeDisabled();
  });
  it("imports a bounded JSON result through the backend, with clear/reset available", async () => {
    useAppStore.setState({ domainRuntimeStatus: blocked() }); mocks.open.mockResolvedValue("/tmp/domain.json"); mocks.send.mockResolvedValue(domainResultFixture());
    render(<OptionalDomainAnnotationPanel />); expand(); fireEvent.click(screen.getByRole("button", { name: "Import domain result JSON" }));
    await screen.findByText("Assigned residues: 3 / 5 (60% coverage).");
    expect(mocks.send).toHaveBeenCalledWith("import_domain_annotation_file", expect.objectContaining({ filepath: "/tmp/domain.json", ref_seq: "MAAAA" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear domain annotation" }));
    expect(screen.queryByText("Assigned residues: 3 / 5 (60% coverage).")).not.toBeInTheDocument();
  });
});
