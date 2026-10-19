/**
 * The KURO drawer strip states what happened, not fixed text. It used to say
 * "Saved just now" before any save and after a failed one, "complete" over an
 * empty result table and "all targets" with no export at all, and a save that
 * finished for the previous project counted for the one now open.
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AutosaveEvent } from "@/lib/autosave";

const events = vi.hoisted(() => ({ listener: null as ((event: AutosaveEvent) => void) | null }));
vi.mock("@/lib/autosave", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/autosave")>()),
  onAutosaveEvent: (listener: (event: AutosaveEvent) => void) => {
    events.listener = listener;
    return () => { if (events.listener === listener) events.listener = null; };
  },
}));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));

import { KuroDrawerStrip } from "./KuroChrome";
import { ProjectProvider } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";

const A = { path: "/projects/A", name: "A", scratch: false };
const B = { path: "/projects/B", name: "B", scratch: false };
const SAVED_AT = "2026-10-17T03:04:05Z";

function strip(project = A) {
  return <ProjectProvider value={project}><KuroDrawerStrip /></ProjectProvider>;
}
function saved(projectPath: string): AutosaveEvent {
  return { kind: "kuro", type: "saved", savedAt: SAVED_AT, target: { projectPath, scratch: false } };
}

beforeEach(() => {
  useAppStore.setState({
    currentSubStep: "design.load",
    isDesigning: false,
    isExporting: false,
    designResults: [],
    successCount: 0,
    totalCount: 0,
  });
});
afterEach(cleanup);

describe("KURO drawer autosave row", () => {
  it("claims nothing before the first save", () => {
    render(strip());
    expect(screen.queryByText("just now")).toBeNull();
  });

  it("shows the time of this project's save", () => {
    render(strip());
    act(() => events.listener?.(saved(A.path)));
    expect(screen.getByText(new Date(SAVED_AT).toLocaleTimeString())).toBeInTheDocument();
  });

  it("shows a failed save as failed", () => {
    render(strip());
    act(() => events.listener?.({
      kind: "kuro", type: "error", error: new Error("disk full"), target: { projectPath: A.path, scratch: false },
    }));
    expect(screen.getByText("Save failed")).toBeInTheDocument();
  });

  it("ignores a save of the previous project that lands after the switch", () => {
    const view = render(strip(A));
    view.rerender(strip(B));
    act(() => events.listener?.(saved(A.path)));
    expect(screen.queryByText(new Date(SAVED_AT).toLocaleTimeString())).toBeNull();
  });
});

describe("KURO drawer run and export rows", () => {
  it("does not call an empty result table complete", () => {
    useAppStore.setState({ currentSubStep: "output.summary" });
    render(strip());
    expect(screen.queryByText("complete")).toBeNull();
  });

  it("reports the designed count when there are results", () => {
    useAppStore.setState({
      currentSubStep: "output.summary",
      designResults: [{ mutation: "A1V" }] as never,
      successCount: 1,
      totalCount: 2,
    });
    render(strip());
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("does not claim every export target succeeded", () => {
    useAppStore.setState({ currentSubStep: "export.all" });
    render(strip());
    expect(screen.queryByText("all targets")).toBeNull();
  });

  it("shows a running export in the queue row", () => {
    useAppStore.setState({ currentSubStep: "export.all", isExporting: true });
    render(strip());
    expect(screen.getByText("Exporting…")).toBeInTheDocument();
  });
});
