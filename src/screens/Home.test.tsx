import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Home } from "./Home";
import * as projectApi from "../lib/project";

vi.mock("../lib/project", async () => {
  const actual = await vi.importActual<typeof import("../lib/project")>("../lib/project");
  return {
    ...actual,
    listRecentProjects: vi.fn(),
    createProject: vi.fn(),
    loadProject: vi.fn(),
  };
});

const listRecentProjectsMock = vi.mocked(projectApi.listRecentProjects);
const createProjectMock = vi.mocked(projectApi.createProject);
const loadProjectMock = vi.mocked(projectApi.loadProject);

describe("Home", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
      expect(onOpenProject).toHaveBeenCalledWith("/tmp/new-project");
    });
  });
});
