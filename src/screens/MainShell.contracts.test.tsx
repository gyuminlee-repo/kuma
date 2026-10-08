import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import i18next from "i18next";

const native = vi.hoisted(() => ({
  files: new Map<string, string>(),
  failWrite: false,
  write: vi.fn<(path: string, text: string) => Promise<void>>(),
  documentDir: vi.fn<() => Promise<string>>(),
  open: vi.fn<() => Promise<string | null>>(),
  invoke: vi.fn<(command: string, args?: Record<string, unknown>) => Promise<unknown>>(),
  register: vi.fn<() => Promise<() => void>>(),
}));

vi.mock("@tauri-apps/plugin-fs", () => ({
  exists: async (path: string) => native.files.has(path),
  mkdir: async () => {},
  writeTextFile: native.write,
  readTextFile: async (path: string) => {
    const value = native.files.get(path);
    if (value === undefined) throw new Error("ENOENT audit boundary");
    return value;
  },
  rename: async (from: string, to: string) => {
    const value = native.files.get(from);
    if (value === undefined) throw new Error("ENOENT rename audit boundary");
    native.files.set(to, value);
    native.files.delete(from);
  },
  remove: async (path: string) => { native.files.delete(path); },
  readDir: async () => [],
  stat: async () => ({ size: 0, mtime: new Date(0) }),
}));
vi.mock("@tauri-apps/api/path", () => ({
  documentDir: native.documentDir,
  appDataDir: async () => "/audit/app-data",
  join: async (...parts: string[]) => parts.join("/"),
  resolve: async (...parts: string[]) => parts.join("/"),
  isAbsolute: async (path: string) => path.startsWith("/"),
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: native.invoke }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: native.open }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    onCloseRequested: native.register,
    close: async () => {},
    destroy: async () => {},
  }),
}));
vi.mock("@/screens/KuroTab", () => ({ KuroTab: () => null }));
vi.mock("@/screens/MameTab", () => ({ MameTab: () => null }));

import { MainShell } from "@/screens/MainShell";
import { Onboarding } from "@/screens/Onboarding";
import { ProjectProvider } from "@/state/projectContext";
import { initI18n } from "@/lib/i18n";
import { _resetStateForTest, flushAutosave, isHydrating, onAutosaveEvent, scheduleAutosave } from "@/lib/autosave";
import { useAppStore } from "@/store/appStore";

function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("Promise not initialized"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

const target = { projectPath: "/audit/frontend-contracts", scratch: false };
const project = { path: target.projectPath, name: "Boundary audit", scratch: false };

async function mountShell() {
  const view = render(<ProjectProvider value={project}><MainShell /></ProjectProvider>);
  await waitFor(() => expect(isHydrating()).toBe(false));
  await waitFor(() => expect(screen.queryByTestId("hydration-blocker")).toBeNull());
  native.write.mockClear();
  return view;
}

async function save(fail: boolean) {
  native.failWrite = fail;
  await act(async () => {
    scheduleAutosave(target, "kuro", () => ({ schema: 5, saved_at: new Date().toISOString(), kuma_version: "audit" }));
    if (fail) await expect(flushAutosave(target, "kuro")).rejects.toThrow("EACCES audit write");
    else await flushAutosave(target, "kuro");
  });
}

beforeEach(async () => {
  vi.clearAllMocks();
  native.files.clear();
  native.failWrite = false;
  native.register.mockResolvedValue(vi.fn());
  native.documentDir.mockResolvedValue("/audit/Documents");
  native.open.mockResolvedValue("/audit/chosen");
  native.invoke.mockImplementation(async (command, args) => {
    if (command === "set_projects_root_cmd") return { projects_root: args?.path, recent_projects: [] };
    if (command === "sidecar_is_running") return false;
    return {};
  });
  native.write.mockImplementation(async (path, text) => {
    if (native.failWrite) throw new Error("EACCES audit write");
    native.files.set(path, text);
  });
  localStorage.clear();
  localStorage.setItem("kuma:autosave-intro-shown", "1");
  _resetStateForTest();
  await initI18n("en");
});

afterEach(() => {
  cleanup();
  _resetStateForTest();
  vi.useRealTimers();
});

describe("FC-01/02/03 real MainShell, hooks and autosave; isolated tab bodies", () => {
  it("CONTROL persists an edited store value and displays successful autosave", async () => {
    await mountShell();
    await act(async () => {
      useAppStore.setState({ mutationText: "A42V" });
      await flushAutosave(target, "kuro");
    });
    expect(native.write).toHaveBeenCalled();
    expect(native.files.get(`${target.projectPath}/.autosave/kuro.json`)).toContain("A42V");
    expect(screen.getByText(i18next.t("mainShell.autosaveSavedJustNow"))).toBeTruthy();
  });

  it("FC-01 Retry writes the failed snapshot without another edit", async () => {
    await mountShell();
    await save(true);
    expect(native.write).toHaveBeenCalledTimes(1);
    expect(screen.getByText(i18next.t("mainShell.autosaveFailed"))).toBeTruthy();
    native.failWrite = false;
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: i18next.t("mainShell.autosaveRetryAriaLabel") }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    expect(native.write).toHaveBeenCalledTimes(2);
    expect(native.files.get(`${target.projectPath}/.autosave/kuro.json`)).toContain('"kuma_version": "audit"');
    expect(screen.queryByText(i18next.t("mainShell.autosaveFailed"))).toBeNull();
    expect(screen.getByText(i18next.t("mainShell.autosaveSavedJustNow"))).toBeTruthy();

  });

  it("FC-02 CONTROL unregisters when registration resolves before unmount", async () => {
    const unregister = vi.fn();
    native.register.mockResolvedValue(unregister);
    const view = await mountShell();
    view.unmount();
    expect(unregister).toHaveBeenCalledTimes(1);
  });

  it("FC-02 unregisters a late registration after unmount", async () => {
    const registration = deferred<() => void>();
    const unregister = vi.fn();
    native.register.mockReturnValue(registration.promise);
    const view = await mountShell();
    expect(native.register).toHaveBeenCalledTimes(1);
    view.unmount();
    await act(async () => { registration.resolve(unregister); await registration.promise; });
    expect(unregister).toHaveBeenCalledTimes(1);

  });

  it("FC-03 warns after three actual failed writes", async () => {
    await mountShell();
    const events: string[] = [];
    const off = onAutosaveEvent((event) => events.push(event.type));
    for (let i = 0; i < 3; i++) await save(true);
    off();
    expect(events).toEqual(["saving", "error", "saving", "error", "saving", "error"]);
    expect(native.write).toHaveBeenCalledTimes(3);
    expect(screen.getByText(i18next.t("mainShell.autosaveFailed"))).toBeTruthy();
    expect(screen.getByText(i18next.t("mainShell.autosaveFailedStreak"))).toBeTruthy();

    await save(false);
    expect(screen.getByText(i18next.t("mainShell.autosaveSavedJustNow"))).toBeTruthy();
  });
});

