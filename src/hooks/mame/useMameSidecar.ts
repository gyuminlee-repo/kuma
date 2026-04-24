import { useCallback, useEffect, useRef, useState } from "react";
import { spawnSidecar, isSidecarRunning, setProgressHandler } from "@/lib/ipc-mame";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { SidecarStatus } from "@/types/mame/models";

export function useMameSidecar() {
  const [status, setStatus] = useState<SidecarStatus>("disconnected");
  const mountedRef = useRef(true);
  const connectRef = useRef<(() => void) | null>(null);
  const attemptsRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    setProgressHandler((progress) => {
      useMameAppStore.setState((state) => ({
        analyzeProgress: progress.value,
        analyzeMessage: progress.message,
        isAnalyzing: state.isAnalyzing || progress.value < 100,
      }));
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

    if (!isSidecarRunning()) {
      connect();
    } else {
      setStatus("ready");
    }

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
