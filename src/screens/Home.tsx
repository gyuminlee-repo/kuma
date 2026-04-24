import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Button } from "../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { cn, formatError } from "../lib/utils";
import {
  createProject,
  listRecentProjects,
  loadProject,
  type RecentProject,
} from "../lib/project";

type HomeProps = {
  onOpenProject: (path: string) => void;
  onOpenScratch: (kuroJsonPath: string) => void;
  onOpenSettings: () => void;
};

export function Home({ onOpenProject, onOpenScratch, onOpenSettings }: HomeProps) {
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>([]);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    void listRecentProjects()
      .then((items) => {
        if (isMounted) {
          setRecentProjects(items);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(formatError(err));
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  async function handleCreateProject() {
    const trimmedName = projectName.trim();
    if (!trimmedName) {
      setError("프로젝트 이름을 입력해 주세요.");
      return;
    }

    setIsCreating(true);
    setError("");
    try {
      const path = await createProject(trimmedName);
      setIsCreateOpen(false);
      setProjectName("");
      onOpenProject(path);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setIsCreating(false);
    }
  }

  async function handleOpenRecentProject(path: string) {
    setError("");
    try {
      await loadProject(path);
      onOpenProject(path);
    } catch (err) {
      setError(formatError(err));
    }
  }

  async function handleOpenFile() {
    setError("");
    try {
      const selected = await open({
        directory: false,
        filters: [
          { name: "Kuro Workspace", extensions: ["kuro.json"] },
          { name: "Kuma Project", extensions: ["json"] },
        ],
      });

      if (typeof selected !== "string") {
        return;
      }

      if (selected.endsWith(".kuro.json")) {
        onOpenScratch(selected);
        return;
      }

      await loadProject(selected);
      onOpenProject(selected);
    } catch (err) {
      setError(formatError(err));
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 px-6 py-12 text-slate-900">
      <div className="mx-auto flex w-full max-w-4xl flex-col items-center">
        <h1 className="text-center text-5xl font-bold tracking-tight">kuma</h1>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Button className="min-w-32" onClick={() => {
            setError("");
            setIsCreateOpen(true);
          }}>
            + 새 프로젝트
          </Button>
          <Button variant="outline" className="min-w-32 bg-white" onClick={() => void handleOpenFile()}>
            파일 열기
          </Button>
          <Button variant="outline" className="min-w-24 bg-white" onClick={onOpenSettings}>
            설정
          </Button>
        </div>

        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

        <section className="mt-12 w-full rounded-3xl border border-slate-200 bg-white/90 p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">최근 프로젝트</h2>
          </div>

          <div className="space-y-3">
            {recentProjects.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                아직 없어요
              </div>
            ) : (
              recentProjects.map((project) => (
                <button
                  key={project.path}
                  type="button"
                  onClick={() => void handleOpenRecentProject(project.path)}
                  className={cn(
                    "w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-left transition",
                    "hover:border-slate-300 hover:bg-slate-100",
                  )}
                >
                  <div className="font-medium text-slate-900">{project.name}</div>
                  <div className="mt-1 text-sm text-slate-600">{project.path}</div>
                  <div className="mt-2 text-xs text-slate-500">{project.last_opened}</div>
                </button>
              ))
            )}
          </div>
        </section>
      </div>

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>새 프로젝트</DialogTitle>
            <DialogDescription>프로젝트 이름을 입력해 주세요.</DialogDescription>
          </DialogHeader>

          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void handleCreateProject();
            }}
          >
            <Input
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder="프로젝트 이름"
              aria-label="프로젝트 이름"
            />

            <DialogFooter>
              <Button type="submit" disabled={isCreating}>
                생성
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
