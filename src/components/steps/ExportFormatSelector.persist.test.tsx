/**
 * The export form's own fields (export name, forward and reverse plate names,
 * amount, vector maps) are project state. They used to live in component
 * state, so leaving step 6 and coming back, or reopening the project, cleared
 * them. They now live in the store and travel through the KURO autosave
 * snapshot.
 */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ipc-kuro", () => ({
  sendRequest: vi.fn(),
  setProgressHandler: vi.fn(),
  cancelAndRespawn: vi.fn(),
}));
vi.mock("@/state/projectContext", () => ({
  useKumaProject: vi.fn().mockReturnValue({ project_id: "test-proj" }),
}));

import { ExportFormatSelector } from "./ExportFormatSelector";
import { useAppStore } from "@/store/appStore";

function field<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`no element #${id}`);
  return el as T;
}

afterEach(() => {
  cleanup();
  useAppStore.getState().resetAll();
});

describe("ExportFormatSelector fields survive a remount", () => {
  it("keeps name, plate names, amount and vector maps after unmount and remount", () => {
    const first = render(<ExportFormatSelector />);
    fireEvent.change(field<HTMLInputElement>("project-name"), { target: { value: "IspS_R2" } });
    fireEvent.change(field<HTMLInputElement>("fwd-plate"), { target: { value: "FWD_1" } });
    fireEvent.change(field<HTMLInputElement>("rvs-plate"), { target: { value: "REV_1" } });
    fireEvent.change(field<HTMLSelectElement>("amount"), { target: { value: "0.2" } });
    fireEvent.click(field<HTMLInputElement>("export-vectormaps"));
    first.unmount();

    render(<ExportFormatSelector />);
    expect(field<HTMLInputElement>("project-name").value).toBe("IspS_R2");
    expect(field<HTMLInputElement>("fwd-plate").value).toBe("FWD_1");
    expect(field<HTMLInputElement>("rvs-plate").value).toBe("REV_1");
    expect(field<HTMLSelectElement>("amount").value).toBe("0.2");
    expect(field<HTMLInputElement>("export-vectormaps").checked).toBe(true);
  });

  it("clears the fields on Clear All", () => {
    render(<ExportFormatSelector />);
    fireEvent.change(field<HTMLInputElement>("project-name"), { target: { value: "IspS_R2" } });
    fireEvent.change(field<HTMLInputElement>("fwd-plate"), { target: { value: "FWD_1" } });
    cleanup();

    useAppStore.getState().resetAll();

    render(<ExportFormatSelector />);
    expect(field<HTMLInputElement>("project-name").value).toBe("");
    expect(field<HTMLInputElement>("fwd-plate").value).toBe("");
  });
});
