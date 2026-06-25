import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { open } from "@tauri-apps/plugin-dialog";
import { ChevronRight, ChevronUp, FlaskConical, Target, Trash2 } from "lucide-react";
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
import { Card, CardDescription, CardTitle } from "../components/ui/card";
import { cn, formatError } from "../lib/utils";
import {
  createProject,
  listRecentProjects,
  loadProject,
  removeRecentProject,
  type RecentProject,
} from "../lib/project";

type HomeProps = {
  onOpenProject: (path: string) => void;
  onOpenScratch: (kuroJsonPath: string) => void;
  onOpenSettings: () => void;
};

export function Home({ onOpenProject, onOpenScratch, onOpenSettings }: HomeProps) {
  const { t } = useTranslation();
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>([]);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<RecentProject | null>(null);
  const [overviewCollapsed, setOverviewCollapsed] = useState<boolean>(
    () => localStorage.getItem("kuma.home.overviewCollapsed") === "1",
  );

  function toggleOverview() {
    setOverviewCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("kuma.home.overviewCollapsed", next ? "1" : "0");
      return next;
    });
  }

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
      setError(t("home.errorEnterName"));
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
    <div className="min-h-screen bg-muted px-6 py-12 text-foreground">
      <div className="mx-auto flex w-full max-w-4xl flex-col items-center">
        <h1 className="text-center text-5xl font-bold tracking-tight">kuma</h1>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Button className="min-w-32" onClick={() => {
            setError("");
            setIsCreateOpen(true);
          }}>
            {t("home.newProject")}
          </Button>
          <Button variant="outline" className="min-w-32" onClick={() => void handleOpenFile()}>
            {t("home.openFile")}
          </Button>
          <Button variant="outline" className="min-w-24" onClick={onOpenSettings}>
            {t("home.settings")}
          </Button>
        </div>

        {error ? <p className="mt-4 text-sm text-error">{error}</p> : null}

        <section
          aria-label={t("home.overview.aria")}
          className="mt-12 w-full rounded-container border border-border bg-card p-6"
        >
          {overviewCollapsed ? (
            <button
              type="button"
              onClick={toggleOverview}
              aria-expanded={false}
              className="flex w-full items-center gap-2 text-left text-base font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              {t("home.overview.aria")}
            </button>
          ) : (
            <>
              <div className="flex items-start justify-between gap-2">
                <p className="text-base font-medium text-foreground">
                  {t("home.overview.identity")}
                </p>
                <button
                  type="button"
                  onClick={toggleOverview}
                  aria-label={t("home.overview.collapse")}
                  aria-expanded={true}
                  className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <ChevronUp className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <h2 className="sr-only">{t("home.overview.aria")}</h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <Card className="border-border bg-muted/40 p-4">
                  <div className="flex items-start gap-3">
                    <Target className="mt-0.5 h-5 w-5 shrink-0 text-info" aria-hidden="true" />
                    <div>
                      <CardTitle className="text-sm font-semibold">
                        {t("home.overview.kuroTitle")}
                      </CardTitle>
                      <CardDescription className="mt-1">
                        {t("home.overview.kuroDesc")}
                      </CardDescription>
                    </div>
                  </div>
                </Card>
                <Card className="border-border bg-muted/40 p-4">
                  <div className="flex items-start gap-3">
                    <FlaskConical className="mt-0.5 h-5 w-5 shrink-0 text-info" aria-hidden="true" />
                    <div>
                      <CardTitle className="text-sm font-semibold">
                        {t("home.overview.mameTitle")}
                      </CardTitle>
                      <CardDescription className="mt-1">
                        {t("home.overview.mameDesc")}
                      </CardDescription>
                    </div>
                  </div>
                </Card>
              </div>
              <button
                type="button"
                onClick={() => {
                  void import("@tauri-apps/plugin-shell").then((m) =>
                    m.open("https://github.com/gyuminlee-repo/kuma#readme"),
                  );
                }}
                className="mt-4 inline-block text-sm text-info underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                {t("home.overview.learnMore")}
              </button>
            </>
          )}
        </section>

        <section className="mt-12 w-full rounded-container border border-border bg-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">{t("home.recentProjects")}</h2>
          </div>

          <div className="space-y-3">
            {recentProjects.length === 0 ? (
              <div className="rounded-container border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                {t("home.noProjects")}
              </div>
            ) : (
              recentProjects.map((project) => (
                <div key={project.path} className="relative">
                  <button
                    type="button"
                    onClick={() => void handleOpenRecentProject(project.path)}
                    className={cn(
                      "w-full rounded-container border border-border bg-muted/50 px-4 py-3 pr-12 text-left transition",
                      "hover:border-border hover:bg-muted",
                    )}
                  >
                    <div className="font-medium text-foreground">{project.name}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{project.path}</div>
                    <div className="mt-2 text-xs text-muted-foreground">{project.last_opened}</div>
                  </button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t("home.deleteButton")}
                    className="absolute right-2 top-2 h-8 w-8 text-muted-foreground hover:text-error"
                    onClick={(e) => {
                      e.stopPropagation();
                      setPendingDelete(project);
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("home.dialogTitle")}</DialogTitle>
            <DialogDescription>{t("home.dialogDescription")}</DialogDescription>
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
              placeholder={t("home.projectNamePlaceholder")}
              aria-label={t("home.projectNameLabel")}
            />

            <DialogFooter>
              <Button type="submit" disabled={isCreating}>
                {t("home.createButton")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={!!pendingDelete} onOpenChange={(o) => !o && setPendingDelete(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("home.deleteConfirmTitle")}</DialogTitle>
            <DialogDescription>{t("home.deleteConfirmDesc")}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setPendingDelete(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-error border-error/40 hover:bg-error/8"
              onClick={async () => {
                if (!pendingDelete) return;
                try {
                  await removeRecentProject(pendingDelete.path);
                  const items = await listRecentProjects();
                  setRecentProjects(items);
                } catch (err) {
                  setError(formatError(err));
                } finally {
                  setPendingDelete(null);
                }
              }}
            >
              {t("home.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
