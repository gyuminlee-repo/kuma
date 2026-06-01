import { create } from "zustand";
import {
  condaDetect,
  condaDetectEnv,
  condaVerifyEnv,
  condaInstallRemovePrefix,
} from "@/lib/ipc-evolvepro";
// Note: condaCreateEnv / condaCancelCreateEnv / setCondaCreate*Handler and the
// install-miniforge Rust commands (condaInstallMiniforge / condaInstallCancel /
// subscribeCondaInstallProgress) are no longer imported here. Both the
// create-env and install-conda flows run through the embedded PTY via
// sentinels (see CondaSetupWizard.tsx). The Rust commands remain wired up in
// @/lib/ipc for Step 4 deprecation. condaInstallRemovePrefix stays as the
// safety path for the [Remove and reinstall] button.
import type { CondaStatus, EnvStatus } from "@/types/models.evolvepro";

export type CreateEnvStepId =
  | "CONDA_CREATE"
  | "PIP_INSTALL"
  | "EVOLVEPRO_INSTALL"
  | "VERIFY";

export type InstallCondaStepId =
  | "PREFIX_CHECK"
  | "DL_MINIFORGE"
  | "INSTALL_MINIFORGE";

export type CondaWizardStage =
  | "idle"
  | "detecting"
  | "ready"
  | "needs_conda"
  | "needs_env"
  | "needs_repair"
  | "installing_conda"
  | "creating_env"
  | "cancelling"
  | "verifying"
  | "cancelling_install"
  | "done"
  | "error"
  | "prefix_conflict";

export interface CondaSetupState {
  stage: CondaWizardStage;
  condaStatus: CondaStatus | null;
  envStatus: EnvStatus | null;
  /** Current PTY-routed create-env step (sentinel-tracked). */
  currentStep: CreateEnvStepId | null;
  /** Current PTY-routed install-conda step (sentinel-tracked). */
  currentInstallStep: InstallCondaStepId | null;
  error: string | null;
  installError: string | null;
  /** Tracks the last stage that was actively attempted, used by retry(). */
  lastAttemptedStage: CondaWizardStage | null;

  open: boolean;
  setOpen: (open: boolean) => void;

  detect: () => Promise<void>;
  verify: () => Promise<void>;
  /**
   * PTY-routed install-conda lifecycle hooks. Dispatch of the actual download
   * and install commands lives in CondaSetupWizard (it owns the SetupTerminal
   * ref); the store only tracks state transitions driven by sentinels.
   */
  startInstallConda: () => void;
  markInstallStep: (stepId: InstallCondaStepId) => void;
  finishInstallSuccess: () => void;
  finishInstallFail: (stepId: InstallCondaStepId, exitCode?: number) => void;
  startCancelInstall: () => void;
  finishCancelInstall: () => void;
  setPrefixConflict: (conflict: boolean) => void;
  /**
   * PTY-routed create-env lifecycle hooks. Actual command dispatch lives in
   * CondaSetupWizard (it owns the SetupTerminal ref); the store only tracks
   * state transitions driven by sentinels.
   */
  startCreateEnv: () => void;
  markCreateEnvStep: (stepId: CreateEnvStepId) => void;
  finishCreateEnvSuccess: () => void;
  finishCreateEnvFail: (stepId: CreateEnvStepId, exitCode?: number) => void;
  startCancelCreateEnv: () => void;
  finishCancelCreateEnv: () => void;
  /**
   * Remove the existing broken miniforge prefix and return to needs_conda so
   * the user can click [Install] again. The Rust side validates the path.
   */
  removeExistingMiniforge: () => Promise<void>;
  /**
   * Retry only the last-failed stage instead of resetting all state.
   * Falls back to a full reset if the last stage is unknown.
   */
  retry: () => Promise<void>;
  runAuto: () => Promise<void>;
  reset: () => void;
}

const INITIAL_STATE = {
  stage: "idle" as CondaWizardStage,
  condaStatus: null,
  envStatus: null,
  currentStep: null as CreateEnvStepId | null,
  currentInstallStep: null as InstallCondaStepId | null,
  error: null,
  installError: null,
  open: false,
  lastAttemptedStage: null as CondaWizardStage | null,
};

