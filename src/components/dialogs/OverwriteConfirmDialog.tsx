/**
 * §5 Output Persistence — 덮어쓰기 확인 다이얼로그.
 *
 * `overwriteConfirm.ts`의 전역 Promise 패턴과 연결되어
 * export 직전 파일이 존재할 때 사용자에게 확인을 요청한다.
 */

import { useEffect, useSyncExternalStore } from "react";
import {
  subscribeOverwriteConfirm,
  getPendingOverwritePath,
  resolveOverwriteConfirm,
} from "@/lib/overwriteConfirm";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

function getSnapshot() {
  return getPendingOverwritePath();
}

export function OverwriteConfirmDialog() {
  const pendingPath = useSyncExternalStore(subscribeOverwriteConfirm, getSnapshot);
  const open = pendingPath !== null;

  // ESC 또는 backdrop 클릭 → cancel
  function handleOpenChange(next: boolean) {
    if (!next) resolveOverwriteConfirm("cancel");
  }

  // 키보드 Enter → overwrite (포커스가 Overwrite 버튼에 있을 때)
  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        resolveOverwriteConfirm("cancel");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const filename = pendingPath ? pendingPath.split(/[\\/]/).pop() ?? pendingPath : "";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>File already exists</DialogTitle>
          <DialogDescription>
            <span className="font-mono text-foreground break-all">{filename}</span>
            {" "}already exists. Do you want to overwrite it?
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <Button
            variant="outline"
            size="sm"
            onClick={() => resolveOverwriteConfirm("cancel")}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => resolveOverwriteConfirm("overwrite")}
            // eslint-disable-next-line jsx-a11y/no-autofocus
            autoFocus
          >
            Overwrite
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
