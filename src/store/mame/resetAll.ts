import { useMameAppStore } from "./mameAppStore";
import { clearWorkspace, getActiveWorkspace } from "@/lib/workspace";

export async function resetMameAll(): Promise<void> {
  const state = useMameAppStore.getState();
  state.resetInput();
  state.resetAnalysis();
  state.resetExport();
  state.resetPhase();
  if (getActiveWorkspace()) {
    try {
      await clearWorkspace("mame");
    } catch {
      // do not surface manifest failures
    }
  }
}
