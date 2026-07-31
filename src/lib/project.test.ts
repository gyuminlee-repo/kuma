import { beforeEach, describe, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { deleteProjectFolder, listRestorableProjects, removeRecentProject } from "./project";

vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
}));

const invokeMock = vi.mocked(invoke);

describe("project IPC wrappers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists restorable projects through list_restorable_projects_cmd", async () => {
    const restorable = [{ path: "/root/alpha", name: "alpha", last_opened: "" }];
    invokeMock.mockResolvedValueOnce(restorable);

    await expect(listRestorableProjects()).resolves.toEqual(restorable);
    expect(invokeMock).toHaveBeenCalledTimes(1);
    expect(invokeMock).toHaveBeenCalledWith("list_restorable_projects_cmd");
  });

  it("deletes a project folder through delete_project_folder_cmd", async () => {
    invokeMock.mockResolvedValueOnce([]);

    await expect(deleteProjectFolder("/root/alpha")).resolves.toEqual([]);
    expect(invokeMock).toHaveBeenCalledTimes(1);
    expect(invokeMock).toHaveBeenCalledWith("delete_project_folder_cmd", { path: "/root/alpha" });
  });

  it("keeps remove_recent_project_cmd as the list-only removal", async () => {
    // The Rust command returns the updated recent list, not the whole config.
    const remaining = [{ path: "/root/beta", name: "beta", last_opened: "" }];
    invokeMock.mockResolvedValueOnce(remaining);

    await expect(removeRecentProject("/root/alpha")).resolves.toEqual(remaining);
    expect(invokeMock).toHaveBeenCalledWith("remove_recent_project_cmd", { path: "/root/alpha" });
  });
});
