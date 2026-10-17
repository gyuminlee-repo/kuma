import { BUILD_EVOLVEPRO_STORAGE_KEY } from "@/lib/mame/buildEvolveproFormStorage";
import { clearBarcodeSetupForm } from "@/lib/mame/barcodeSetupFormStorage";
import i18next from "i18next";
import { toast } from "sonner";
import { cancelAndRespawn, sendRequest, isSidecarRunning } from "@/lib/ipc-mame";
import { formatError } from "@/lib/utils";
import { useRoundStore } from "@/store/round/roundSlice";
import { useMameAppStore } from "./mameAppStore";
import { clearWorkspace, getActiveWorkspace } from "@/lib/workspace";

/**
 * @param options.preserveWorkspaceArtifacts Set by project hydration, which
 *   resets the stores before restoring a project. It is not the operator
 *   clearing anything, so the project's manifest artifacts and its saved
 *   Step 1 form are kept. Clear All passes nothing and removes both.
 */
export async function resetMameAll(options?: { preserveWorkspaceArtifacts?: boolean }): Promise<void> {
  const state = useMameAppStore.getState();
  // Read before resetInput clears it.
  const formProjectPath = state.formStoragePath;
  // A reset ends the running analysis instead of letting its reply land in the
  // cleared (or next project's) workspace. resetInput retires the run on the
  // frontend; the backend run is killed below and the user is told why.
  const analysisWasRunning = state.isAnalyzing;
  state.resetInput();
  state.resetAnalysis();
  state.resetExport();
  state.resetPhase();
  useRoundStore.setState({ rounds: [], active_round_id: null });
  // Clear All forgets the Step 1 form of this project. Opening a project does
  // not: that reset used to delete the (then global) form on every open, so a
  // reopened project always came back with an empty Barcode Setup. Bumping
  // resetEpoch makes the mounted panel reload from storage either way.
  if (!options?.preserveWorkspaceArtifacts) {
    clearBarcodeSetupForm(formProjectPath);
  }
  try {
    window.localStorage.removeItem(BUILD_EVOLVEPRO_STORAGE_KEY);
  } catch {
    // localStorage may be unavailable (SSR, sandbox); ignore.
  }
  state.bumpResetEpoch();
  if (analysisWasRunning) {
    try {
      await cancelAndRespawn();
      toast.info(i18next.t("toast.analysisCancelledByReset"));
    } catch (err) {
      toast.error(i18next.t("toast.analysisCancelFailed", { message: formatError(err) }));
    }
  }
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
