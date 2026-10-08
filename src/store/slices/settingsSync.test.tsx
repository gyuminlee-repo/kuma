/**
 * Theme and offline mode each have one setter that writes the settings bundle.
 *
 * Before: the menu theme submenu wrote localStorage only, so the next launch
 * restored preferences.json and undid the change (item 5). Every `useTheme()`
 * call kept its own `useState`, so the radio in one menu disagreed with the
 * other after a change (item 10). The About dialog's offline toggle flipped the
 * in-memory flag without touching `network.offline_mode`, so a restart turned
 * offline mode off again and external calls resumed (item 6).
 */
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/ipc-kuro", () => ({
  sendRequest: vi.fn(async (method: string) => {
    if (method === "settings_load") {
      return {
        settings: {
          language: "en",
          theme: "light",
          default_workspace_folder: null,
          network: {
            offline_mode: false,
            consent_uniprot: true,
            consent_blast: true,
            consent_alphafold: true,
            consent_interpro: true,
            consent_esmfold: true,
            contact_email: "",
          },
        },
        effective_contact_email: "env@lab.org",
        contact_email_source: "env",
      };
    }
    return { ok: true, path: "/tmp/preferences.json" };
  }),
  setProgressHandler: vi.fn(),
  isSidecarRunning: () => false,
}));

vi.mock("@tauri-apps/api/path", () => ({
  resolveResource: vi.fn(async () => { throw new Error("no bundled resources in tests"); }),
}));
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(async () => null),
}));

import { useAppStore } from "../appStore";
import { useTheme } from "../../components/ui/ThemeToggle";
import { SharedAboutDialog } from "../../components/layout/SharedAboutDialog";
import { SettingsDialog } from "../../components/layout/SettingsDialog";

beforeEach(async () => {
  localStorage.clear();
  await act(async () => {
    await useAppStore.getState().loadSettings();
  });
});

describe("theme has one source and one setter", () => {
  it("a theme picked through useTheme lands in the settings bundle", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("dark"));
    expect(useAppStore.getState().settings?.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("every useTheme instance shows the same checked value", () => {
    const menuA = renderHook(() => useTheme());
    const menuB = renderHook(() => useTheme());
    act(() => menuA.result.current.setTheme("dark"));
    expect(menuB.result.current.theme).toBe("dark");
  });

  it("loading settings updates the checked value without a save", async () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    expect(useAppStore.getState().isDirty).toBe(false);
  });
});

describe("About dialog offline toggle", () => {
  it("writes network.offline_mode like the Settings dialog", () => {
    render(<SharedAboutDialog open onOpenChange={() => {}} kind="kuro" />);
    fireEvent.click(screen.getByRole("checkbox", { name: /offline/i }));
    expect(useAppStore.getState().offlineMode).toBe(true);
    expect(useAppStore.getState().settings?.network?.offline_mode).toBe(true);
  });
});

describe("EBI contact email source", () => {
  it("keeps the address and source settings_load reported", () => {
    expect(useAppStore.getState().contactEmailResolution).toEqual({
      email: "env@lab.org",
      source: "env",
    });
  });
});

describe("Settings dialog names where the EBI address comes from", () => {
  it("says the environment variable overrides the empty field", () => {
    render(<SettingsDialog open onOpenChange={() => {}} scope="kuro" />);
    const tab = screen.getByRole("tab", { name: /network/i });
    fireEvent.mouseDown(tab);
    fireEvent.click(tab);
    const note = screen.getByTestId("settings-contact-email-source");
    expect(note.textContent).toContain("env@lab.org");
    expect(note.textContent).toContain("KURO_CONTACT_EMAIL");
  });
});
