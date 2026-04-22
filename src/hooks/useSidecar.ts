import { useCallback, useEffect, useRef, useState } from "react";
import { spawnSidecar, killSidecar, isSidecarRunning } from "../lib/ipc";

type SidecarStatus = "disconnected" | "connecting" | "ready" | "error";

export function useSidecar() {
  const [status, setStatus] = useState<SidecarStatus>("disconnected");
  const mountedRef = useRef(true);
  const connectRef = useRef<(() => void) | null>(null);
  const attemptsRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

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
      } catch (err) {
        attemptsRef.current++;
        console.error(
          `[useSidecar] Failed to spawn (attempt ${attemptsRef.current}/${MAX_RETRIES}):`,
          err,
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
      killSidecar();
    };
  }, []);

  /** Reset attempt counter and restart the connection loop. */
  const retry = useCallback(() => {
    clearTimeout(retryTimeoutRef.current);
    attemptsRef.current = 0;
    connectRef.current?.();
  }, []);

  return { status, retry };
}
