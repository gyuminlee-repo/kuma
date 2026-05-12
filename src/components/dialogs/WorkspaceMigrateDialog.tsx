/**
 * WorkspaceMigrateDialog — §14 Schema dry-run migration modal.
 *
 * Shown when a workspace with an older schema_version is loaded.
 * Presents a confirmation UI with backup + migrate or cancel options.
 */

import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";

export interface MigrateDialogState {
  open: boolean;
  filePath: string;
  fromVersion: string;
  toVersion: string;
  /** true = no migration fn registered for this pair */
  noPath: boolean;
}

export const MIGRATE_DIALOG_CLOSED: MigrateDialogState = {
  open: false,
  filePath: "",
  fromVersion: "",
  toVersion: "",
  noPath: false,
};

interface WorkspaceMigrateDialogProps {
  state: MigrateDialogState;
  /** Called when user confirms migration. Caller is responsible for backup + migrate + load. */
  onConfirm: () => Promise<void>;
  /** Called when user cancels. Caller clears dialog state. */
  onCancel: () => void;
  /** True while backup/migrate is in progress */
  loading?: boolean;
}

export function WorkspaceMigrateDialog({
  state,
  onConfirm,
  onCancel,
  loading = false,
}: WorkspaceMigrateDialogProps) {
  const { t } = useTranslation();
  const { open, filePath, fromVersion, toVersion, noPath } = state;

  return (
    <Dialog open={open}>
      <DialogContent
        aria-modal="true"
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{t("workspaceMigrate.title")}</DialogTitle>
          <DialogDescription>
            {t("workspaceMigrate.description", { from: fromVersion, to: toVersion })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm text-foreground">
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-caption text-muted-foreground break-all">
            {filePath}
          </div>

          {noPath ? (
            <p className="text-warning text-sm" role="alert">
              {t("workspaceMigrate.noPathAlert")}
            </p>
          ) : (
            <>
              <p>
                {t("workspaceMigrate.migratingWillTitle")}
              </p>
              <ul className="ml-4 list-disc space-y-1 text-sm text-muted-foreground">
                <li>
                  {t("workspaceMigrate.backupItem", { template: "<filename>.backup-<timestamp>.json" })}
                </li>
                <li>
                  {t("workspaceMigrate.convertItem", { toVersion })}
                </li>
                <li>{t("workspaceMigrate.loadItem")}</li>
              </ul>
              <p className="text-caption text-muted-foreground">
                {t("workspaceMigrate.backupNote")}
              </p>
            </>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={loading}
            aria-label={t("workspaceMigrate.cancelAriaLabel")}
          >
            {t("workspaceMigrate.cancelBtn")}
          </Button>
          {!noPath && (
            <Button
              onClick={() => void onConfirm()}
              disabled={loading}
              aria-label={t("workspaceMigrate.migrateAriaLabel")}
            >
              {loading ? t("workspaceMigrate.migratingBtn") : t("workspaceMigrate.migrateBtn")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
