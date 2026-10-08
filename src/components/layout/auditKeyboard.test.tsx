import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AppLayout } from "@/components/layout/AppLayout";
import { useAppStore } from "@/store/appStore";
import { checkKuroInputSize } from "@/lib/inputThresholds";
import { ProjectProvider } from "@/state/projectContext";
import i18next from "i18next";

const autosaveMocks = vi.hoisted(() => ({
  flushAutosave: vi.fn(async () => {}),
}));

vi.mock("@/lib/autosave", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/autosave")>();
  return { ...actual, flushAutosave: autosaveMocks.flushAutosave };
});

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(async (method: string) => {
    if (method === "health_info") throw new Error("No sidecar in component audit");
    return undefined;
  }),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(async () => {}),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

vi.mock("@/hooks/useSidecar", () => ({
  useSidecar: () => ({ status: "ready", retry: vi.fn() }),
}));

const initialState = useAppStore.getState();

beforeEach(() => {
  autosaveMocks.flushAutosave.mockClear();
  localStorage.clear();
  useAppStore.setState({
    seqInfo: {
      header: "audit",
      seq_length: 99,
      genes: [{ gene: "gene1", product: "", cds_start: 0, cds_end: 99, aa_length: 33 }],
    },
    mutationText: Array.from({ length: 1000 }, () => "M1A").join("\n"),
    selectedGene: "",
    isDesigning: false,
    mutationInputMode: "text",
    currentMajor: "design",
    currentSubStep: "design.submit",
    evolveproTotalCount: 0,
    loadSettings: vi.fn(async () => {}),
    loadPolymerases: vi.fn(async () => {}),
    loadNetworkConsentSettings: vi.fn(),
    designPrimers: vi.fn(async () => {}),
  });
});

afterEach(() => {
  cleanup();
  useAppStore.setState(initialState, true);
  localStorage.clear();
});

it("shows the size warning when Run Design is clicked", async () => {
  // Given
  render(<AppLayout />);
  const message = checkKuroInputSize({ rowCount: 1000 }).message;
  // When
  await act(async () => {
    const region = screen.getByRole("region", { name: /^run design$/i });
    fireEvent.click(within(region).getByRole("button", { name: /^run design$/i }));
  });
  // Then
  expect(screen.getByText(message)).toBeInTheDocument();
  expect(useAppStore.getState().designPrimers).not.toHaveBeenCalled();
});

it("shows the same size warning for Ctrl+Enter", async () => {
  // Given
  render(<AppLayout />);
  const message = checkKuroInputSize({ rowCount: 1000 }).message;
  // When
  await act(async () => {
    fireEvent.keyDown(document.body, { key: "Enter", ctrlKey: true });
  });
  // Then
  expect(useAppStore.getState().currentSubStep).toBe("design.submit");
  expect(useAppStore.getState().designPrimers).not.toHaveBeenCalled();
  expect(screen.queryByText(message)).toBeInTheDocument();
});

it("saves the new project after the provider changes without remounting", async () => {
  // Given
  const { rerender } = render(
    <ProjectProvider value={{ path: "/audit/project-a", name: "A", scratch: false }}>
      <AppLayout />
    </ProjectProvider>,
  );
  await act(async () => {
    fireEvent.keyDown(document.body, { key: "s", ctrlKey: true });
  });
  expect(autosaveMocks.flushAutosave).toHaveBeenCalledWith(
    expect.objectContaining({ projectPath: "/audit/project-a" }), "kuro",
  );
  autosaveMocks.flushAutosave.mockClear();
  // When
  rerender(
    <ProjectProvider value={{ path: "/audit/project-b", name: "B", scratch: false }}>
      <AppLayout />
    </ProjectProvider>,
  );
  await act(async () => {
    fireEvent.keyDown(document.body, { key: "s", ctrlKey: true });
  });
  // Then
  expect(autosaveMocks.flushAutosave).toHaveBeenCalledWith(
    expect.objectContaining({ projectPath: "/audit/project-b" }), "kuro",
  );
  expect(autosaveMocks.flushAutosave).toHaveBeenCalledWith(
    expect.objectContaining({ projectPath: "/audit/project-b" }), "mame",
  );
});

it("keyboard warnings continue through preflight to exactly one design", async () => {
  render(<AppLayout />);
  fireEvent.keyDown(document.body, { key: "Enter", ctrlKey: true });
  const size = screen.getByRole("alertdialog");
  const level = checkKuroInputSize({ rowCount: 1000 }).level;
  fireEvent.click(within(size).getByRole("button", { name: i18next.t(level === "block" ? "inputSizeWarning.continueLabelBlock" : "inputSizeWarning.continueLabel") }));
  const warning = await screen.findByText(i18next.t("preflight.warnDiskUnavailable"));
  expect(warning).toBeInTheDocument();
  expect(useAppStore.getState().designPrimers).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: i18next.t("preflight.continueBtn") }));
  await waitFor(() => expect(useAppStore.getState().designPrimers).toHaveBeenCalledTimes(1));
});

it("cancelling keyboard warning does not run design", () => {
  render(<AppLayout />);
  fireEvent.keyDown(document.body, { key: "Enter", ctrlKey: true });
  fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: i18next.t("inputSizeWarning.cancelLabel") }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(useAppStore.getState().designPrimers).not.toHaveBeenCalled();
});
