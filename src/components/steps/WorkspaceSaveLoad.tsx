/**
 * WorkspaceSaveLoad — workspace save/load buttons.
 *
 * [source: spec §1 — "export.workspace: exportSlice.getWorkspaceSnapshot / loadWorkspace"]
 *
 * Calls handleSaveWorkspace / handleLoadWorkspace from export-handlers.
 *
 * v1: workspace migration dialog (WorkspaceMigrateDialog) is not wired here.
 * handleLoadWorkspace requires onMigrationNeeded callback; v1 passes a no-op.
 * TODO Stage 3: wire WorkspaceMigrateDialog properly (mirror MenuBar migration flow).
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  handleSaveWorkspace,
  handleLoadWorkspace,
} from "@/components/layout/export-handlers";
import { useKumaProject } from "@/state/projectContext";

export function WorkspaceSaveLoad() {
  const { t } = useTranslation();
  const project = useKumaProject();
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSave = async () => {
    if (!project) return;
    setIsSaving(true);
    try {
      await handleSaveWorkspace(project);
    } finally {
      setIsSaving(false);
    }
  };

  const handleLoad = async () => {
    if (!project) return;
    setIsLoading(true);
    try {
      // TODO Stage 3: wire WorkspaceMigrateDialog (migration flow)
      // Currently passes a no-op to onMigrationNeeded.
      await handleLoadWorkspace(project, () => {
        // no-op: migration dialog wiring deferred to Stage 3
      });
    } finally {
      setIsLoading(false);
    }
  };

  const noProject = !project;

  return (
    <div
      className="flex flex-col gap-4 p-6"
      role="region"
      aria-label={t("phaseC.subSteps.export.workspace")}
    >
      <h3 className="text-sm font-semibold text-foreground">
        {t("phaseC.subSteps.export.workspace")}
      </h3>
      {noProject && (
        <p className="text-xs text-muted-foreground">
          {/* No project open — workspace save/load requires a project */}
          Open a project to enable workspace save / load.
        </p>
      )}
      <div className="flex gap-3">
        <Button
          variant="default"
          onClick={() => void handleSave()}
          disabled={isSaving || noProject}
        >
          {isSaving ? t("common.loading") : t("phaseC.export.workspace.save")}
        </Button>
        <Button
          variant="outline"
          onClick={() => void handleLoad()}
          disabled={isLoading || noProject}
        >
          {isLoading ? t("common.loading") : t("phaseC.export.workspace.load")}
        </Button>
      </div>
    </div>
  );
}
