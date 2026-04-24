import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { MameAppLayout } from "@/components/mame/layout/MameAppLayout";
import { rpc } from "@/lib/ipc";
import { listRecentProjects, loadProject } from "@/lib/project";
import { useKumaProject } from "@/state/projectContext";

type MatchCandidate = { path: string; name: string };

export function MameTab() {
  const project = useKumaProject();
  const [match, setMatch] = useState<MatchCandidate | null>(null);

  useEffect(() => {
    const handler = async (ev: Event) => {
      const custom = ev as CustomEvent<{ path: string }>;
      const xlsxPath = custom.detail?.path;
      if (!xlsxPath) {
        return;
      }
      try {
        const meta = await rpc<{ project_id: string } | null>("mame", "read_kuma_meta", {
          path: xlsxPath,
        });
        if (!meta || !meta.project_id) {
          return;
        }
        if (project?.project_id === meta.project_id) {
          return;
        }
        const recents = await listRecentProjects();
        const hit = recents.find((recent) => recent.project_id === meta.project_id);
        if (hit) {
          setMatch({ path: hit.path, name: hit.name });
        }
      } catch {
        // silent fallback to scratch
      }
    };

    window.addEventListener("kuma:mame-xlsx-dropped", handler as EventListener);
    return () => {
      window.removeEventListener("kuma:mame-xlsx-dropped", handler as EventListener);
    };
  }, [project?.project_id]);

  async function confirmLoad() {
    if (!match) {
      return;
    }
    try {
      await loadProject(match.path);
      window.dispatchEvent(
        new CustomEvent("kuma:project-load-request", { detail: { path: match.path } }),
      );
    } finally {
      setMatch(null);
    }
  }

  return (
    <>
      <MameAppLayout />
      <Dialog open={match !== null} onOpenChange={(open) => !open && setMatch(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>프로젝트 매칭 발견</DialogTitle>
            <DialogDescription>
              {match ? `${match.name} 프로젝트로 로드하시겠어요?` : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMatch(null)}>
              아니오
            </Button>
            <Button onClick={() => void confirmLoad()}>로드</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
