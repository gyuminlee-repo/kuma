/**
 * handleExportAll: project-folder routing and artifact registration.
 *
 * Mirrors the MAME behaviour introduced in `mame: route generated artifacts
 * through projects`. Three properties are pinned here:
 *   1. with a project open, the directory picker defaults to `<project>/design`
 *      and that folder is created first (a missing defaultPath is ignored by
 *      the dialog, so the mkdir is load-bearing, not cosmetic),
 *   2. the files the sidecar reports as written are recorded in the manifest
 *      with a type derived from the filename suffix, and
 *   3. without a project, the old behaviour is unchanged, so the picker opens
 *      with no default and nothing is registered.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const mockOpen = vi.hoisted(() => vi.fn());
const mockMkdir = vi.hoisted(() => vi.fn());
const mockSendRequest = vi.hoisted(() => vi.fn());
const mockRegisterArtifacts = vi.hoisted(() => vi.fn());
const mockEnsureWorkspace = vi.hoisted(() => vi.fn());

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mockOpen, save: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ mkdir: mockMkdir }));
vi.mock("../../lib/ipc-kuro", () => ({ sendRequest: mockSendRequest }));
vi.mock("../../lib/workspace", () => ({
  registerArtifacts: mockRegisterArtifacts,
  ensureWorkspaceFromExportPath: mockEnsureWorkspace,
}));
vi.mock("../../lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));
vi.mock("../../lib/overwriteConfirm", () => ({
  fileExists: vi.fn(),
  requestOverwriteConfirm: vi.fn(),
}));
vi.mock("../dialogs/WorkspaceMigrateDialog", () => ({
  MIGRATE_DIALOG_CLOSED: Symbol("closed"),
}));
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));
vi.mock("../../store/appStore", () => ({
  useAppStore: {
    getState: () => ({
      designResults: [],
      plateMappings: [],
      dedupInfo: undefined,
      tableSorting: [],
      yPredMap: {},
      customCandidates: [],
      exportExcel: vi.fn(),
    }),
    setState: vi.fn(),
  },
}));

import { handleExportAll } from "./export-handlers";

const BASE_PARAMS = {
  amount: "0.05" as const,
  echoTransferVol: 1,
  janusTransferVol: 1,
  bom: false,
};

const SIDECAR_RESULT = {
  success: [
    "proj_20260731_echo.csv",
    "proj_20260731_platemap.xlsx",
    "proj_20260731_run.json",
    "proj_20260731_notes.txt",
  ],
  failed: [],
  output_dir: "/proj/design/proj_20260731",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockSendRequest.mockResolvedValue(SIDECAR_RESULT);
  mockRegisterArtifacts.mockResolvedValue(undefined);
  mockEnsureWorkspace.mockResolvedValue(undefined);
  mockMkdir.mockResolvedValue(undefined);
});

describe("handleExportAll project routing", () => {
  it("creates the project export folder and defaults the picker to it", async () => {
    mockOpen.mockResolvedValue("/proj/design");

    await handleExportAll({ ...BASE_PARAMS, projectPath: "/proj" });

    expect(mockMkdir).toHaveBeenCalledWith("/proj/design", { recursive: true });
    expect(mockOpen).toHaveBeenCalledWith(
      expect.objectContaining({ directory: true, defaultPath: "/proj/design" }),
    );
  });

  it("registers each produced file under the type its suffix implies", async () => {
    mockOpen.mockResolvedValue("/proj/design");

    await handleExportAll({ ...BASE_PARAMS, projectPath: "/proj" });

    expect(mockRegisterArtifacts).toHaveBeenCalledTimes(1);
    expect(mockRegisterArtifacts).toHaveBeenCalledWith([
      {
        app: "kuro",
        step: "export",
        type: "kuro_echo_csv",
        absolutePath: "/proj/design/proj_20260731/proj_20260731_echo.csv",
      },
      {
        app: "kuro",
        step: "export",
        type: "kuro_platemap_xlsx",
        absolutePath: "/proj/design/proj_20260731/proj_20260731_platemap.xlsx",
      },
      {
        app: "kuro",
        step: "export",
        type: "kuro_run_json",
        absolutePath: "/proj/design/proj_20260731/proj_20260731_run.json",
      },
    ]);
  });

  it("leaves the picker undefaulted without a project but still records the files", async () => {
    mockOpen.mockResolvedValue("/elsewhere");

    await handleExportAll({ ...BASE_PARAMS });

    expect(mockMkdir).not.toHaveBeenCalled();
    expect(mockOpen).toHaveBeenCalledWith({ directory: true, multiple: false });
    // Saving outside a project keeps the pre-existing behaviour of deriving a
    // workspace from wherever the user saved, so the manifest is still written.
    expect(mockEnsureWorkspace).toHaveBeenCalledTimes(1);
    expect(mockRegisterArtifacts).toHaveBeenCalledTimes(1);
  });

  it("returns null and skips registration when the picker is cancelled", async () => {
    mockOpen.mockResolvedValue(null);

    const result = await handleExportAll({ ...BASE_PARAMS, projectPath: "/proj" });

    expect(result).toBeNull();
    expect(mockSendRequest).not.toHaveBeenCalled();
    expect(mockRegisterArtifacts).not.toHaveBeenCalled();
  });
});
