import { useMameAppStore } from "./mameAppStore";
import { clearWorkspace, getActiveWorkspace } from "@/lib/workspace";

export async function resetMameAll(): Promise<void> {
  const state = useMameAppStore.getState();
  state.resetInput();
  state.resetAnalysis();
  state.resetExport();
  state.resetPhase();
  // Clear component-local persisted form state (BarcodeSetupPanel) so filename
  // labels and entered values do not survive a Clear. Bumping resetEpoch
  // notifies subscribed components to reinitialise their useState as well.
  try {
    window.localStorage.removeItem("kuma:mame:barcodeSetup");
  } catch {
    // localStorage may be unavailable (SSR, sandbox); ignore.
  }
  state.bumpResetEpoch();
  if (getActiveWorkspace()) {
    try {
      await clearWorkspace("mame");
    } catch {
      // do not surface manifest failures
    }
  }
}
