import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Home } from "./Home";
import * as projectApi from "../lib/project";
import type { RecentProject } from "../lib/project";

vi.mock("../lib/project", async () => {
  const actual = await vi.importActual<typeof import("../lib/project")>("../lib/project");
  return {
    ...actual,
    listRecentProjects: vi.fn(),
    createProject: vi.fn(),
    loadProject: vi.fn(),
    removeRecentProject: vi.fn(),
    listRestorableProjects: vi.fn(),
    deleteProjectFolder: vi.fn(),
  };
});

const listRecentProjectsMock = vi.mocked(projectApi.listRecentProjects);
const createProjectMock = vi.mocked(projectApi.createProject);
const loadProjectMock = vi.mocked(projectApi.loadProject);
const removeRecentProjectMock = vi.mocked(projectApi.removeRecentProject);
const listRestorableProjectsMock = vi.mocked(projectApi.listRestorableProjects);
const deleteProjectFolderMock = vi.mocked(projectApi.deleteProjectFolder);

const SAMPLE = {
  path: "/tmp/sample.json",
  name: "sample",
  last_opened: "2026-04-24T09:00:00Z",
};

const OTHER = {
  path: "/tmp/other.json",
  name: "other",
  last_opened: "2026-04-25T09:00:00Z",
};

/** A promise resolved by hand, so a delete can be held mid-flight. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function renderHome(onOpenProject = vi.fn()) {
  render(
    <Home onOpenProject={onOpenProject} onOpenScratch={vi.fn()} onOpenSettings={vi.fn()} />,
  );
  return onOpenProject;
}

describe("Home", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    listRestorableProjectsMock.mockResolvedValue([]);
  });

  it("renders the primary actions and recent projects heading", async () => {
    listRecentProjectsMock.mockResolvedValueOnce([]);

    render(
      <Home
        onOpenProject={vi.fn()}
        onOpenScratch={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );

    expect(await screen.findByRole("button", { name: "+ New project" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open file" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Settings" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Recent projects" })).toBeTruthy();
  });

  it("shows the empty state when there are no recent projects", async () => {
    listRecentProjectsMock.mockResolvedValueOnce([]);

    render(
      <Home
        onOpenProject={vi.fn()}
        onOpenScratch={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );

    expect(await screen.findByText("No projects yet")).toBeTruthy();
  });

  it("shows the overview card on the empty-recent state", async () => {
    listRecentProjectsMock.mockResolvedValueOnce([]);

    render(
      <Home
        onOpenProject={vi.fn()}
        onOpenScratch={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );

    expect(
      await screen.findByText("kuma — multi-round protein variant engineering, end to end."),
    ).toBeTruthy();
    expect(screen.getByText("KURO")).toBeTruthy();
    expect(screen.getByText("MAME")).toBeTruthy();
    expect(screen.getByText("Variant selection & SDM primer design")).toBeTruthy();
    expect(screen.getByText(/SDM primer results/)).toBeTruthy();
    expect(screen.getByText("NGS validation & activity")).toBeTruthy();
    expect(screen.getByText(/Sequencing QC/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Learn more" })).toBeTruthy();
  });

  it("shows the overview even when recent projects exist", async () => {
    listRecentProjectsMock.mockResolvedValueOnce([
      {
        path: "/tmp/sample.json",
        name: "sample",
        last_opened: "2026-04-24T09:00:00Z",
      },
    ]);

    render(
      <Home
        onOpenProject={vi.fn()}
        onOpenScratch={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );

    await screen.findByText("sample");
    expect(
      screen.getByText("kuma — multi-round protein variant engineering, end to end."),
    ).toBeTruthy();
    expect(screen.getByRole("region", { name: "About kuma" })).toBeTruthy();
  });

  it("collapses the overview and persists the preference", async () => {
    listRecentProjectsMock.mockResolvedValueOnce([]);

    render(
      <Home
        onOpenProject={vi.fn()}
        onOpenScratch={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );

    await screen.findByText("kuma — multi-round protein variant engineering, end to end.");
    fireEvent.click(screen.getByRole("button", { name: "Collapse" }));

    expect(
      screen.queryByText("kuma — multi-round protein variant engineering, end to end."),
    ).toBeNull();
    expect(screen.getByRole("button", { name: "About kuma" })).toBeTruthy();
    expect(localStorage.getItem("kuma.home.overviewCollapsed")).toBe("1");
  });

  it("respects a collapsed overview preference on mount", async () => {
    localStorage.setItem("kuma.home.overviewCollapsed", "1");
    listRecentProjectsMock.mockResolvedValueOnce([]);

    render(
      <Home
        onOpenProject={vi.fn()}
        onOpenScratch={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );

    expect(await screen.findByRole("button", { name: "About kuma" })).toBeTruthy();
    expect(
      screen.queryByText("kuma — multi-round protein variant engineering, end to end."),
    ).toBeNull();
  });

  it("opens the create dialog and creates a new project", async () => {
    const onOpenProject = vi.fn();

    listRecentProjectsMock.mockResolvedValueOnce([
      {
        path: "/tmp/sample.json",
        name: "sample",
        last_opened: "2026-04-24T09:00:00Z",
      },
    ]);
    createProjectMock.mockResolvedValueOnce("/tmp/new-project");
    loadProjectMock.mockResolvedValue({
      schema: 1,
      project_id: "test-project-id",
      name: "unused",
    });

    render(
      <Home
        onOpenProject={onOpenProject}
        onOpenScratch={vi.fn()}
        onOpenSettings={vi.fn()}
      />,
    );

    await screen.findByText("sample");
    fireEvent.click(screen.getByRole("button", { name: "+ New project" }));
    expect(await screen.findByRole("heading", { name: "New project" })).toBeTruthy();

    fireEvent.change(screen.getByRole("textbox", { name: "Project name" }), {
      target: { value: "alpha" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(createProjectMock).toHaveBeenCalledWith("alpha");
      expect(onOpenProject).toHaveBeenCalledWith("/tmp/new-project", { newlyCreated: true });
    });
  });

  it("opens the delete choice dialog without touching either delete API", async () => {
    listRecentProjectsMock.mockResolvedValue([SAMPLE]);

    renderHome();
    await screen.findByText("sample");
    fireEvent.click(screen.getByTestId("delete-project"));

    expect(await screen.findByTestId("delete-choice-step")).toBeTruthy();
    expect(removeRecentProjectMock).not.toHaveBeenCalled();
    expect(deleteProjectFolderMock).not.toHaveBeenCalled();
  });

  it("removes only the list entry when the list-only option is chosen", async () => {
    listRecentProjectsMock.mockResolvedValue([SAMPLE, OTHER]);
    // remove_recent_project_cmd resolves with the updated recent list itself.
    removeRecentProjectMock.mockResolvedValue([OTHER]);

    renderHome();
    await screen.findByText("sample");
    fireEvent.click(screen.getAllByTestId("delete-project")[0]);
    fireEvent.click(await screen.findByTestId("delete-from-list"));

    await waitFor(() => {
      expect(removeRecentProjectMock).toHaveBeenCalledWith(SAMPLE.path);
    });
    expect(removeRecentProjectMock).toHaveBeenCalledTimes(1);
    expect(deleteProjectFolderMock).not.toHaveBeenCalled();
    // The returned list must actually reach the rendered recent list.
    await waitFor(() => {
      expect(screen.queryByText("sample")).toBeNull();
    });
    expect(screen.getByText("other")).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByTestId("delete-choice-step")).toBeNull();
    });
  });

  it("asks for a second confirmation before trashing the folder", async () => {
    listRecentProjectsMock.mockResolvedValue([SAMPLE]);

    renderHome();
    await screen.findByText("sample");
    fireEvent.click(screen.getByTestId("delete-project"));
    fireEvent.click(await screen.findByTestId("delete-folder"));

    expect(await screen.findByTestId("delete-folder-confirm-step")).toBeTruthy();
    expect(deleteProjectFolderMock).not.toHaveBeenCalled();
    expect(removeRecentProjectMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("delete-folder-cancel")).toHaveFocus();
  });

  it("trashes the folder once the confirmation is accepted", async () => {
    listRecentProjectsMock.mockResolvedValue([SAMPLE]);
    deleteProjectFolderMock.mockResolvedValue([]);

    renderHome();
    await screen.findByText("sample");
    fireEvent.click(screen.getByTestId("delete-project"));
    fireEvent.click(await screen.findByTestId("delete-folder"));
    fireEvent.click(await screen.findByTestId("delete-folder-confirm"));

    await waitFor(() => {
      expect(deleteProjectFolderMock).toHaveBeenCalledWith(SAMPLE.path);
    });
    expect(deleteProjectFolderMock).toHaveBeenCalledTimes(1);
    expect(removeRecentProjectMock).not.toHaveBeenCalled();
  });

  it("ignores repeat clicks while a list-only removal is in flight", async () => {
    listRecentProjectsMock.mockResolvedValue([SAMPLE]);
    const pending = deferred<RecentProject[]>();
    removeRecentProjectMock.mockReturnValue(pending.promise);

    renderHome();
    await screen.findByText("sample");
    fireEvent.click(screen.getByTestId("delete-project"));
    const listOnly = await screen.findByTestId("delete-from-list");

    fireEvent.click(listOnly);
    fireEvent.click(listOnly);
    fireEvent.click(listOnly);

    expect(removeRecentProjectMock).toHaveBeenCalledTimes(1);
    expect(listOnly).toBeDisabled();

    pending.resolve([]);
    await waitFor(() => {
      expect(screen.queryByTestId("delete-choice-step")).toBeNull();
    });
    expect(removeRecentProjectMock).toHaveBeenCalledTimes(1);
  });

  it("ignores repeat clicks while the folder is being moved to the trash", async () => {
    listRecentProjectsMock.mockResolvedValue([SAMPLE]);
    const pending = deferred<RecentProject[]>();
    deleteProjectFolderMock.mockReturnValue(pending.promise);

    renderHome();
    await screen.findByText("sample");
    fireEvent.click(screen.getByTestId("delete-project"));
    fireEvent.click(await screen.findByTestId("delete-folder"));
    const confirm = await screen.findByTestId("delete-folder-confirm");

    fireEvent.click(confirm);
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(deleteProjectFolderMock).toHaveBeenCalledTimes(1);
    expect(confirm).toBeDisabled();

    pending.resolve([]);
    await waitFor(() => {
      expect(screen.queryByTestId("delete-folder-confirm-step")).toBeNull();
    });
    // A stale second call would surface a spurious "not an existing directory".
    expect(deleteProjectFolderMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/not an existing directory/)).toBeNull();
  });

  it("cancels the confirmation step without calling any delete API", async () => {
    listRecentProjectsMock.mockResolvedValue([SAMPLE]);

    renderHome();
    await screen.findByText("sample");
    fireEvent.click(screen.getByTestId("delete-project"));
    fireEvent.click(await screen.findByTestId("delete-folder"));
    fireEvent.click(await screen.findByTestId("delete-folder-cancel"));

    await waitFor(() => {
      expect(screen.queryByTestId("delete-folder-confirm-step")).toBeNull();
    });
    expect(deleteProjectFolderMock).not.toHaveBeenCalled();
    expect(removeRecentProjectMock).not.toHaveBeenCalled();
  });

  it("reopens on the choice step after a folder delete", async () => {
    listRecentProjectsMock.mockResolvedValue([SAMPLE, OTHER]);
    deleteProjectFolderMock.mockResolvedValue([OTHER]);

    renderHome();
    await screen.findByText("sample");
    fireEvent.click(screen.getAllByTestId("delete-project")[0]);
    fireEvent.click(await screen.findByTestId("delete-folder"));
    fireEvent.click(await screen.findByTestId("delete-folder-confirm"));

    await waitFor(() => {
      expect(deleteProjectFolderMock).toHaveBeenCalledWith(SAMPLE.path);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("delete-folder-confirm-step")).toBeNull();
    });

    fireEvent.click(screen.getByTestId("delete-project"));
    expect(await screen.findByTestId("delete-choice-step")).toBeTruthy();
    expect(screen.queryByTestId("delete-folder-confirm-step")).toBeNull();
  });

  it("renders restorable projects and reopens one on restore", async () => {
    const onOpenProject = vi.fn();
    listRecentProjectsMock.mockResolvedValue([]);
    listRestorableProjectsMock.mockResolvedValue([
      { path: "/tmp/left-behind.json", name: "left-behind", last_opened: "" },
    ]);
    loadProjectMock.mockResolvedValue({
      schema: 1,
      project_id: "restored-id",
      name: "left-behind",
    });

    renderHome(onOpenProject);

    expect(await screen.findByText("left-behind")).toBeTruthy();
    expect(screen.getByText("/tmp/left-behind.json")).toBeTruthy();

    fireEvent.click(screen.getByTestId("restore-project"));

    await waitFor(() => {
      expect(loadProjectMock).toHaveBeenCalledWith("/tmp/left-behind.json");
      expect(onOpenProject).toHaveBeenCalledWith("/tmp/left-behind.json");
    });
  });
});
