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
import { useTranslation } from "react-i18next";
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

const EXPORT_ONLY = new Set(["export_order", "export_mapping", "export_excel"]);

// ── 컴포넌트 ─────────────────────────────────────────────────────────────────

export function ReRunManifestDialog({
  open,
  manifest,
  verifyResult,
  onClose,
  onStatusMessage,
}: ReRunManifestDialogProps) {
  const { t } = useTranslation();
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
      onStatusMessage(t("reRunManifest.statusDone", { method: manifest.method }));
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
          <DialogTitle>{t("reRunManifest.title")}</DialogTitle>
          <DialogDescription>
            {t("reRunManifest.description")}
          </DialogDescription>
        </DialogHeader>

        {/* manifest 요약 */}
        <div className="space-y-3 text-sm">
          {/* method */}
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">{t("reRunManifest.labelMethod")}</span>
            <span className="font-medium text-foreground">{t(`reRunManifest.method.${manifest.method}`, { defaultValue: manifest.method })}</span>
          </div>

          {/* kuma version */}
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">{t("reRunManifest.labelVersion")}</span>
            <span className="text-foreground">{manifest.kuma_version}</span>
          </div>

          {/* platform */}
          <div className="flex gap-2">
            <span className="w-28 shrink-0 text-muted-foreground">{t("reRunManifest.labelPlatform")}</span>
            <span className="text-foreground">{t("reRunManifest.labelPlatformValue", { platform: manifest.platform, pythonVersion: manifest.python_version })}</span>
          </div>

          {/* inputs */}
          {inputKeys.length > 0 && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">{t("reRunManifest.labelInputs")}</span>
              <ul className="space-y-0.5 text-foreground">
                {inputKeys.map((k) => (
                  <li key={k} className="break-all" title={manifest.inputs[k].path}>
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
              <span className="w-28 shrink-0 text-muted-foreground">{t("reRunManifest.labelParams")}</span>
              <span className="text-foreground">{t("reRunManifest.labelParamsValue", { count: paramKeys.length })}</span>
            </div>
          )}

          {/* seed */}
          {manifest.seed !== null && (
            <div className="flex gap-2">
              <span className="w-28 shrink-0 text-muted-foreground">{t("reRunManifest.labelSeed")}</span>
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
            <p className="font-semibold">{t("reRunManifest.warningTitle")}</p>
            <p className="mt-0.5 text-warning/80">
              {t("reRunManifest.warningBody")}
            </p>
            {verifyResult!.missing.length > 0 && (
              <p className="mt-0.5">
                {t("reRunManifest.warningMissingPaths", { paths: verifyResult!.missing.join(", ") })}
              </p>
            )}
            {verifyResult!.mismatched.length > 0 && (
              <p className="mt-0.5">
                {t("reRunManifest.warningHashMismatch", { paths: verifyResult!.mismatched.join(", ") })}
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
            {t("reRunManifest.exportOnlyNotice")}
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
            {t("reRunManifest.btnCancel")}
          </Button>
          <Button
            size="sm"
            onClick={() => { void handleReRun(); }}
            disabled={running || isExportOnly}
            aria-busy={running}
          >
            {running ? t("reRunManifest.btnRunning") : t("reRunManifest.btnRerun")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
