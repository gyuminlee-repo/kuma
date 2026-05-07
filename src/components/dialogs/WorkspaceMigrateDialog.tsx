/**
 * WorkspaceMigrateDialog — §14 Schema dry-run migration modal.
 *
 * Shown when a workspace with an older schema_version is loaded.
 * Presents a confirmation UI with backup + migrate or cancel options.
 */

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
  const { open, filePath, fromVersion, toVersion, noPath } = state;

  return (
    <Dialog open={open}>
      <DialogContent
        aria-modal="true"
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Workspace Version Mismatch</DialogTitle>
          <DialogDescription>
            The selected workspace uses schema version{" "}
            <strong className="text-foreground">{fromVersion}</strong>, but the
            current app requires{" "}
            <strong className="text-foreground">{toVersion}</strong>.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm text-foreground">
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-caption text-muted-foreground break-all">
            {filePath}
          </div>

          {noPath ? (
            <p className="text-warning text-sm" role="alert">
              No automatic migration is defined for this version pair. Manual
              upgrade is required — the workspace cannot be loaded.
            </p>
          ) : (
            <>
              <p>
                Migrating will:
              </p>
              <ul className="ml-4 list-disc space-y-1 text-sm text-muted-foreground">
                <li>
                  Create a backup copy:{" "}
                  <span className="font-mono text-xs">
                    {"<filename>.backup-<timestamp>.json"}
                  </span>
                </li>
                <li>
                  Convert the workspace to version{" "}
                  <strong>{toVersion}</strong>
                </li>
                <li>Load the converted workspace</li>
              </ul>
              <p className="text-caption text-muted-foreground">
                The original file is preserved as a backup. Migration cannot be
                undone automatically — restore the backup manually if needed.
              </p>
            </>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={loading}
            aria-label="Cancel workspace load"
          >
            Cancel
          </Button>
          {!noPath && (
            <Button
              onClick={() => void onConfirm()}
              disabled={loading}
              aria-label="Backup original file and migrate workspace"
            >
              {loading ? "Migrating…" : "Migrate (Backup + Convert)"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
