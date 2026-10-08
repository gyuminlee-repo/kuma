/**
 * A KURO Export All in a project hands its plate map to MAME in the same
 * session (item 7 of the 2026-09-29 input audit).
 *
 * `<prefix>_platemap.xlsx` carries the `expected_mutations` sheet MAME reads
 * as its expected list. Before, MAME only picked a KURO workbook up while a
 * project was being opened, and then only the retired `sdm_primer_xlsx`, so an
 * export made during the session never reached Step 2. The handoff fills an
 * empty expected input only, never replaces one the operator chose, and runs
 * only in a project session: a scratch session has no project workspace at the
 * start of the export (lane A empties it there).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockOpen = vi.hoisted(() => vi.fn());
const mockSendRequest = vi.hoisted(() => vi.fn());
const mockActiveWorkspace = vi.hoisted(() => vi.fn<() => string | null>());
const mame = vi.hoisted(() => ({
  expectedPath: "",
  chooseExpectedPath: vi.fn(),
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mockOpen, save: vi.fn() }));
vi.mock("@tauri-apps/plugin-fs", () => ({ mkdir: vi.fn(async () => undefined) }));
vi.mock("../../lib/ipc-kuro", () => ({ sendRequest: mockSendRequest }));
vi.mock("../../lib/workspace", () => ({
  registerArtifacts: vi.fn(async () => undefined),
  ensureWorkspaceFromExportPath: vi.fn(async () => undefined),
  getActiveWorkspace: mockActiveWorkspace,
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
    }),
    setState: vi.fn(),
  },
}));
vi.mock("../../store/mame/mameAppStore", () => ({
  useMameAppStore: { getState: () => mame },
}));

import { handleExportAll } from "./export-handlers";

const PARAMS = {
  amount: "0.05" as const,
  echoTransferVol: 1,
  janusTransferVol: 1,
  bom: false,
  projectPath: "/proj",
};

const PLATEMAP = "/proj/design/run_20260929/run_20260929_platemap.xlsx";

beforeEach(() => {
  vi.clearAllMocks();
  mame.expectedPath = "";
  mockOpen.mockResolvedValue("/proj/design");
  mockActiveWorkspace.mockReturnValue("/proj");
  mockSendRequest.mockResolvedValue({
    success: ["run_20260929_echo.csv", "run_20260929_platemap.xlsx"],
    failed: [],
    output_dir: "/proj/design/run_20260929",
  });
});

describe("Export All plate map reaches MAME", () => {
  it("fills an empty MAME expected input with the plate map", async () => {
    await handleExportAll(PARAMS);
    expect(mame.chooseExpectedPath).toHaveBeenCalledWith(PLATEMAP);
  });

  it("leaves an expected workbook the operator chose alone", async () => {
    mame.expectedPath = "/proj/other.xlsx";
    await handleExportAll(PARAMS);
    expect(mame.chooseExpectedPath).not.toHaveBeenCalled();
  });

  it("does nothing in a scratch session", async () => {
    mockActiveWorkspace.mockReturnValue(null);
    await handleExportAll({ ...PARAMS, projectPath: "/appdata/scratch" });
    expect(mame.chooseExpectedPath).not.toHaveBeenCalled();
  });

  it("does nothing when the active workspace is another project", async () => {
    mockActiveWorkspace.mockReturnValue("/previous-project");
    await handleExportAll({ ...PARAMS, projectPath: "/appdata/scratch" });
    expect(mame.chooseExpectedPath).not.toHaveBeenCalled();
  });

  it("does nothing when the plate map was not written", async () => {
    mockSendRequest.mockResolvedValue({
      success: ["run_20260929_echo.csv"],
      failed: [{ path: "run_20260929_platemap.xlsx", reason: "disk full" }],
      output_dir: "/proj/design/run_20260929",
    });
    await handleExportAll(PARAMS);
    expect(mame.chooseExpectedPath).not.toHaveBeenCalled();
  });
});
