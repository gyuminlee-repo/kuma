import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { MenuBar } from "./MenuBar";

const autosaveMocks = vi.hoisted(() => ({
  flushAutosave: vi.fn(() => Promise.resolve()),
}));

vi.mock("@/lib/autosave", () => ({
  flushAutosave: autosaveMocks.flushAutosave,
}));

vi.mock("../../lib/autosave", () => ({
  flushAutosave: autosaveMocks.flushAutosave,
}));

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
  spawnSidecar: vi.fn(() => Promise.resolve()),
  getLastProgressAt: vi.fn(() => Date.now()),
}));

function pressCtrlS(target: Element | Document = document): void {
  target.dispatchEvent(
    new KeyboardEvent("keydown", { key: "s", ctrlKey: true, bubbles: true, cancelable: true }),
  );
}

describe("MenuBar manual save (Ctrl/Cmd+S)", () => {
  beforeEach(() => {
    autosaveMocks.flushAutosave.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it("flushes autosave for both kuro and mame kinds on Ctrl+S", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/proj", name: "proj", scratch: false }}>
        <MenuBar />
      </ProjectProvider>,
    );

    pressCtrlS();

    expect(autosaveMocks.flushAutosave).toHaveBeenCalledWith(
      expect.objectContaining({ projectPath: "/tmp/proj", scratch: false }),
      "kuro",
    );
    expect(autosaveMocks.flushAutosave).toHaveBeenCalledWith(
      expect.objectContaining({ projectPath: "/tmp/proj", scratch: false }),
      "mame",
    );
  });

  it("still triggers save when focus is inside a textarea", () => {
    render(
      <ProjectProvider value={{ path: "/tmp/proj", name: "proj", scratch: false }}>
        <MenuBar />
        <textarea data-testid="scratch-textarea" />
      </ProjectProvider>,
    );

    const textarea = screen.getByTestId("scratch-textarea");
    textarea.focus();
    pressCtrlS(textarea);

    expect(autosaveMocks.flushAutosave).toHaveBeenCalled();
  });

  it("does not double-flush on a single Ctrl+S press", () => {
    render(
      <ProjectProvider value={{ path: "/tmp/proj", name: "proj", scratch: false }}>
        <MenuBar />
      </ProjectProvider>,
    );

    pressCtrlS();

    // One press → exactly one flush call per kind (kuro + mame), not more.
    const calls = autosaveMocks.flushAutosave.mock.calls as unknown as unknown[][];
    const kuroCalls = calls.filter((c) => c[1] === "kuro");
    const mameCalls = calls.filter((c) => c[1] === "mame");
    expect(kuroCalls).toHaveLength(1);
    expect(mameCalls).toHaveLength(1);
  });
});
