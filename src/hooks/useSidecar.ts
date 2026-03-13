import { useEffect, useRef, useState } from "react";
import { spawnSidecar, killSidecar, isSidecarRunning } from "../lib/ipc";

export type SidecarStatus = "disconnected" | "connecting" | "ready" | "error";

export function useSidecar() {
  const [status, setStatus] = useState<SidecarStatus>("disconnected");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    let retryTimeout: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const MAX_RETRIES = 5;

    async function connect() {
      if (!mountedRef.current) return;
      setStatus("connecting");
      try {
        await spawnSidecar();
        if (mountedRef.current) setStatus("ready");
      } catch (err) {
        attempts++;
        console.error(
          `[useSidecar] Failed to spawn (attempt ${attempts}/${MAX_RETRIES}):`,
          err,
        );
        if (mountedRef.current && attempts < MAX_RETRIES) {
          setStatus("error");
          retryTimeout = setTimeout(connect, 3000 * Math.min(attempts, 3));
        } else if (mountedRef.current) {
          setStatus("error");
        }
      }
    }

    if (!isSidecarRunning()) {
      connect();
    } else {
      setStatus("ready");
    }

    return () => {
      mountedRef.current = false;
      clearTimeout(retryTimeout);
      killSidecar();
    };
  }, []);

  return { status };
}
