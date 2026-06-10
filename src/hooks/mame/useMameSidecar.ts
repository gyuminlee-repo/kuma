import { useCallback, useEffect, useRef, useState } from "react";
import { spawnSidecar, setProgressHandler } from "@/lib/ipc-mame";
import { composeAnalysisProgress } from "@/lib/mame/composeAnalysisProgress";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import { useAppStore } from "@/store/appStore";
import type { SidecarStatus } from "@/types/mame/models";

export function useMameSidecar() {
  const [status, setStatus] = useState<SidecarStatus>("disconnected");
  const mountedRef = useRef(true);
  const connectRef = useRef<(() => void) | null>(null);
  const attemptsRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    setProgressHandler((progress) => {
      useMameAppStore.setState((state) => {
        const hasStage = progress.stage !== undefined;
        // Folded raw-run analyze (single `analyze` call over a MinKNOW run
        // folder): the backend already emits a unified 0..100 value (demux
        // 0..50, analyze 50..100) and stamps a `stage` key. Pass it through
        // as-is — composeAnalysisProgress here would double-rescale. The
        // legacy/consensus path (no stage) keeps phase-based scaling.
        const scaledProgress = hasStage
          ? Math.round(Math.max(0, Math.min(100, progress.value)))
          : composeAnalysisProgress(
              progress.value,
              state.analyzePhase ?? "analyze",
              state.inputMode === "raw_run",
            );
        return {
          analyzeProgress: scaledProgress,
          analyzeMessage: progress.message,
          isAnalyzing: state.isAnalyzing || progress.value < 100,
          ...(progress.current !== undefined && progress.total !== undefined
            ? { analyzeCurrent: progress.current, analyzeTotal: progress.total }
            : {}),
          ...(hasStage ? { analyzeStage: progress.stage } : {}),
          // Drive the demux->analyze phase transition off the backend stage so
          // the single-call raw-run path advances the UI without a manual flip.
          ...(progress.stage === "demux" || progress.stage === "analyze"
            ? { analyzePhase: progress.stage }
            : {}),
        };
      });
      if (progress.message) {
        const ts = new Date().toLocaleTimeString();
        useAppStore.getState().appendLogLine(`[${ts}] [MAME] ${progress.message}`);
      }
    });
    return () => setProgressHandler(null);
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const MAX_RETRIES = 5;

    async function connect() {
      if (!mountedRef.current) return;
      setStatus("connecting");
      try {
        await spawnSidecar();
        if (mountedRef.current) {
          attemptsRef.current = 0;
          setStatus("ready");
        }
      } catch (error) {
        attemptsRef.current++;
        console.error(
          `[useSidecar] Failed to spawn (attempt ${attemptsRef.current}/${MAX_RETRIES}):`,
          error,
        );
        if (mountedRef.current && attemptsRef.current < MAX_RETRIES) {
          setStatus("error");
          retryTimeoutRef.current = setTimeout(connect, 3000 * Math.min(attemptsRef.current, 3));
        } else if (mountedRef.current) {
          setStatus("error");
        }
      }
    }

    connectRef.current = connect;

    connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(retryTimeoutRef.current);
      // Do not kill sidecar on unmount: lifecycle is owned by the Rust manager
      // so the sidecar persists across tab switches.
    };
  }, []);

  const retry = useCallback(() => {
    clearTimeout(retryTimeoutRef.current);
    attemptsRef.current = 0;
    connectRef.current?.();
  }, []);

  return { status, retry };
}
