/**
 * End-to-end frontend integration: onboarding → home → create project → workspace,
 * and Mame tab xlsx-drop → match dialog → load-project dispatch.
 *
 * Mocks:
 *  - `@/lib/project` invoke wrappers (getConfig/createProject/listRecentProjects/loadProject)
 *  - `@/lib/ipc` rpc (for Kuro export project_id pass-through + Mame read_kuma_meta)
 *  - `@/components/mame/layout/MameAppLayout` (heavy store-connected component)
 *
 * Emulates Task 10 Step 10.1 at the React layer without Tauri / Playwright.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock project API (Tauri invoke wrappers).
vi.mock("../lib/project", async () => {
  const actual = await vi.importActual<typeof import("../lib/project")>("../lib/project");
  return {
    ...actual,
    getConfig: vi.fn(),
    createProject: vi.fn(),
    loadProject: vi.fn(),
    listRecentProjects: vi.fn(),
    setProjectsRoot: vi.fn(),
  };
});

// Mock the unified sidecar IPC layer.
vi.mock("@/lib/ipc", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ipc")>();
  return {
    ...actual,
    rpc: vi.fn().mockResolvedValue({}),
  };
});

// Replace the heavy MameAppLayout with a stub that dispatches the integration event.
vi.mock("@/components/mame/layout/MameAppLayout", () => ({
  MameAppLayout: () => (
    <button
      type="button"
      data-testid="mame-drop-stub"
      onClick={() =>
        window.dispatchEvent(
          new CustomEvent("kuma:mame-xlsx-dropped", {
            detail: { path: "/tmp/incoming.xlsx" },
          }),
        )
      }
    >
      drop-xlsx
    </button>
  ),
}));

// Hide the Kuro tab body to keep the DOM lean; the integration focus is flow.
vi.mock("./KuroTab", () => ({
  KuroTab: () => <div data-testid="kuro-tab-stub">kuro</div>,
}));

import { App } from "@/App";
import * as projectApi from "../lib/project";
import { rpc } from "@/lib/ipc";

const getConfigMock = vi.mocked(projectApi.getConfig);
const createProjectMock = vi.mocked(projectApi.createProject);
const loadProjectMock = vi.mocked(projectApi.loadProject);
const listRecentProjectsMock = vi.mocked(projectApi.listRecentProjects);
const rpcMock = vi.mocked(rpc);

describe("kuma end-to-end integration (frontend)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getConfigMock.mockResolvedValue({
      projects_root: "/tmp/kuma",
      recent_projects: [],
    });
    listRecentProjectsMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("create-project flow: Home → workspace (MainShell) transition", async () => {
    const user = userEvent.setup();
    createProjectMock.mockResolvedValue("/tmp/kuma/Sample_42");
    loadProjectMock.mockResolvedValue({
      schema: 1,
      project_id: "proj-uuid-1",
      name: "Sample_42",
      stage: "draft",
    });

    render(<App />);

    // Home screen appears after getConfig resolves.
    await screen.findByRole("button", { name: /New project/ });

    await user.click(screen.getByRole("button", { name: /New project/ }));
    const input = await screen.findByLabelText("Project name");
    await user.type(input, "Sample_42");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(createProjectMock).toHaveBeenCalledWith("Sample_42");
    });
    // After creation, App transitions to workspace (MainShell header visible).
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Kuro" })).toBeTruthy();
      expect(screen.getByRole("tab", { name: "Mame" })).toBeTruthy();
    });
    // Project name surfaced in header.
    expect(screen.getByText("Sample_42")).toBeTruthy();
  });

  it("switching to Mame tab lazy-spawns the mame sidecar via ping", async () => {
    const user = userEvent.setup();
    createProjectMock.mockResolvedValue("/tmp/kuma/S");
    loadProjectMock.mockResolvedValue({
      schema: 1,
      project_id: "proj-uuid-2",
      name: "S",
      stage: "draft",
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: /New project/ }));
    const input = await screen.findByLabelText("Project name");
    await user.type(input, "S");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await screen.findByRole("tab", { name: "Mame" });
    rpcMock.mockClear();
    await user.click(screen.getByRole("tab", { name: "Mame" }));
    expect(rpcMock).toHaveBeenCalledWith("mame", "ping", {});
  });

  it("Mame xlsx drop with recognized project_id opens match dialog and loads on accept", async () => {
    const user = userEvent.setup();
    createProjectMock.mockResolvedValue("/tmp/kuma/Sample_42");
    loadProjectMock.mockResolvedValue({
      schema: 1,
      project_id: "proj-mame-42",
      name: "Sample_42",
      stage: "draft",
    });
    // Recents include a DIFFERENT project with the id advertised by the xlsx meta.
    listRecentProjectsMock.mockResolvedValue([
      {
        path: "/tmp/kuma/Other",
        name: "Other",
        last_opened: "2026-04-24T00:00:00+09:00",
        project_id: "proj-other-xlsx",
      },
    ]);
    // rpc("mame", "read_kuma_meta", ...) returns a project_id that matches Other.
    rpcMock.mockImplementation(async (kind, method) => {
      if (kind === "mame" && method === "read_kuma_meta") {
        return { project_id: "proj-other-xlsx" };
      }
      return {};
    });

    render(<App />);
    // Create+enter workspace so MainShell renders.
    await user.click(await screen.findByRole("button", { name: /New project/ }));
    await user.type(await screen.findByLabelText("Project name"), "Sample_42");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await screen.findByRole("tab", { name: "Mame" });

    // Activate Mame tab so its effect registers the drop listener.
    await user.click(screen.getByRole("tab", { name: "Mame" }));
    await screen.findByTestId("mame-drop-stub", undefined, { timeout: 5000 });

    // Simulate drop event (stub button dispatches the custom event).
    fireEvent.click(screen.getByTestId("mame-drop-stub"));

    // Dialog surfaces with the recent project's name.
    const dialogText = await screen.findByText(/Load "Other"\?/);
    expect(dialogText).toBeTruthy();

    // Accept → loadProject invoked for the recent project path.
    loadProjectMock.mockClear();
    await user.click(screen.getByRole("button", { name: "Load" }));
    await waitFor(() => {
      expect(loadProjectMock).toHaveBeenCalledWith("/tmp/kuma/Other");
    });
  });

  it("Mame xlsx drop with unknown project_id does not open the dialog", async () => {
    const user = userEvent.setup();
    createProjectMock.mockResolvedValue("/tmp/kuma/S");
    loadProjectMock.mockResolvedValue({
      schema: 1,
      project_id: "proj-current",
      name: "S",
      stage: "draft",
    });
    listRecentProjectsMock.mockResolvedValue([]);
    rpcMock.mockImplementation(async (kind, method) => {
      if (kind === "mame" && method === "read_kuma_meta") {
        return { project_id: "proj-unknown" };
      }
      return {};
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: /New project/ }));
    await user.type(await screen.findByLabelText("Project name"), "S");
    await user.click(screen.getByRole("button", { name: "Create" }));
    await user.click(await screen.findByRole("tab", { name: "Mame" }));
    await screen.findByTestId("mame-drop-stub", undefined, { timeout: 5000 });
    fireEvent.click(screen.getByTestId("mame-drop-stub"));

    // Give any async handlers a microtask window, then assert no dialog.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText("Matching project found")).toBeNull();
  });
});