export const useCondaSetupStore = create<CondaSetupState>()((set, get) => ({
  ...INITIAL_STATE,

  setOpen: (open) => set({ open }),

  detect: async () => {
    set({ stage: "detecting", error: null, lastAttemptedStage: "detecting" });
    try {
      const condaStatus = await condaDetect();
      set({ condaStatus });

      if (!condaStatus.installed) {
        set({ stage: "needs_conda" });
        return;
      }

      const envStatus = await condaDetectEnv("evolvepro");
      set({ envStatus });

      if (!envStatus.exists) {
        set({ stage: "needs_env" });
        return;
      }

      const condaExe = condaStatus.conda_exe ?? "conda";
      const verifyResult = await condaVerifyEnv("evolvepro", condaExe);
      if (verifyResult.ok) {
        set({ stage: "done" });
      } else {
        set({ stage: "needs_repair" });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ stage: "error", error: message });
    }
  },

  startInstallConda: () => {
    set({
      stage: "installing_conda",
      error: null,
      installError: null,
      currentInstallStep: "PREFIX_CHECK",
      lastAttemptedStage: "installing_conda",
    });
  },

  markInstallStep: (stepId) => {
    set({ currentInstallStep: stepId });
  },

  finishInstallSuccess: () => {
    set((state) => ({
      stage: "needs_env",
      currentInstallStep: null,
      installError: null,
      // Mark conda as installed so downstream UI (progress steps) updates.
      condaStatus: state.condaStatus
        ? { ...state.condaStatus, installed: true }
        : { installed: true, conda_exe: null, version: null },
    }));
  },

  finishInstallFail: (stepId, exitCode) => {
    const detail = exitCode != null ? ` (exit ${exitCode})` : "";
    const msg = `Install step ${stepId} failed${detail}.`;
    set({
      stage: "error",
      currentInstallStep: null,
      installError: msg,
      error: msg,
    });
  },

  startCancelInstall: () => {
    set({ stage: "cancelling_install", error: null });
  },

  finishCancelInstall: () => {
    set({
      stage: "needs_conda",
      currentInstallStep: null,
      installError: null,
      error: null,
    });
  },

  setPrefixConflict: (conflict) => {
    if (conflict) {
      set({ stage: "prefix_conflict", currentInstallStep: null });
    }
  },

  startCreateEnv: () => {
    set({
      stage: "creating_env",
      error: null,
      currentStep: "CONDA_CREATE",
      lastAttemptedStage: "creating_env",
    });
  },

  markCreateEnvStep: (stepId) => {
    set({ currentStep: stepId });
  },

  finishCreateEnvSuccess: () => {
    set({ stage: "done", currentStep: null, error: null });
  },

  finishCreateEnvFail: (stepId, exitCode) => {
    const detail =
      exitCode != null ? ` (exit ${exitCode})` : "";
    set({
      stage: "error",
      currentStep: null,
      error: `Step ${stepId} failed${detail}.`,
    });
  },

  startCancelCreateEnv: () => {
    set({ stage: "cancelling", error: null });
  },

  finishCancelCreateEnv: () => {
    set({ stage: "needs_env", currentStep: null, error: null });
  },

  runAuto: async () => {
    // After Step 2 migration the create-env flow is driven by the wizard's
    // SetupTerminal (PTY + sentinels), so runAuto only handles detection and
    // verification. When the env is missing or broken, it leaves the stage at
    // needs_env / needs_repair so the user (or wizard) can dispatch the
    // create-env PTY pipeline.
    set({ stage: "detecting", error: null, lastAttemptedStage: "detecting" });
    try {
      const condaStatus = await condaDetect();
      set({ condaStatus });

      if (!condaStatus.installed) {
        set({ stage: "needs_conda" });
        return;
      }

      const envStatus = await condaDetectEnv("evolvepro");
      set({ envStatus });

      const missing = Object.entries(envStatus.packages ?? {})
        .filter(([, version]) => version === null)
        .map(([name]) => name);

      if (!envStatus.exists) {
        set({ stage: "needs_env" });
        return;
      }

      if (missing.length > 0) {
        set({ stage: "needs_repair" });
        return;
      }

      const condaExe = condaStatus.conda_exe ?? "conda";
      set({ stage: "verifying" });
      const verifyResult = await condaVerifyEnv("evolvepro", condaExe);
      if (verifyResult.ok) {
        set({ stage: "done" });
      } else {
        set({
          stage: "needs_repair",
          error: verifyResult.error ?? "Verification failed.",
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ stage: "error", error: message });
    }
  },

  verify: async () => {
    set({ stage: "verifying", error: null, lastAttemptedStage: "verifying" });
    const condaStatus = get().condaStatus;
    const condaExe = condaStatus?.conda_exe ?? "conda";
    try {
      const verifyResult = await condaVerifyEnv("evolvepro", condaExe);
      if (verifyResult.ok) {
        set({ stage: "done" });
      } else {
        set({
          stage: "error",
          error: verifyResult.error ?? "Verification failed after env creation.",
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ stage: "error", error: message });
    }
  },

  removeExistingMiniforge: async () => {
    set({ error: null });
    try {
      await condaInstallRemovePrefix();
      // Prefix removed; return to needs_conda so the user can reinstall.
      set({ stage: "needs_conda" });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ stage: "error", error: message });
    }
  },

  retry: async () => {
    const last = get().lastAttemptedStage;
    if (last === "installing_conda") {
      // PTY-routed install retry: surface back to needs_conda so the user
      // clicks [Install] again to re-enter the PTY dispatch flow.
      set({
        stage: "needs_conda",
        error: null,
        installError: null,
        currentInstallStep: null,
      });
    } else if (last === "creating_env") {
      // The create-env flow is now driven by the wizard's PTY dispatch, so
      // returning to needs_env lets the user click [Create Env] to retry.
      set({ stage: "needs_env", error: null, currentStep: null });
    } else if (last === "verifying") {
      await get().verify();
    } else if (last === "detecting") {
      await get().detect();
    } else {
      // Unknown last stage: fall back to full reset.
      get().reset();
    }
  },

  reset: () => set({ ...INITIAL_STATE, open: true }),
}));
