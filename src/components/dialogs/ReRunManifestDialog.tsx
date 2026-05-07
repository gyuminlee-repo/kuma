/**
 * ReRunManifestDialog — §12 Reproducibility: manifest 재현 실행 확인 모달
 *
 * 사용 흐름:
 *   1. DnD 또는 메뉴 "Open run manifest..." → manifest 로드
 *   2. 이 모달 열림 → 사용자에게 method, inputs, params 요약 표시
 *   3. SHA-256 불일치 경고 표시 (있을 경우)
 *   4. "Re-run" 클릭 → reRunFromManifest 실행
 */

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { type RunManifest } from "@/lib/runManifest";
import { reRunFromManifest, type InputVerifyResult } from "@/lib/reRun";

// ── 타입 ─────────────────────────────────────────────────────────────────────

export interface ReRunManifestDialogProps {
  open: boolean;
  manifest: RunManifest | null;
  /** 검증 결과 (비동기로 선계산된 값) */
  verifyResult: InputVerifyResult | null;
  /** 모달 닫기 콜백 */
  onClose: () => void;
  /** re-run 완료 후 상태 메시지 표시 콜백 */
  onStatusMessage: (msg: string) => void;
}

// ── 헬퍼 ─────────────────────────────────────────────────────────────────────

function methodLabel(method: string): string {
  switch (method) {
    case "design_sdm_primers": return "Kuro — SDM primer design";
    case "merge_for_evolvepro": return "Mame — merge for EVOLVEpro";
    case "export_order": return "Export: order sheet (re-run 불가)";
    case "export_mapping": return "Export: plate mapping (re-run 불가)";
    case "export_excel": return "Export: Excel (re-run 불가)";
    default: return method;
  }
}

const EXPORT_ONLY = new Set(["export_order", "export_mapping", "export_excel"]);

// ── 컴포넌트 ─────────────────────────────────────────────────────────────────

export function ReRunManifestDialog({
  open,
  manifest,
  verifyResult,
  onClose,
  onStatusMessage,
}: ReRunManifestDialogProps) {
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  if (!manifest) return null;

  const isExportOnly = EXPORT_ONLY.has(manifest.method);
  const inputKeys = Object.keys(manifest.inputs);
  const paramKeys = Object.keys(manifest.params);
  const hasMismatch =
    verifyResult !== null &&
    (verifyResult.mismatched.length > 0 || verifyResult.missing.length > 0);

  async function handleReRun() {
    if (!manifest) return;
    setRunning(true);
    setRunError(null);
    try {
      await reRunFromManifest(manifest);
      onStatusMessage(`Re-run 완료: ${manifest.method}`);
      onClose();
    } catch (err) {
      setRunError(String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v && !running) onClose(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>재현 실행 확인</DialogTitle>
          <DialogDescription>
            저장된 manifest 에서 동일한 작업을 재현합니다.
          </DialogDescription>
        </DialogHeader>

        {/* manifest 요약 */}
        <div className="space-y-3 text-sm">
          {/* method */}
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">Method</span>
            <span className="font-medium text-foreground">{methodLabel(manifest.method)}</span>
          </div>

          {/* kuma version */}
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">kuma version</span>
            <span className="text-foreground">{manifest.kuma_version}</span>
          </div>

          {/* platform */}
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">Platform</span>
            <span className="text-foreground">{manifest.platform} / Python {manifest.python_version}</span>
          </div>

          {/* inputs */}
          {inputKeys.length > 0 && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">Inputs</span>
              <ul className="space-y-0.5 text-foreground">
                {inputKeys.map((k) => (
                  <li key={k} className="truncate max-w-xs">
                    <span className="text-muted-foreground">{k}:</span>{" "}
                    <span className="font-mono text-xs">{manifest.inputs[k].path}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* params 개수 */}
          {paramKeys.length > 0 && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">Params</span>
              <span className="text-foreground">{paramKeys.length}개 매개변수</span>
            </div>
          )}

          {/* seed */}
          {manifest.seed !== null && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">Seed</span>
              <span className="text-foreground font-mono">{manifest.seed}</span>
            </div>
          )}
        </div>

        {/* SHA-256 불일치 경고 */}
        {hasMismatch && (
          <div
            role="alert"
            className="rounded-md border border-warning/40 bg-warning/8 px-3 py-2 text-sm text-warning"
          >
            <p className="font-semibold">입력 파일이 변경되었습니다.</p>
            <p className="mt-0.5 text-warning/80">
              동일 결과가 보장되지 않습니다. 계속 진행하시겠습니까?
            </p>
            {verifyResult!.missing.length > 0 && (
              <p className="mt-0.5">
                경로 없음: {verifyResult!.missing.join(", ")}
              </p>
            )}
            {verifyResult!.mismatched.length > 0 && (
              <p className="mt-0.5">
                해시 불일치: {verifyResult!.mismatched.join(", ")}
              </p>
            )}
          </div>
        )}

        {/* export-only 안내 */}
        {isExportOnly && (
          <div
            role="status"
            className="rounded-md border border-border bg-muted px-3 py-2 text-sm text-muted-foreground"
          >
            이 manifest 는 export 작업입니다. 직접 re-run 할 수 없습니다.
            원본 데이터에서 다시 export 하세요.
          </div>
        )}

        {/* run 에러 */}
        {runError !== null && (
          <div
            role="alert"
            className="rounded-md border border-error/40 bg-error/8 px-3 py-2 text-sm text-error"
          >
            {runError}
          </div>
        )}

        <DialogFooter className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={running}
          >
            취소
          </Button>
          <Button
            size="sm"
            onClick={() => { void handleReRun(); }}
            disabled={running || isExportOnly}
            aria-busy={running}
          >
            {running ? "실행 중…" : "Re-run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
