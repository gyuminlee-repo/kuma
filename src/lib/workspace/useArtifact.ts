import { useEffect, useState } from "react";
import { getLatestArtifact, getActiveWorkspace } from "./api";
import { subscribe } from "./events";
import type { ArtifactRef, ArtifactType } from "./types";

export function useArtifact(type: ArtifactType): ArtifactRef | null {
  const [ref, setRef] = useState<ArtifactRef | null>(null);

  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      if (!getActiveWorkspace()) {
        if (alive) setRef(null);
        return;
      }
      try {
        const v = await getLatestArtifact(type);
        if (alive) setRef(v);
      } catch {
        if (alive) setRef(null);
      }
    };
    refresh();
    const off = subscribe("workspace:updated", refresh);
    return () => {
      alive = false;
      off();
    };
  }, [type]);

  return ref;
}
