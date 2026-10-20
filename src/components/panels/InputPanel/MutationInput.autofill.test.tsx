/**
 * The EVOLVEpro table field fills itself from the project manifest only while
 * the field is empty and nobody chose a table. A table the operator picked
 * (Browse or a drop onto the window), a path the project restore brought back
 * and a round-activity hydrate that has no file are all choices the manifest
 * must not overwrite. The "operator picked" fact lives in the store so it
 * survives the panel unmounting on a tab switch and, through the autosave
 * snapshot, a restart.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAppStore } from "@/store/appStore";
import { initI18n } from "@/lib/i18n";
import ko from "@/locales/ko.json";
import type { ArtifactRef } from "@/lib/workspace";

const artifactHolder = vi.hoisted(() => ({ current: null as ArtifactRef | null }));
const browseHolder = vi.hoisted(() => ({ nextPath: "" }));

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: vi.fn() }));
vi.mock("../../../lib/file-utils", () => ({
  browseFile: vi.fn((_filters: unknown, onPick: (path: string) => void) => {
    onPick(browseHolder.nextPath);
  }),
}));
vi.mock("../../../lib/workspace", () => ({ useArtifact: () => artifactHolder.current, getActiveWorkspace: () => null }));
vi.mock("./SourceColumnPanel", () => ({
  SourceColumnPanel: () => <div data-testid="source-column-panel" />,
}));
vi.mock("../../widgets/EvolveproSelectTable", () => ({
  EvolveproSelectTable: () => <div data-testid="evolvepro-select-table" />,
}));

import { MutationInput } from "./MutationInput";
import { beginHydration, endHydration, _resetStateForTest } from "@/lib/autosave";

const MANIFEST_CSV = "/proj/evolvepro_from_manifest.csv";

function artifact(path: string): ArtifactRef {
  return {
    id: "a1",
    app: "kuro",
    step: "input",
    type: "evolvepro_csv",
    path,
    producedAt: "2026-09-29T00:00:00.000Z",
    mtime: "2026-09-29T00:00:00.000Z",
    sizeBytes: 10,
    stale: false,
  };
}

let loadSpy: ReturnType<typeof vi.fn>;
const originalLoad = useAppStore.getState().loadEvolveproCsv;

beforeEach(() => {
  useAppStore.getState().resetAll();
  loadSpy = vi.fn(async (path: string) => {
    useAppStore.setState({ evolveproCsvPath: path });
  });
  useAppStore.setState({ loadEvolveproCsv: loadSpy as unknown as typeof originalLoad });
  artifactHolder.current = artifact(MANIFEST_CSV);
});

afterEach(() => {
  useAppStore.setState({ loadEvolveproCsv: originalLoad });
  artifactHolder.current = null;
  _resetStateForTest();
});

describe("MutationInput manifest auto-fill", () => {
  it.each(["manifest", "browse"])("handles a rejected %s load without losing the store error", async (source) => {
    const message = "Strict spatial count 95 exceeds 30 eligible unique sites";
    const failingLoad = async () => {
      useAppStore.setState({ strictSpatialError: message, statusMessage: message });
      throw new Error(message);
    };
    useAppStore.setState({ loadEvolveproCsv: failingLoad });
    if (source === "browse") artifactHolder.current = null;
    browseHolder.nextPath = "/elsewhere/rejected.csv";
    await act(async () => { render(<MutationInput />); });
    if (source === "browse") {
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Browse" })); });
    }
    expect(useAppStore.getState().strictSpatialError).toBe(message);
    expect(useAppStore.getState().statusMessage).toBe(message);
  });

  it("fills an empty field from the manifest", () => {
    render(<MutationInput />);
    expect(loadSpy).toHaveBeenCalledTimes(1);
    expect(loadSpy).toHaveBeenCalledWith(MANIFEST_CSV);
  });

  it("does not replace a path the project restore brought back", () => {
    useAppStore.setState({ evolveproCsvPath: "/proj/restored.csv" });
    render(<MutationInput />);
    expect(loadSpy).not.toHaveBeenCalled();
    expect(useAppStore.getState().evolveproCsvPath).toBe("/proj/restored.csv");
  });

  it("does not replace a table the operator picked, even after the panel remounts", () => {
    // Picked, then the load failed and left the field empty, then the panel
    // unmounted and came back (tab switch). The pick is still the operator's.
    useAppStore.setState({ evolveproCsvUserPicked: true, evolveproCsvPath: "" });
    render(<MutationInput />);
    expect(loadSpy).not.toHaveBeenCalled();
  });

  it("does not replace a round-activity hydrate, which has candidates but no file", () => {
    useAppStore.setState({
      evolveproCsvPath: "",
      mutationText: "A1V",
      evolveproRankedCandidates: [{ variant: "A1V", y_pred: 1, aa_position: 1 }],
      evolveproSelectedVariants: ["A1V"],
    });
    render(<MutationInput />);
    expect(loadSpy).not.toHaveBeenCalled();
  });

  it("records a Browse pick in the store", () => {
    artifactHolder.current = null;
    browseHolder.nextPath = "/elsewhere/picked.csv";
    render(<MutationInput />);
    fireEvent.click(screen.getByRole("button", { name: "Browse" }));
    expect(loadSpy).toHaveBeenCalledWith("/elsewhere/picked.csv");
    expect(useAppStore.getState().evolveproCsvUserPicked).toBe(true);
  });

  it("uses the active locale for the working file-picker button", async () => {
    // Given: Korean is loaded and there is no manifest-driven selection.
    artifactHolder.current = null;
    browseHolder.nextPath = "/elsewhere/korean.csv";
    await initI18n("ko");
    const view = render(<MutationInput />);
    try {
      // When: the operator uses the localized control.
      fireEvent.click(screen.getByRole("button", { name: ko.common.browse }));
      // Then: the same file-picking action runs under that locale.
      expect(loadSpy).toHaveBeenCalledWith("/elsewhere/korean.csv");
      expect(useAppStore.getState().evolveproCsvUserPicked).toBe(true);
    } finally {
      view.unmount();
      await initI18n("en");
    }
  });

  it("does not overwrite a Browse pick when the manifest updates afterwards", () => {
    artifactHolder.current = null;
    browseHolder.nextPath = "/elsewhere/picked.csv";
    const { rerender } = render(<MutationInput />);
    fireEvent.click(screen.getByRole("button", { name: "Browse" }));
    loadSpy.mockClear();

    artifactHolder.current = artifact(MANIFEST_CSV);
    act(() => {
      rerender(<MutationInput />);
    });
    expect(loadSpy).not.toHaveBeenCalled();
    expect(useAppStore.getState().evolveproCsvPath).toBe("/elsewhere/picked.csv");
  });

  it("waits for a project restore to finish before filling", () => {
    // The project branch opens the registry (the manifest artifact appears)
    // before the KURO snapshot is read. Filling then would load the manifest
    // table under the restore, and in the fingerprint fast path nothing
    // supersedes that load: its response would reseed the restored selection.
    beginHydration();
    render(<MutationInput />);
    expect(loadSpy).not.toHaveBeenCalled();

    // The restore brought no table back (fresh project): fill once it ends.
    act(() => {
      endHydration();
    });
    expect(loadSpy).toHaveBeenCalledTimes(1);
    expect(loadSpy).toHaveBeenCalledWith(MANIFEST_CSV);
  });

  it("does not fill after a restore that brought a table back", () => {
    beginHydration();
    render(<MutationInput />);
    act(() => {
      useAppStore.setState({ evolveproCsvPath: "/proj/restored.csv" });
      endHydration();
    });
    expect(loadSpy).not.toHaveBeenCalled();
  });

  it("clears the picked flag on reset so a new project can auto-fill again", () => {
    useAppStore.setState({ evolveproCsvUserPicked: true });
    useAppStore.getState().resetAll();
    expect(useAppStore.getState().evolveproCsvUserPicked).toBe(false);
  });
});
