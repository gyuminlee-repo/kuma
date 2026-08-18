/**
 * "Open file" hands `load_project` a directory, because that is what it takes.
 *
 * The picker advertises `{ name: "Kuma Project", extensions: ["json"] }` with
 * `directory: false`, so it returns the manifest FILE. `load_project` does
 * `path.join("kuma.project.json")` itself (src-tauri/src/project.rs:51), so the
 * selection used to resolve to `.../kuma.project.json/kuma.project.json` and
 * could never open anything; the user saw the raw OS error instead.
 *
 * The `.kuro.json` branch is left alone on purpose: `onOpenScratch` wants the
 * file, and that asymmetry is what identified this branch as the wrong one.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const dialogMocks = vi.hoisted(() => ({ open: vi.fn() }));

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: dialogMocks.open }));

vi.mock("../lib/project", async () => {
  const actual = await vi.importActual<typeof import("../lib/project")>("../lib/project");
  return {
    ...actual,
    listRecentProjects: vi.fn(),
    listRestorableProjects: vi.fn(),
    createProject: vi.fn(),
    loadProject: vi.fn(),
    removeRecentProject: vi.fn(),
    deleteProjectFolder: vi.fn(),
  };
});

import { Home, projectDirOf } from "./Home";
import * as projectApi from "../lib/project";

const loadProjectMock = vi.mocked(projectApi.loadProject);
const listRecentProjectsMock = vi.mocked(projectApi.listRecentProjects);
const listRestorableProjectsMock = vi.mocked(projectApi.listRestorableProjects);

const PROJECT_DIR = "/tmp/kuma/MyProject";
const PROJECT_MANIFEST = `${PROJECT_DIR}/kuma.project.json`;

async function clickOpenFile() {
  const onOpenProject = vi.fn();
  const onOpenScratch = vi.fn();
  render(
    <Home
      onOpenProject={onOpenProject}
      onOpenScratch={onOpenScratch}
      onOpenSettings={vi.fn()}
    />,
  );
  await userEvent.click(await screen.findByRole("button", { name: "Open file" }));
  return { onOpenProject, onOpenScratch };
}

describe("projectDirOf", () => {
  it("strips the manifest component the picker returns", () => {
    expect(projectDirOf(PROJECT_MANIFEST)).toBe(PROJECT_DIR);
  });

  it("strips it on Windows separators too", () => {
    // The Tauri picker returns backslashes on Windows, which is the shipping target.
    expect(projectDirOf("C:\\kuma\\MyProject\\kuma.project.json")).toBe("C:\\kuma\\MyProject");
  });

  it("passes a directory through untouched", () => {
    expect(projectDirOf(PROJECT_DIR)).toBe(PROJECT_DIR);
  });

  it("leaves an unrelated json file alone", () => {
    // Only the manifest name is special; any other .json stays as picked so the
    // failure names the file the user chose rather than a folder they did not.
    expect(projectDirOf("/tmp/notes.json")).toBe("/tmp/notes.json");
  });

  it("keeps the root rather than returning an empty path", () => {
    expect(projectDirOf("/kuma.project.json")).toBe("/");
  });
});

describe("Home: Open file", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    listRecentProjectsMock.mockResolvedValue([]);
    listRestorableProjectsMock.mockResolvedValue([]);
  });

  it("loads the project FOLDER when the manifest file is picked", async () => {
    dialogMocks.open.mockResolvedValue(PROJECT_MANIFEST);
    loadProjectMock.mockResolvedValue(undefined as never);

    const { onOpenProject } = await clickOpenFile();

    await waitFor(() => expect(loadProjectMock).toHaveBeenCalled());
    expect(loadProjectMock).toHaveBeenCalledWith(PROJECT_DIR);
    expect(onOpenProject).toHaveBeenCalledWith(PROJECT_DIR);
  });

  it("still hands the FILE to onOpenScratch for a .kuro.json pick", async () => {
    dialogMocks.open.mockResolvedValue("/tmp/scratch/work.kuro.json");

    const { onOpenScratch } = await clickOpenFile();

    await waitFor(() =>
      expect(onOpenScratch).toHaveBeenCalledWith("/tmp/scratch/work.kuro.json"),
    );
    expect(loadProjectMock).not.toHaveBeenCalled();
  });

  it("does nothing when the picker is dismissed", async () => {
    dialogMocks.open.mockResolvedValue(null);

    const { onOpenProject, onOpenScratch } = await clickOpenFile();

    await waitFor(() => expect(dialogMocks.open).toHaveBeenCalled());
    expect(loadProjectMock).not.toHaveBeenCalled();
    expect(onOpenProject).not.toHaveBeenCalled();
    expect(onOpenScratch).not.toHaveBeenCalled();
  });
});
