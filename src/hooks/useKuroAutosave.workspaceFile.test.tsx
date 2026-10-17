/**
 * A session opened from a `.kuro.json` on Home saves into that file, in the
 * workspace format Home reads it in. It used to save the autosave snapshot to
 * the app-data scratch file and report "Saved", so reopening the file showed
 * it as it was before the edits.
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const schedule = vi.hoisted(() => vi.fn());
vi.mock("@/lib/autosave", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/autosave")>()),
  scheduleAutosave: schedule,
}));
vi.mock("@/lib/ipc-kuro", () => ({ sendRequest: vi.fn(), setProgressHandler: vi.fn(), cancelAndRespawn: vi.fn() }));

import { ProjectProvider, type KumaProject } from "@/state/projectContext";
import { useAppStore } from "@/store/appStore";
import { useKuroAutosave } from "./useKuroAutosave";

function Harness() {
  useKuroAutosave();
  return null;
}

afterEach(cleanup);

let edits = 0;
function lastScheduled(project: KumaProject) {
  schedule.mockClear();
  edits += 1;
  render(<ProjectProvider value={project}><Harness /></ProjectProvider>);
  act(() => useAppStore.setState({ mutationText: `V${edits}A` }));
  const [target, kind, build] = schedule.mock.calls.at(-1) ?? [];
  return { target, kind, snapshot: typeof build === "function" ? build() : undefined };
}

describe("KURO autosave of a workspace file session", () => {
  it("targets the opened file with the workspace format", () => {
    const file = "/shared/plan.kuro.json";
    const { target, kind, snapshot } = lastScheduled({ path: file, name: "plan", scratch: true, workspaceFile: file });
    expect(kind).toBe("kuro");
    expect(target).toMatchObject({ workspaceFile: file });
    expect(snapshot).toMatchObject({ schema_version: "0.3" });
  });

  it("keeps the autosave snapshot for an ordinary project", () => {
    const { target, snapshot } = lastScheduled({ path: "/projects/a", name: "a", scratch: false });
    expect(target).not.toHaveProperty("workspaceFile", expect.any(String));
    expect(snapshot).toHaveProperty("schema");
    expect(snapshot).not.toHaveProperty("schema_version");
  });
});
