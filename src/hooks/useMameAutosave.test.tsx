import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProjectProvider } from "@/state/projectContext";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useMameAutosave } from "./useMameAutosave";

const autosaveMocks = vi.hoisted(() => ({
  scheduleAutosave: vi.fn(),
  flushAutosave: vi.fn(() => Promise.resolve()),
}));

vi.mock("@/lib/autosave", () => ({
  scheduleAutosave: autosaveMocks.scheduleAutosave,
  flushAutosave: autosaveMocks.flushAutosave,
}));

let latestFlush: (() => Promise<void>) | null = null;

function Harness() {
  const { flushMameAutosave } = useMameAutosave();
  latestFlush = flushMameAutosave;
  return null;
}

describe("useMameAutosave", () => {
  beforeEach(() => {
    latestFlush = null;
    autosaveMocks.scheduleAutosave.mockClear();
    autosaveMocks.flushAutosave.mockClear();
    useMameAppStore.getState().resetInput();
  });

  afterEach(() => {
    cleanup();
  });

  it("schedules mame autosave when persisted input fields change", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/kuma-project", name: "Demo", scratch: false }}>
        <Harness />
      </ProjectProvider>,
    );

    act(() => {
      useMameAppStore.getState().setInputDir("/runs/2026-05-26");
    });

    await waitFor(() => {
      expect(autosaveMocks.scheduleAutosave).toHaveBeenCalledTimes(1);
    });
    expect(autosaveMocks.scheduleAutosave).toHaveBeenCalledWith(
      expect.objectContaining({ projectPath: "/tmp/kuma-project", scratch: false }),
      "mame",
      expect.any(Function),
    );
  });

  it("skips scheduling for scratch projects", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/kuma-scratch", name: "Scratch", scratch: true }}>
        <Harness />
      </ProjectProvider>,
    );

    act(() => {
      useMameAppStore.getState().setInputDir("/runs/scratch");
    });

    await Promise.resolve();
    expect(autosaveMocks.scheduleAutosave).not.toHaveBeenCalled();
  });

  it("flushes the current mame autosave target", async () => {
    render(
      <ProjectProvider value={{ path: "/tmp/kuma-project", name: "Demo", scratch: false }}>
        <Harness />
      </ProjectProvider>,
    );

    if (latestFlush === null) {
      throw new Error("flush callback was not registered");
    }

    await act(async () => {
      await latestFlush?.();
    });

    expect(autosaveMocks.flushAutosave).toHaveBeenCalledWith(
      expect.objectContaining({ projectPath: "/tmp/kuma-project", scratch: false }),
      "mame",
    );
  });
});
