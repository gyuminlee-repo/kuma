/**
 * The Step 1 Barcode Setup form belongs to a project (item 8 of the 2026-09-29
 * input audit).
 *
 * It used to sit under one global key that `resetMameAll` removed on every
 * project open, so reopening a project always showed an empty form, and until
 * then one project's FASTA and seeds showed up in any other. Now the form is
 * stored per project path; opening a project keeps it and Clear All removes it.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { resetMameAll } from "@/store/mame/resetAll";
import { barcodeSetupStorageKey } from "@/lib/mame/barcodeSetupFormStorage";

const rpc = vi.hoisted(() => vi.fn());
vi.mock("@/lib/ipc", () => ({ rawSidecarRpc: rpc }));
vi.mock("@/lib/ipc-mame", () => ({
  sendRequest: vi.fn(),
  isSidecarRunning: () => false,
}));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ readTextFile: vi.fn(async () => "") }));
vi.mock("@/lib/workspace", () => ({
  registerArtifacts: vi.fn(),
  getActiveWorkspace: vi.fn(() => null),
  clearWorkspace: vi.fn(),
}));
vi.mock("@/lib/overwriteConfirm", () => ({ fileExists: vi.fn(), requestOverwriteConfirm: vi.fn() }));
vi.mock("@/lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));

import { BarcodeSetupPanel } from "./BarcodeSetupPanel";

function panelFor(path: string) {
  return (
    <ProjectProvider value={{ path, name: "Demo", scratch: false }}>
      <BarcodeSetupPanel />
    </ProjectProvider>
  );
}

function geneName(): HTMLElement {
  return screen.getByLabelText("Gene name");
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  useMameAppStore.setState({
    resetEpoch: 0,
    sharedFastaPath: null,
    mameSamplePrefill: null,
    cdsCandidates: [],
    selectedCdsIndex: 0,
  });
});

describe("Barcode Setup form is kept per project", () => {
  it("the store keeps the bridged project path through that reset", async () => {
    useMameAppStore.getState().setFormStoragePath("/projA");
    useMameAppStore.getState().setProjectPath("/projA");
    await act(async () => {
      await resetMameAll({ preserveWorkspaceArtifacts: true });
    });
    expect(useMameAppStore.getState().formStoragePath).toBe("/projA");
    expect(useMameAppStore.getState().projectPath).toBe("/projA");
  });

  it("survives the reset that opening a project runs", async () => {
    render(panelFor("/projA"));
    fireEvent.change(geneName(), { target: { value: "ispS" } });

    // useAutosaveHydration: resetMameAll({ preserveWorkspaceArtifacts: true }).
    await act(async () => {
      await resetMameAll({ preserveWorkspaceArtifacts: true });
    });

    expect(geneName()).toHaveValue("ispS");
  });

  it("shows each project its own form", () => {
    const view = render(panelFor("/projA"));
    fireEvent.change(geneName(), { target: { value: "ispS" } });

    view.rerender(panelFor("/projB"));
    expect(geneName()).toHaveValue("");
    fireEvent.change(geneName(), { target: { value: "dxs" } });

    view.rerender(panelFor("/projA"));
    expect(geneName()).toHaveValue("ispS");
  });

  it("Clear All empties the form and forgets it", async () => {
    // useMameAutosave bridges the project path into the store; Clear All reads it.
    useMameAppStore.getState().setFormStoragePath("/projA");
    render(panelFor("/projA"));
    fireEvent.change(geneName(), { target: { value: "ispS" } });

    await act(async () => {
      await resetMameAll();
    });

    expect(geneName()).toHaveValue("");
    expect(localStorage.getItem(barcodeSetupStorageKey("/projA"))).toBeNull();
  });

  it("keeps a saved gene range instead of re-picking the longest candidate", async () => {
    localStorage.setItem(
      barcodeSetupStorageKey("/projA"),
      JSON.stringify({
        fastaPath: "/projA/genes.gb",
        geneStart: "0",
        geneEnd: "303",
        geneName: "short_gene",
      }),
    );
    rpc.mockResolvedValue({
      header: "genes",
      seq_length: 1800,
      genes: [
        { gene: "short_gene", product: "short", cds_start: 0, cds_end: 303, aa_length: 101 },
        { gene: "long_gene", product: "long", cds_start: 600, cds_end: 1503, aa_length: 301 },
      ],
    });

    render(panelFor("/projA"));

    await waitFor(() => expect(useMameAppStore.getState().cdsCandidates).toHaveLength(2));
    expect(geneName()).toHaveValue("short_gene");
    expect(useMameAppStore.getState().selectedCdsIndex).toBe(0);
  });
});

describe("the former global key", () => {
  it("is adopted by the project its paths lie in, then removed", () => {
    localStorage.setItem(
      "kuma:mame:barcodeSetup",
      JSON.stringify({ geneName: "ispS", barcodeSeedsPath: "/projA/input/seeds.xlsx" }),
    );
    render(panelFor("/projA"));
    expect(geneName()).toHaveValue("ispS");
    expect(localStorage.getItem("kuma:mame:barcodeSetup")).toBeNull();
    expect(localStorage.getItem(barcodeSetupStorageKey("/projA"))).not.toBeNull();
  });

  it("is not shown in a project its paths do not belong to", () => {
    localStorage.setItem(
      "kuma:mame:barcodeSetup",
      JSON.stringify({ geneName: "ispS", fastaPath: "/projA/input/cds.fa" }),
    );
    render(panelFor("/projB"));
    expect(geneName()).toHaveValue("");
    expect(localStorage.getItem("kuma:mame:barcodeSetup")).not.toBeNull();
  });
});
