/**
 * useRunDesign — shared Run Design logic (AppLayout + RunDesignAction single source)
 *
 * Extracts tryRunDesign from AppLayout.tsx (lines 117–160) into a reusable hook.
 * Manages dialog states internally (sizeWarning, preflight) so callers can mount
 * the companion dialogs without prop-drilling.
 *
 * Returns:
 *   run()            — call to trigger design with preflight + size guard
 *   isDesigning      — boolean reactive from store
 *   missingFields    — derived array (re-computed on each call), empty = ready
 *   hasBlockingIssue — true when missingFields.length > 0 or sidecar not ready
 *   sizeWarning      — pending size-warning state (pass to InputSizeWarningDialog)
 *   setSizeWarning   — clear/advance from calling component
 *   preflightResult  — pending preflight result (pass to PreflightDialog)
 *   setPreflightResult — clear/advance from calling component
 */

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { checkKuroInputSize, type InputSizeLevel } from "@/lib/inputThresholds";
import { runPreflightCheck, type PreflightResult } from "@/lib/preflight";
import { useFlushKuroBeforeDesign } from "./useKuroAutosave";
import { useSidecar } from "./useSidecar";

export interface SizeWarningState {
  level: InputSizeLevel;
  message: string;
  pendingAction: () => void;
}

export interface PreflightState {
  result: PreflightResult;
  pendingAction: () => void;
}

export interface UseRunDesignReturn {
  run: () => void;
  isDesigning: boolean;
  missingFields: string[];
  hasBlockingIssue: boolean;
  sizeWarning: SizeWarningState | null;
  setSizeWarning: (s: SizeWarningState | null) => void;
  preflightResult: PreflightState | null;
  setPreflightResult: (s: PreflightState | null) => void;
}

export function useRunDesign(): UseRunDesignReturn {
  const { t } = useTranslation();
  const isDesigning = useAppStore((s) => s.isDesigning);
  const flushBeforeDesign = useFlushKuroBeforeDesign();
  const { status: sidecarStatus } = useSidecar();

  const [sizeWarning, setSizeWarning] = useState<SizeWarningState | null>(null);
  const [preflightResult, setPreflightResult] = useState<PreflightState | null>(null);

  const collectMissingFields = useCallback((): string[] => {
    const s = useAppStore.getState();
    const missing: string[] = [];
    if (!s.seqInfo) missing.push(t("appLayout.missingSeqFile"));
    if (!s.mutationText.trim()) missing.push(t("appLayout.missingMutations"));
    if (s.seqInfo && s.seqInfo.genes.length > 1 && !s.selectedGene) {
      missing.push(t("appLayout.missingTargetGene"));
    }
    return missing;
  // t is stable across renders; exhaustive-deps intentionally minimal
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = useCallback(() => {
    if (useAppStore.getState().isDesigning) return;

    const missing = collectMissingFields();
    if (missing.length > 0) {
      // Callers subscribe to missingFields via the return value; no extra state needed.
      return;
    }

    const mutationText = useAppStore.getState().mutationText;
    const rowCount = mutationText
      .trim()
      .split("\n")
      .filter((l) => l.trim() && !l.trim().startsWith("#")).length;
    const sizeCheck = checkKuroInputSize({ rowCount });

    const runWithPreflight = () => {
      void runPreflightCheck({ sidecarStatus, requiresNetwork: false }).then(
        (pfResult) => {
          const actualRun = () => {
            void flushBeforeDesign().then(() =>
              useAppStore.getState().designPrimers(),
            );
          };
          if (!pfResult.ok || pfResult.warnings.length > 0) {
            setPreflightResult({ result: pfResult, pendingAction: actualRun });
          } else {
            actualRun();
          }
        },
      );
    };

    if (sizeCheck.level !== "ok") {
      setSizeWarning({
        level: sizeCheck.level,
        message: sizeCheck.message,
        pendingAction: runWithPreflight,
      });
      return;
    }

    runWithPreflight();
  }, [collectMissingFields, flushBeforeDesign, sidecarStatus]);

  // Derive missingFields on each render so callers always see fresh state
  const missingFields = collectMissingFields();
  const hasBlockingIssue = missingFields.length > 0 || sidecarStatus !== "ready";

  return {
    run,
    isDesigning,
    missingFields,
    hasBlockingIssue,
    sizeWarning,
    setSizeWarning,
    preflightResult,
    setPreflightResult,
  };
}
