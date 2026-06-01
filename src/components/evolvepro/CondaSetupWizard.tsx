import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, XCircle, AlertTriangle, Circle, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/Spinner";
import { useCondaSetupStore } from "@/store/evolvepro/condaSetupStore";
import { SetupTerminal, type SetupTerminalHandle } from "@/components/evolvepro/SetupTerminal";
import {
  buildCreateEnvCommand,
  buildDownloadCommand,
  buildEnvRemoveCommand,
  buildEvolveProInstallCommand,
  buildInitShellCommand,
  buildInstallCancelCleanupCommand,
  buildPipInstallCommand,
  buildPrefixCheckCommand,
  buildSilentInstallCommand,
  buildVerifyCommand,
  deriveEnvPython,
  detectMiniforgePlatform,
  wrapWithSentinel,
} from "@/lib/condaCommands";

type SetupStatus = "pending" | "active" | "done" | "error";

function StatusIcon({ status }: { status: SetupStatus }) {
  if (status === "done") {
    return <CheckCircle2 className="h-4 w-4 text-green-600" aria-hidden="true" />;
  }
  if (status === "active") {
    return <Loader2 className="h-4 w-4 animate-spin text-blue-600" aria-hidden="true" />;
  }
  if (status === "error") {
    return <XCircle className="h-4 w-4 text-destructive" aria-hidden="true" />;
  }
  return <Circle className="h-4 w-4 text-muted-foreground/60" aria-hidden="true" />;
}

/**
 * Returns an i18n key under `conda.wizard.currentWork.*` describing the
 * in-progress step, or null. The caller resolves it via t().
 */
function summarizeCurrentWorkKey(
  stage: string,
  currentInstallStep: ReturnType<
    typeof useCondaSetupStore.getState
  >["currentInstallStep"],
  currentStep: ReturnType<typeof useCondaSetupStore.getState>["currentStep"],
): string | null {
  if (stage === "detecting") return "conda.wizard.currentWork.detecting";
  if (stage === "installing_conda") {
    if (currentInstallStep === "PREFIX_CHECK")
      return "conda.wizard.currentWork.prefixCheck";
    if (currentInstallStep === "DL_MINIFORGE")
      return "conda.wizard.currentWork.downloadMiniforge";
    if (currentInstallStep === "INSTALL_MINIFORGE")
      return "conda.wizard.currentWork.installMiniforge";
    return "conda.wizard.currentWork.installMiniforge";
  }
  if (stage === "cancelling_install")
    return "conda.wizard.currentWork.cancellingInstall";
  if (stage === "creating_env") {
    if (currentStep === "CONDA_CREATE") return "conda.wizard.currentWork.createConda";
    if (currentStep === "PIP_INSTALL")
      return "conda.wizard.currentWork.pipInstall";
    if (currentStep === "EVOLVEPRO_INSTALL")
      return "conda.wizard.currentWork.evolveproInstall";
    if (currentStep === "VERIFY") return "conda.wizard.currentWork.verify";
    return "conda.wizard.currentWork.preparing";
  }
  if (stage === "cancelling") return "conda.wizard.currentWork.cancelling";
  if (stage === "verifying") return "conda.wizard.currentWork.verifyingFinal";
  if (stage === "done") return "conda.wizard.currentWork.done";
  if (stage === "error") return "conda.wizard.currentWork.error";
  return null;
}

