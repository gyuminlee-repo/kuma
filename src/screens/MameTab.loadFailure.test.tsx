/**
 * A failed project load is distinguishable from a cancel.
 *
 * `confirmLoad` was `try { await loadProject(...); dispatch } finally { close }`
 * with no `catch`. On rejection the dialog closed, the
 * `kuma:project-load-request` event never fired, nothing changed and nothing
 * was said, which is byte-for-byte what the Cancel button produces. The
 * rejection then escaped unhandled through `void confirmLoad()`.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/mame/layout/MameAppLayout", () => ({
  MameAppLayout: () => <div data-testid="mame-app-layout" />,
}));

vi.mock("@/lib/ipc-mame", () => ({ sendRequest: vi.fn() }));

vi.mock("@/lib/project", () => ({
  listRecentProjects: vi.fn(),
  loadProject: vi.fn(),
}));

vi.mock("@/state/projectContext", () => ({
  useKumaProject: () => ({ project_id: "p1", name: "Proj", path: "/tmp/kuma/Proj" }),
}));

import { MameTab } from "./MameTab";
import { listRecentProjects, loadProject } from "@/lib/project";
import { sendRequest } from "@/lib/ipc-mame";

const loadProjectMock = vi.mocked(loadProject);
const listRecentProjectsMock = vi.mocked(listRecentProjects);
const sendRequestMock = vi.mocked(sendRequest);

const MATCH_PATH = "/tmp/kuma/Matched";

/** Drive the drop handler to the point where the confirm dialog is open. */
async function openMatchDialog() {
  const loadRequests: string[] = [];
  const onLoadRequest = (ev: Event) => {
    loadRequests.push((ev as CustomEvent<{ path: string }>).detail.path);
  };
  window.addEventListener("kuma:project-load-request", onLoadRequest);

  render(<MameTab />);

  // The handler asks the sidecar for the workbook's project_id, then looks it
  // up in recents; a hit is what opens the dialog.
  sendRequestMock.mockResolvedValue({ project_id: "matched" } as never);
  listRecentProjectsMock.mockResolvedValue([
    { path: MATCH_PATH, name: "Matched", last_opened: "", project_id: "matched" },
  ] as never);

  window.dispatchEvent(
    new CustomEvent("kuma:mame-xlsx-dropped", { detail: { path: "/tmp/drop.xlsx" } }),
  );

  await screen.findByRole("button", { name: "Load" });
  return {
    loadRequests,
    cleanup: () => window.removeEventListener("kuma:project-load-request", onLoadRequest),
  };
}

describe("MameTab: matching-project load failure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the dialog open and states the reason when the load fails", async () => {
    const { loadRequests, cleanup } = await openMatchDialog();
    loadProjectMock.mockRejectedValue(new Error("SchemaTooNew"));

    await userEvent.click(screen.getByRole("button", { name: "Load" }));

    const alert = await screen.findByTestId("mame-tab-load-error");
    expect(alert.textContent).toContain("SchemaTooNew");
    // The distinguishing part: a cancel closes the dialog, a failure does not.
    expect(screen.getByRole("button", { name: "Load" })).toBeTruthy();
    // And the load event must NOT have fired for a project that never loaded.
    expect(loadRequests).toEqual([]);
    cleanup();
  });

  it("closes the dialog and fires the load event on success", async () => {
    const { loadRequests, cleanup } = await openMatchDialog();
    loadProjectMock.mockResolvedValue(undefined as never);

    await userEvent.click(screen.getByRole("button", { name: "Load" }));

    await waitFor(() => expect(loadRequests).toEqual([MATCH_PATH]));
    expect(screen.queryByTestId("mame-tab-load-error")).toBeNull();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Load" })).toBeNull());
    cleanup();
  });

  it("says nothing when the dialog is cancelled", async () => {
    const { loadRequests, cleanup } = await openMatchDialog();

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Load" })).toBeNull());
    expect(loadProjectMock).not.toHaveBeenCalled();
    expect(loadRequests).toEqual([]);
    cleanup();
  });
});
