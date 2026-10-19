/**
 * An Export All belongs to the workspace it started in.
 *
 * The user can open another project while the export_all RPC runs. The files
 * it produced must be recorded in the registry of the project that exported
 * them, and the plate map must not be handed to the MAME screen of the project
 * that is open now. Export All also holds the global export flag (close and
 * sidecar-restart guards) until it settles, and an overlapping export that
 * finishes first cannot drop that flag.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockOpen = vi.hoisted(() => vi.fn());
const mockSave = vi.hoisted(() => vi.fn());
const mockSendRequest = vi.hoisted(() => vi.fn());
const mockActiveWorkspace = vi.hoisted(() => vi.fn<() => string | null>());
const mockRegister = vi.hoisted(() => vi.fn(async () => undefined));
const mockEnsure = vi.hoisted(() => vi.fn(async () => undefined));
const setState = vi.hoisted(() => vi.fn());
const mame = vi.hoisted(() => ({ expectedPath: "", chooseExpectedPath: vi.fn() }));

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mockOpen, save: mockSave }));
vi.mock("@tauri-apps/plugin-fs", () => ({ mkdir: vi.fn(async () => undefined) }));
vi.mock("../../lib/ipc-kuro", () => ({ sendRequest: mockSendRequest }));
vi.mock("../../lib/workspace", () => ({
  registerArtifacts: mockRegister,
  ensureWorkspaceFromExportPath: mockEnsure,
  getActiveWorkspace: mockActiveWorkspace,
}));
vi.mock("../../lib/openFolder", () => ({ revealInOSFolder: vi.fn() }));
vi.mock("../../lib/overwriteConfirm", () => ({
  fileExists: vi.fn(async () => false),
  requestOverwriteConfirm: vi.fn(),
}));
vi.mock("../dialogs/WorkspaceMigrateDialog", () => ({ MIGRATE_DIALOG_CLOSED: Symbol("closed") }));
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
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
      setStatus: vi.fn(),
    }),
    setState,
  },
}));
vi.mock("../../store/mame/mameAppStore", () => ({ useMameAppStore: { getState: () => mame } }));

import { handleExportAll, handleExportBenchmarkCsv } from "./export-handlers";

const PARAMS = {
  amount: "0.05" as const,
  echoTransferVol: 1,
  janusTransferVol: 1,
  bom: false,
  projectPath: "/proj",
};
const RESULT = {
  success: ["run_echo.csv", "run_platemap.xlsx"],
  failed: [],
  output_dir: "/proj/design/run",
};

function deferredExportAll(): { finish: (value: unknown) => void } {
  const handle = { finish: (_value: unknown) => {} };
  mockSendRequest.mockImplementation((method: string) =>
    method === "export_all"
      ? new Promise((resolve) => { handle.finish = resolve; })
      : Promise.resolve({}));
  return handle;
}

beforeEach(() => {
  vi.clearAllMocks();
  mame.expectedPath = "";
  mockOpen.mockResolvedValue("/proj/design");
  mockActiveWorkspace.mockReturnValue("/proj");
  mockSendRequest.mockResolvedValue(RESULT);
});

describe("Export All records into the workspace it started in", () => {
  it("records into the starting project and hands the plate map over when nothing changed", async () => {
    await handleExportAll(PARAMS);
    expect(mockRegister).toHaveBeenCalledWith(expect.any(Array), "/proj");
    expect(mockEnsure).not.toHaveBeenCalled();
    expect(mame.chooseExpectedPath).toHaveBeenCalledWith("/proj/design/run/run_platemap.xlsx");
  });

  it("keeps a late export out of the project opened while it ran", async () => {
    const pending = deferredExportAll();
    const run = handleExportAll(PARAMS);
    await vi.waitFor(() => expect(mockSendRequest).toHaveBeenCalledWith("export_all", expect.anything()));
    mockActiveWorkspace.mockReturnValue("/other");
    pending.finish(RESULT);
    await run;

    expect(mockRegister).toHaveBeenCalledWith(expect.any(Array), "/proj");
    expect(mame.chooseExpectedPath).not.toHaveBeenCalled();
  });

  it("without a workspace, records into the export folder even if a project opened meanwhile", async () => {
    mockActiveWorkspace.mockReturnValue(null);
    const pending = deferredExportAll();
    const run = handleExportAll({ ...PARAMS, projectPath: undefined });
    await vi.waitFor(() => expect(mockSendRequest).toHaveBeenCalledWith("export_all", expect.anything()));
    mockActiveWorkspace.mockReturnValue("/other");
    pending.finish(RESULT);
    await run;

    expect(mockEnsure).toHaveBeenCalledWith("/proj/design/run/run_echo.csv");
    expect(mockRegister).toHaveBeenCalledWith(expect.any(Array), "/proj/design/run");
  });
});

describe("Export All holds the export flag", () => {
  it("raises the flag while the RPC runs and drops it after", async () => {
    const pending = deferredExportAll();
    const run = handleExportAll(PARAMS);
    await vi.waitFor(() => expect(mockSendRequest).toHaveBeenCalledWith("export_all", expect.anything()));
    expect(setState).toHaveBeenLastCalledWith({ isExporting: true });
    pending.finish(RESULT);
    await run;
    expect(setState).toHaveBeenLastCalledWith({ isExporting: false });
  });

  it("drops the flag when the RPC fails", async () => {
    mockSendRequest.mockRejectedValue(new Error("disk full"));
    await handleExportAll(PARAMS);
    expect(setState).toHaveBeenLastCalledWith({ isExporting: false });
  });

  it("an overlapping benchmark export cannot release it", async () => {
    const pending = deferredExportAll();
    const run = handleExportAll(PARAMS);
    await vi.waitFor(() => expect(mockSendRequest).toHaveBeenCalledWith("export_all", expect.anything()));
    mockSave.mockResolvedValue("/tmp/benchmark.csv");
    await handleExportBenchmarkCsv({});
    expect(setState).toHaveBeenLastCalledWith({ isExporting: true });
    pending.finish(RESULT);
    await run;
    expect(setState).toHaveBeenLastCalledWith({ isExporting: false });
  });
});