export function CondaSetupWizard() {
  const { t } = useTranslation();
  const termRef = useRef<SetupTerminalHandle | null>(null);
  const [autoRunning, setAutoRunning] = useState(false);
  const [runAutoActive, setRunAutoActive] = useState(false);
  const runAutoActiveRef = useRef(false);
  useEffect(() => {
    runAutoActiveRef.current = runAutoActive;
  }, [runAutoActive]);
  const [initShellRunning, setInitShellRunning] = useState(false);
  const [envResetting, setEnvResetting] = useState(false);
  const [resetConfirming, setResetConfirming] = useState(false);
  // Gates the spinning indicator in the "설정 진행 상황" panel. Only flips ON
  // when the user clicks a button inside the wizard (Start, Run Auto, Install,
  // Create, Reset). Auto-triggered detect on wizard mount keeps it OFF so the
  // progress icons render as static dots until the user explicitly acts.
  const [userInitiatedAction, setUserInitiatedAction] = useState(false);
  // Manual input mode: when ON, the user types y/n themselves in the terminal.
  // When OFF (default), SetupTerminal auto-confirms common conda prompts.
  const [manualMode, setManualMode] = useState(false);
  const {
    open,
    setOpen,
    stage,
    currentStep,
    currentInstallStep,
    envStatus,
    condaStatus,
    error,
    detect,
    startInstallConda,
    markInstallStep,
    finishInstallSuccess,
    finishInstallFail,
    startCancelInstall,
    finishCancelInstall,
    setPrefixConflict,
    startCreateEnv,
    markCreateEnvStep,
    finishCreateEnvSuccess,
    finishCreateEnvFail,
    startCancelCreateEnv,
    finishCancelCreateEnv,
    removeExistingMiniforge,
    retry,
    reset,
  } = useCondaSetupStore();

  const condaExe = condaStatus?.conda_exe ?? "conda";
  const envPython = deriveEnvPython(condaExe);

  // Clear the spinner gate whenever the wizard returns to a wait/terminal stage
  // (idle, needs_*, prefix_conflict, done, error). Active stages (detecting,
  // installing_conda, creating_env, cancelling*, verifying) keep whatever the
  // user set when they triggered the action.
  useEffect(() => {
    if (
      stage === "idle" ||
      stage === "needs_conda" ||
      stage === "needs_env" ||
      stage === "needs_repair" ||
      stage === "prefix_conflict" ||
      stage === "done" ||
      stage === "error"
    ) {
      setUserInitiatedAction(false);
    }
  }, [stage]);

  const handleResetEnv = () => {
    const term = termRef.current;
    if (!term) {
      reset();
      return;
    }
    if (!resetConfirming) {
      // First click arms an inline confirmation. Native window.confirm is
      // blocked inside the Tauri webview ("dialog.confirm not allowed").
      setResetConfirming(true);
      return;
    }
    setResetConfirming(false);
    setEnvResetting(true);
    setUserInitiatedAction(true);
    term.write("[reset] removing evolvepro env...\n");
    term.runCommand(
      wrapWithSentinel(buildEnvRemoveCommand(condaExe), "ENV_RESET"),
    );
  };

  const handleCancelReset = () => setResetConfirming(false);

  const handleRunAuto = async () => {
    if (autoRunning) return;
    setAutoRunning(true);
    setRunAutoActive(true);
    runAutoActiveRef.current = true;
    setUserInitiatedAction(true);
    try {
      await detect();
      const s = useCondaSetupStore.getState();
      if (s.stage === "needs_conda") {
        await new Promise((r) => setTimeout(r, 200));
        handleInstallConda();
      } else if (s.stage === "needs_env" || s.stage === "needs_repair") {
        await new Promise((r) => setTimeout(r, 200));
        handleCreateEnv();
      } else {
        setRunAutoActive(false);
        runAutoActiveRef.current = false;
      }
    } catch (e) {
      termRef.current?.write(`[auto] error: ${e instanceof Error ? e.message : String(e)}\n`);
      setRunAutoActive(false);
      runAutoActiveRef.current = false;
    } finally {
      setAutoRunning(false);
    }
  };

  // Dispatch the install-conda pipeline through the PTY. The chain is:
  // PREFIX_CHECK -> (EXIST | DIRTY | ABSENT) -> DL_MINIFORGE -> INSTALL_MINIFORGE.
  const handleInstallConda = () => {
    const term = termRef.current;
    if (!term) {
      finishInstallFail("PREFIX_CHECK");
      return;
    }
    setUserInitiatedAction(true);
    startInstallConda();
    term.write("[install-conda] checking existing miniforge prefix...\n");
    const plat = detectMiniforgePlatform();
    term.runCommand(buildPrefixCheckCommand(plat));
  };

  const handleCancelInstallConda = () => {
    const term = termRef.current;
    if (!term) return;
    if (!window.confirm(t("conda.wizard.confirmCancelInstall"))) return;
    setUserInitiatedAction(true);
    startCancelInstall();
    term.write("[cancel] sending Ctrl-C and cleaning up partial install...\n");
    term.interrupt();
    // ~300ms for the shell to return to a prompt after SIGINT (matches the
    // create-env cancel timing). Cleanup tries to remove both the installer
    // file and any partial prefix; failures are tolerated.
    window.setTimeout(() => {
      const plat = detectMiniforgePlatform();
      term.runCommand(
        wrapWithSentinel(
          buildInstallCancelCleanupCommand(plat),
          "INSTALL_REMOVE_AFTER_CANCEL",
        ),
      );
    }, 300);
  };

  // Dispatch the create-env pipeline through the PTY. First command kicks
  // off the chain; subsequent steps are enqueued by the sentinel handler.
  const handleCreateEnv = () => {
    const term = termRef.current;
    if (!term) {
      // SetupTerminal mounts together with this component, so this should not
      // happen in normal flow. Surface a clear error rather than silently
      // swallowing the click.
      finishCreateEnvFail("CONDA_CREATE");
      return;
    }
    setUserInitiatedAction(true);
    startCreateEnv();
    term.write("[create-env] starting conda create...\n");
    term.runCommand(
      wrapWithSentinel(buildCreateEnvCommand(condaExe), "CONDA_CREATE"),
    );
  };

  const handleCancelCreateEnv = () => {
    const term = termRef.current;
    if (!term) return;
    if (!window.confirm(t("conda.wizard.confirmCancelCreateEnv"))) return;
    setUserInitiatedAction(true);
    startCancelCreateEnv();
    term.write("[cancel] sending Ctrl-C and cleaning up partial env...\n");
    term.interrupt();
    // Give the shell ~300ms to return to the prompt after SIGINT before the
    // cleanup command is enqueued. Empirically sufficient for both bash and
    // PowerShell; if this proves flaky, switch to an echo-based readiness
    // probe before the remove command.
    window.setTimeout(() => {
      term.runCommand(
        wrapWithSentinel(
          buildEnvRemoveCommand(condaExe),
          "ENV_REMOVE_AFTER_CANCEL",
        ),
      );
    }, 300);
  };

  // Sentinel listener: drives stage transitions for the PTY-routed flows.
  useEffect(() => {
    const term = termRef.current;
    if (!term) return;
    console.debug("[CondaSetupWizard] registering sentinel listener; envPython=", envPython);
    const unsubscribe = term.onSentinel("__EP_", (kind, stepId, exitCode) => {
      console.debug("[CondaSetupWizard] sentinel cb fired", kind, stepId, exitCode);
      if (stepId === "INIT_SHELL") {
        setInitShellRunning(false);
        if (kind === "OK") {
          term.write("[conda init] close and reopen the terminal for changes to take effect\n");
        } else {
          term.write(`[conda init] failed (exit ${exitCode ?? "?"})\n`);
        }
        return;
      }
      // Install-conda flow: prefix probe branches before the download.
      if (stepId === "PREFIX_EXIST") {
        // Existing miniforge3 with a conda binary. Skip download/install and
        // move straight to env creation.
        term.write("[install-conda] existing miniforge detected; skipping install.\n");
        finishInstallSuccess();
        if (runAutoActiveRef.current) {
          setTimeout(() => handleCreateEnv(), 300);
        }
        return;
      }
      if (stepId === "PREFIX_DIRTY") {
        // Directory exists but no conda binary. Defer to the prefix_conflict
        // UI so the user can decide between remove-and-reinstall vs cancel.
        term.write("[install-conda] miniforge3 directory exists without conda; needs user decision.\n");
        setPrefixConflict(true);
        setRunAutoActive(false);
        runAutoActiveRef.current = false;
        return;
      }
      if (stepId === "PREFIX_ABSENT") {
        // Fresh install path.
        markInstallStep("DL_MINIFORGE");
        const plat = detectMiniforgePlatform();
        term.write("[install-conda] downloading installer...\n");
        term.runCommand(
          wrapWithSentinel(buildDownloadCommand(plat), "DL_MINIFORGE"),
        );
        return;
      }
      if (stepId === "DL_MINIFORGE") {
        if (kind === "OK") {
          markInstallStep("INSTALL_MINIFORGE");
          const plat = detectMiniforgePlatform();
          term.write("[install-conda] download complete; running silent installer...\n");
          term.runCommand(
            wrapWithSentinel(
              buildSilentInstallCommand(plat),
              "INSTALL_MINIFORGE",
            ),
          );
        } else {
          finishInstallFail("DL_MINIFORGE", exitCode);
          setRunAutoActive(false);
          runAutoActiveRef.current = false;
        }
        return;
      }
      if (stepId === "INSTALL_MINIFORGE") {
        if (kind === "OK") {
          term.write("[install-conda] miniforge installed successfully.\n");
          finishInstallSuccess();
          if (runAutoActiveRef.current) {
            setTimeout(() => handleCreateEnv(), 300);
          }
        } else {
          finishInstallFail("INSTALL_MINIFORGE", exitCode);
          setRunAutoActive(false);
          runAutoActiveRef.current = false;
        }
        return;
      }
      if (stepId === "INSTALL_REMOVE_AFTER_CANCEL") {
        term.write(
          kind === "OK"
            ? "[cancel] partial install removed.\n"
            : `[cancel] cleanup exited ${exitCode ?? "?"}\n`,
        );
        finishCancelInstall();
        return;
      }
      if (stepId === "CONDA_CREATE") {
        if (kind === "OK") {
          markCreateEnvStep("PIP_INSTALL");
          term.write("[create-env] conda env created; installing pip packages...\n");
          term.runCommand(
            wrapWithSentinel(buildPipInstallCommand(envPython), "PIP_INSTALL"),
          );
        } else {
          finishCreateEnvFail("CONDA_CREATE", exitCode);
          setRunAutoActive(false);
          runAutoActiveRef.current = false;
        }
        return;
      }
      if (stepId === "PIP_INSTALL") {
        if (kind === "OK") {
          markCreateEnvStep("EVOLVEPRO_INSTALL");
          term.write(
            "[create-env] pip install complete; installing EvolvePro source (workaround for upstream missing __init__.py)...\n",
          );
          term.runCommand(
            wrapWithSentinel(
              buildEvolveProInstallCommand(envPython),
              "EVOLVEPRO_INSTALL",
            ),
          );
        } else {
          finishCreateEnvFail("PIP_INSTALL", exitCode);
          setRunAutoActive(false);
          runAutoActiveRef.current = false;
        }
        return;
      }
      if (stepId === "EVOLVEPRO_INSTALL") {
        if (kind === "OK") {
          markCreateEnvStep("VERIFY");
          term.write(
            "[create-env] EvolvePro source installed; verifying imports...\n",
          );
          term.runCommand(
            wrapWithSentinel(buildVerifyCommand(envPython), "VERIFY"),
          );
        } else {
          finishCreateEnvFail("EVOLVEPRO_INSTALL", exitCode);
          setRunAutoActive(false);
          runAutoActiveRef.current = false;
        }
        return;
      }
      if (stepId === "VERIFY") {
        if (kind === "OK") {
          term.write("[create-env] verification passed; refreshing env state...\n");
          finishCreateEnvSuccess();
          setRunAutoActive(false);
          runAutoActiveRef.current = false;
          // Re-detect to refresh condaStatus/envStatus with the freshly installed env.
          void detect().catch((e) => {
            console.warn("[CondaSetupWizard] post-VERIFY detect failed:", e);
          });
        } else {
          finishCreateEnvFail("VERIFY", exitCode);
          setRunAutoActive(false);
          runAutoActiveRef.current = false;
        }
        return;
      }
      if (stepId === "ENV_REMOVE_AFTER_CANCEL") {
        term.write(
          kind === "OK"
            ? "[cancel] partial env removed.\n"
            : `[cancel] cleanup exited ${exitCode ?? "?"}\n`,
        );
        finishCancelCreateEnv();
        return;
      }
      if (stepId === "ENV_RESET") {
        term.write(
          kind === "OK"
            ? "[reset] evolvepro env removed.\n"
            : `[reset] cleanup exited ${exitCode ?? "?"}\n`,
        );
        setEnvResetting(false);
        reset();
        return;
      }
      if (kind === "OK") {
        console.debug(`[CondaSetupWizard] sentinel OK: ${stepId}`);
      } else {
        console.debug(
          `[CondaSetupWizard] sentinel FAIL: ${stepId} exit=${exitCode ?? "?"}`,
        );
      }
    });
    return unsubscribe;
  }, [
    envPython,
    markCreateEnvStep,
    finishCreateEnvSuccess,
    finishCreateEnvFail,
    finishCancelCreateEnv,
    markInstallStep,
    finishInstallSuccess,
    finishInstallFail,
    finishCancelInstall,
    setPrefixConflict,
    reset,
    detect,
  ]);

  // Note: previous installProgress mirror effect and bytes/total progress bar
  // computation removed in v0.5.20 (PTY routing). The terminal itself is now
  // the live progress surface; the dialog shows an indeterminate bar.

  const failedPackages = envStatus?.packages
    ? Object.entries(envStatus.packages)
        .filter(([, v]) => v === null)
        .map(([k]) => k)
        .join(", ")
    : "";

  const setupSteps: Array<{ key: string; label: string; status: SetupStatus }> = [
    {
      key: "conda",
      label: t("conda.wizard.progressSteps.conda"),
      status: stage === "error"
        ? "error"
        : condaStatus?.installed || stage === "needs_env" || stage === "creating_env" || stage === "cancelling" || stage === "verifying" || stage === "done" || stage === "needs_repair"
          ? "done"
          : stage === "detecting" || stage === "installing_conda" || stage === "needs_conda"
            ? "active"
            : "pending",
    },
    {
      key: "env",
      label: t("conda.wizard.progressSteps.env"),
      status: stage === "error"
        ? "error"
        : stage === "done"
          ? "done"
          : stage === "creating_env" && currentStep === "CONDA_CREATE"
            ? "active"
            : stage === "creating_env" || stage === "verifying" || stage === "needs_repair" || envStatus?.exists
              ? "done"
              : stage === "needs_env" || stage === "cancelling"
                ? "active"
                : "pending",
    },
    {
      key: "packages",
      label: t("conda.wizard.progressSteps.packages"),
      status: stage === "error"
        ? "error"
        : stage === "done"
          ? "done"
          : stage === "creating_env" &&
              (currentStep === "PIP_INSTALL" ||
                currentStep === "EVOLVEPRO_INSTALL")
            ? "active"
            : stage === "creating_env" && currentStep === "VERIFY"
              ? "done"
              : stage === "needs_repair"
                ? "active"
                : "pending",
    },
    {
      key: "verify",
      label: t("conda.wizard.progressSteps.verify"),
      status: stage === "error"
        ? "error"
        : stage === "done"
          ? "done"
          : stage === "verifying" || (stage === "creating_env" && currentStep === "VERIFY")
            ? "active"
            : "pending",
    },
  ];

  const currentWorkKey = summarizeCurrentWorkKey(stage, currentInstallStep, currentStep);
  const currentWork = currentWorkKey ? t(currentWorkKey) : null;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-2xl" aria-describedby="conda-wizard-desc">
        <DialogHeader>
          <DialogTitle>{t("conda.wizard.title")}</DialogTitle>
        </DialogHeader>
        <div id="conda-wizard-desc" className="space-y-4">
          {stage === "idle" && (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">
                {t("conda.wizard.idleHint")}
              </p>
              <Button
                onClick={() => {
                  setUserInitiatedAction(true);
                  void detect();
                }}
                className="w-fit"
              >
                {t("conda.wizard.start")}
              </Button>
            </div>
          )}

          {stage === "detecting" && (
            <div className="flex items-center gap-3" role="status" aria-live="polite">
              <Spinner size="sm" />
              <span className="text-sm text-muted-foreground">{t("conda.wizard.detecting")}</span>
            </div>
          )}

          {stage === "needs_conda" && (
            <div className="flex flex-col gap-3">
              <p className="text-sm">{t("conda.wizard.needsConda")}</p>
              <Button onClick={handleInstallConda} className="w-fit">
                {t("conda.wizard.installConda")}
              </Button>
            </div>
          )}

          {stage === "installing_conda" && (
            <div className="flex flex-col gap-3" role="status" aria-live="polite">
              <Progress className="h-2" />
              <p className="text-xs text-muted-foreground">
                {t("conda.wizard.installingConda")}
              </p>
              <Button
                variant="outline"
                onClick={handleCancelInstallConda}
                className="w-fit"
              >
                {t("conda.wizard.cancel")}
              </Button>
            </div>
          )}

          {stage === "cancelling_install" && (
            <div className="flex items-center gap-3" role="status" aria-live="polite">
              <Spinner size="sm" />
              <span className="text-sm text-muted-foreground">
                {t("conda.wizard.cancellingPleaseWait")}
              </span>
            </div>
          )}

          {stage === "needs_env" && (
            <div className="flex flex-col gap-3">
              <p className="text-sm">{t("conda.wizard.needsEnv")}</p>
              <Button onClick={handleCreateEnv} className="w-fit">
                {t("conda.wizard.createEnv")}
              </Button>
            </div>
          )}

          {stage === "creating_env" && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-3" role="status" aria-live="polite">
                <Spinner size="sm" />
                <span className="text-sm text-muted-foreground">
                  {t("conda.wizard.creatingEnv")}
                </span>
              </div>
              <Button
                variant="destructive"
                size="sm"
                onClick={handleCancelCreateEnv}
                className="w-fit"
              >
                {t("conda.wizard.cancel")}
              </Button>
            </div>
          )}

          {stage === "cancelling" && (
            <div className="flex items-center gap-3" role="status" aria-live="polite">
              <Spinner size="sm" />
              <span className="text-sm text-muted-foreground">
                {t("conda.wizard.cancellingPleaseWait")}
              </span>
            </div>
          )}

          {stage === "needs_repair" && (
            <div className="flex flex-col gap-3">
              <p className="text-sm">
                {failedPackages
                  ? t("conda.wizard.needsRepairPackages", { packages: failedPackages })
                  : t("conda.wizard.needsRepair")}
              </p>
              <Button onClick={handleCreateEnv} className="w-fit">
                {t("conda.wizard.recreate")}
              </Button>
            </div>
          )}

          {stage === "verifying" && (
            <div className="flex items-center gap-3" role="status" aria-live="polite">
              <Spinner size="sm" />
              <span className="text-sm text-muted-foreground">{t("conda.wizard.verifying")}</span>
            </div>
          )}

          {stage === "prefix_conflict" && (
            <div className="flex flex-col items-center gap-3 py-2">
              <AlertTriangle className="h-12 w-12 text-amber-500" aria-hidden="true" />
              <p className="text-sm text-center">
                {t("conda.wizard.prefixConflict")}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  onClick={() => void removeExistingMiniforge()}
                  className="w-fit"
                >
                  {t("conda.wizard.removeAndReinstall")}
                </Button>
                <Button variant="outline" onClick={() => setOpen(false)} className="w-fit">
                  {t("conda.wizard.cancel")}
                </Button>
              </div>
            </div>
          )}

          {stage === "done" && (
            <div className="flex flex-col items-center gap-3 py-2">
              <CheckCircle2 className="h-12 w-12 text-green-500" aria-hidden="true" />
              <p className="text-sm font-medium">{t("conda.wizard.done")}</p>
              <div className="flex flex-col items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={initShellRunning}
                  onClick={() => {
                    const term = termRef.current;
                    if (!condaStatus?.conda_exe || initShellRunning || !term) return;
                    if (!window.confirm("Run `conda init` to enable the `conda` command in this terminal? This modifies your shell profile permanently.")) return;
                    setInitShellRunning(true);
                    term.write("[conda init] running...\n");
                    const cmd = wrapWithSentinel(
                      buildInitShellCommand(condaStatus.conda_exe),
                      "INIT_SHELL",
                    );
                    term.runCommand(cmd);
                  }}
                  className="w-fit"
                >
                  {initShellRunning ? "Enabling..." : "Enable `conda` command in terminal"}
                </Button>
                <Button onClick={() => setOpen(false)} className="w-fit">
                  {t("conda.wizard.close")}
                </Button>
              </div>
            </div>
          )}

          {stage === "error" && (
            <div className="flex flex-col items-center gap-3 py-2">
              <XCircle className="h-12 w-12 text-destructive" aria-hidden="true" />
              <p className="text-sm text-destructive break-all">{error}</p>
              <div className="flex gap-2">
                <Button
                  onClick={() => {
                    setUserInitiatedAction(true);
                    void retry();
                  }}
                  variant="outline"
                  className="w-fit"
                >
                  {t("conda.wizard.retry")}
                </Button>
                <Button onClick={reset} variant="ghost" className="w-fit text-xs text-muted-foreground">
                  {t("conda.wizard.resetAll")}
                </Button>
              </div>
            </div>
          )}

          <div className="space-y-3 rounded border border-border bg-muted/30 p-3" role="status" aria-live="polite">
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium">{t("conda.wizard.progressTitle")}</p>
              {currentWork ? (
                <p className="text-xs text-muted-foreground">{currentWork}</p>
              ) : null}
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {setupSteps.map((step) => {
                // Suppress the spinning Loader2 in the progress panel until the
                // user explicitly clicks an action button. Auto-triggered detect
                // on wizard mount keeps the icons as static dots.
                const displayStatus: SetupStatus =
                  step.status === "active" && !userInitiatedAction
                    ? "pending"
                    : step.status;
                return (
                  <div key={step.key} className="flex min-w-0 items-center gap-2 rounded border border-border bg-background px-2 py-2">
                    <StatusIcon status={displayStatus} />
                    <span className="truncate text-xs">{step.label}</span>
                  </div>
                );
              })}
            </div>
            {stage === "creating_env" ? (
              <p className="text-xs text-muted-foreground">
                {t("conda.wizard.creatingEnvHint")}
              </p>
            ) : null}
          </div>

          <div className="mt-4 flex flex-col gap-2 border-t pt-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">Terminal</p>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={manualMode}
                    onChange={(e) => setManualMode(e.target.checked)}
                    className="h-3.5 w-3.5"
                  />
                  Manual input mode
                </label>
                <Button
                  size="sm"
                  onClick={() => void handleRunAuto()}
                  disabled={autoRunning}
                  className="w-fit"
                >
                  {autoRunning ? "Running..." : "Run Auto"}
                </Button>
                {stage !== "detecting" &&
                stage !== "cancelling" &&
                stage !== "cancelling_install" ? (
                  resetConfirming ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted-foreground">
                        {t("conda.wizard.resetConfirmPrompt")}
                      </span>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={handleResetEnv}
                        disabled={envResetting || autoRunning}
                        className="w-fit"
                      >
                        {t("conda.wizard.resetConfirmYes")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={handleCancelReset}
                        disabled={envResetting || autoRunning}
                        className="w-fit"
                      >
                        {t("conda.wizard.resetConfirmNo")}
                      </Button>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleResetEnv}
                      disabled={envResetting || autoRunning}
                      className="w-fit"
                      title={t("conda.wizard.resetEnvTitle")}
                    >
                      {envResetting
                        ? t("conda.wizard.resetEnvRemoving")
                        : t("conda.wizard.resetEnvButton")}
                    </Button>
                  )
                ) : null}
              </div>
            </div>
            <SetupTerminal ref={termRef} autoConfirm={!manualMode} className="h-64 w-full rounded border bg-[#0b0f17]" />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
