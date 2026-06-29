import { BUILD_EVOLVEPRO_STORAGE_KEY } from "@/lib/mame/buildEvolveproFormStorage";
import { sendRequest, isSidecarRunning } from "@/lib/ipc-mame";
import { useRoundStore } from "@/store/round/roundSlice";
import { useMameAppStore } from "./mameAppStore";
import { clearWorkspace, getActiveWorkspace } from "@/lib/workspace";

export async function resetMameAll(options?: { preserveWorkspaceArtifacts?: boolean }): Promise<void> {
  const state = useMameAppStore.getState();
  state.resetInput();
  state.resetAnalysis();
  state.resetExport();
  state.resetPhase();
  useRoundStore.setState({ rounds: [], active_round_id: null });
  // Clear component-local persisted form state (BarcodeSetupPanel) so filename
  // labels and entered values do not survive a Clear. Bumping resetEpoch
  // notifies subscribed components to reinitialise their useState as well.
  try {
    window.localStorage.removeItem("kuma:mame:barcodeSetup");
    window.localStorage.removeItem(BUILD_EVOLVEPRO_STORAGE_KEY);
  } catch {
    // localStorage may be unavailable (SSR, sandbox); ignore.
  }
  state.bumpResetEpoch();
  if (isSidecarRunning()) {
    try {
      await sendRequest("reset_state", {}, 10_000);
    } catch {
      // A reset must leave the UI clean even if the sidecar is not available.
    }
  }
  if (!options?.preserveWorkspaceArtifacts && getActiveWorkspace()) {
    try {
      await clearWorkspace("mame");
    } catch {
      // do not surface manifest failures
    }
  }
}