it("FC-01/03 repeated Retry failures emit errors and warn, then recover", async () => {
  await mountShell();
  await save(true);
  for (let attempt = 2; attempt <= 3; attempt++) {
    fireEvent.click(screen.getByRole("button", { name: i18next.t("mainShell.autosaveRetryAriaLabel") }));
    await waitFor(() => expect(native.write).toHaveBeenCalledTimes(attempt));
    await waitFor(() => expect(screen.getByText(i18next.t("mainShell.autosaveFailed"))).toBeTruthy());
  }
  expect(screen.getByText(i18next.t("mainShell.autosaveFailedStreak"))).toBeTruthy();
  native.failWrite = false;
  fireEvent.click(screen.getByRole("button", { name: i18next.t("mainShell.autosaveRetryAriaLabel") }));
  await waitFor(() => expect(screen.getByText(i18next.t("mainShell.autosaveSavedJustNow"))).toBeTruthy());
  expect(native.write).toHaveBeenCalledTimes(4);
});

describe("FC-04 real Onboarding and project invoke wrapper", () => {
  it("CONTROL resolves the default and submits the chosen folder", async () => {
    const done = vi.fn();
    render(<Onboarding onDone={done} />);
    await waitFor(() => expect(screen.getByLabelText("Projects folder")).toHaveValue("/audit/Documents/kuma"));
    fireEvent.click(screen.getByRole("button", { name: "Choose folder" }));
    await waitFor(() => expect(screen.getByLabelText("Projects folder")).toHaveValue("/audit/chosen"));
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(done).toHaveBeenCalledWith({ projects_root: "/audit/chosen", recent_projects: [] }));
    expect(native.invoke).toHaveBeenCalledWith("set_projects_root_cmd", { path: "/audit/chosen" });
  });

  it("FC-04 retains the folder picked before default resolution", async () => {
    const documents = deferred<string>();
    native.documentDir.mockReturnValue(documents.promise);
    render(<Onboarding onDone={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Choose folder" }));
    await waitFor(() => expect(screen.getByLabelText("Projects folder")).toHaveValue("/audit/chosen"));
    expect(screen.getByRole("button", { name: "Done" })).toBeDisabled();
    await act(async () => { documents.resolve("/audit/Documents"); await documents.promise; });
    expect(screen.getByLabelText("Projects folder")).toHaveValue("/audit/chosen");

  });
});
