/**
 * useProjectArchiveActions.ts, project zip import and export, shared by both menubars.
 *
 * The archive holds the whole project folder, which is the work of both apps: the two
 * autosave snapshots, the workspace manifest and the artifacts routed into the folder
 * (`src-tauri/src/project_archive.rs`). So the action belongs to the project rather
 * than to KURO, and living in one menubar is what let MAME go without it.
 *
 * Keeping the two callbacks here rather than in each menubar also keeps their failure
 * behaviour identical. A cancelled dialog is not an error and stays silent; a failed
 * archive says so in a toast instead of leaving the operator to guess.
 */

import { useCallback } from "react";
import { open as openDialog, save as saveDialog } from "@tauri-apps/plugin-dialog";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { exportProjectZip, importProjectZip, getConfig, loadProject } from "@/lib/project";

export interface ProjectArchiveActions {
  exportZip: () => void;
  importZip: () => void;
}

export function useProjectArchiveActions(
  projectPath: string | undefined,
  projectName: string | undefined,
): ProjectArchiveActions {
  const { t } = useTranslation();

  const exportZip = useCallback(() => {
    void (async () => {
      if (!projectPath) return;
      try {
        const target = await saveDialog({
          defaultPath: `${projectName ?? "kuma-project"}.zip`,
          filters: [{ name: "ZIP", extensions: ["zip"] }],
        });
        if (!target) return;
        const summary = await exportProjectZip(projectPath, target);
        toast.success(
          t("file.exportProjectZipDone", { count: summary.file_count, path: summary.path }),
        );
      } catch (err) {
        toast.error(t("file.exportProjectZipFailed", { detail: String(err) }));
      }
    })();
  }, [projectPath, projectName, t]);

  const importZip = useCallback(() => {
    void (async () => {
      try {
        const archive = await openDialog({
          multiple: false,
          filters: [{ name: "ZIP", extensions: ["zip"] }],
        });
        if (typeof archive !== "string") return;
        const config = await getConfig();
        const summary = await importProjectZip(archive, config.projects_root);
        await loadProject(summary.path);
        toast.success(
          t("file.importProjectZipDone", { count: summary.file_count, path: summary.path }),
        );
        // 풀어 놓고 열지 않으면 사용자가 폴더를 다시 찾아야 하므로 한 동작으로 잇는다.
        window.dispatchEvent(new CustomEvent("kuma:return-to-home"));
      } catch (err) {
        toast.error(t("file.importProjectZipFailed", { detail: String(err) }));
      }
    })();
  }, [t]);

  return { exportZip, importZip };
}
