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
    localStorage.clear();
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
    expect(screen.getByText("MAME")).toBeTruthy();
    expect(screen.getByText("Turn sequencing reads into per-variant activity.")).toBeTruthy();
    expect(screen.getByText("KURO")).toBeTruthy();
    expect(screen.getByText("Rank variants and design the next round.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Learn more" })).toBeTruthy();
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
      expect(onOpenProject).toHaveBeenCalledWith("/tmp/new-project");
    });
  });
});
