import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ProgressNotification } from "@/lib/ipc-mame/types";

// Capture the progress handler the hook registers so we can drive it directly.
let captured: ((p: ProgressNotification) => void) | null = null;

vi.mock("@/lib/ipc-mame", () => ({
  spawnSidecar: vi.fn(() => Promise.resolve()),
  setProgressHandler: vi.fn((handler: ((p: ProgressNotification) => void) | null) => {
    captured = handler;
  }),
}));

// ipc-kuro is touched transitively via appStore's progress handler; stub it so
// the test never reaches the Tauri bridge.
vi.mock("@/lib/ipc-kuro", () => ({
  setProgressHandler: vi.fn(),
}));

import { useMameSidecar } from "./useMameSidecar";
import { useMameAppStore } from "@/store/mame/mameAppStore";

function emit(p: ProgressNotification) {
  if (!captured) throw new Error("progress handler not registered");
  captured(p);
}

describe("useMameSidecar progress subscription", () => {
  beforeEach(() => {
    captured = null;
    useMameAppStore.setState({
      analyzePhase: null,
      analyzeStage: null,
      analyzeProgress: 0,
      isAnalyzing: true,
      inputMode: "raw_run",
    });
  });

  it("drives analyzePhase from the backend stage and passes the unified value through without rescale", () => {
    renderHook(() => useMameSidecar());
    expect(captured).toBeTypeOf("function");

    // Folded raw-run: backend already emits unified 0..100 (demux 0..50).
    // stage='demux' must flip analyzePhase and the value must NOT be rescaled.
    emit({ value: 30, message: "Demuxing reads (3/10)", stage: "demux" });
    expect(useMameAppStore.getState().analyzePhase).toBe("demux");
    expect(useMameAppStore.getState().analyzeStage).toBe("demux");
    expect(useMameAppStore.getState().analyzeProgress).toBe(30);

    // stage='analyze' (50..100 band) advances the phase, still no rescale.
    emit({ value: 75, message: "Analyzing variants", stage: "analyze" });
    expect(useMameAppStore.getState().analyzePhase).toBe("analyze");
    expect(useMameAppStore.getState().analyzeStage).toBe("analyze");
    expect(useMameAppStore.getState().analyzeProgress).toBe(75);
  });

  it("keeps phase-based scaling on the legacy/consensus path when no stage is present", () => {
    useMameAppStore.setState({ inputMode: "consensus", analyzePhase: null, analyzeStage: null });
    renderHook(() => useMameSidecar());

    // No stage key -> legacy path; consensus (non-raw) passes value straight
    // through and leaves stage/phase untouched.
    emit({ value: 40, message: "Analyzing" });
    expect(useMameAppStore.getState().analyzeProgress).toBe(40);
    expect(useMameAppStore.getState().analyzeStage).toBeNull();
    expect(useMameAppStore.getState().analyzePhase).toBeNull();
  });
});
