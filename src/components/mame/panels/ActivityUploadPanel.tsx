/**
 * ActivityUploadPanel — 활성 데이터 파일 업로드 패널
 *
 * - CSV/Excel 파일을 Tauri open dialog로 선택
 * - 파일 확장자로 format 자동 감지 (long_csv | long_xlsx)
 * - uploadActivityFile RPC 호출
 * - 업로드 결과 (n records) 및 오류 표시
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4.4
 */

import { useTranslation } from "react-i18next";
import { open } from "@tauri-apps/plugin-dialog";
import { Button } from "@/components/ui/button";
import { useActivityStore, type ActivitySlice } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { useStore } from "zustand";
import { Upload } from "lucide-react";

type ActivityFormat = "long_csv" | "long_xlsx";

function inferFormat(path: string): ActivityFormat {
  const lower = path.toLowerCase();
  if (lower.endsWith(".csv")) return "long_csv";
  return "long_xlsx"; // .xlsx | .xls
}

export function ActivityUploadPanel() {
  const { t } = useTranslation();

  const activeRoundId = useRoundStore((s) => s.active_round_id);
  const activeRound = useRoundStore((s) =>
    s.rounds.find((r) => r.id === activeRoundId) ?? null
  );

  const activityStore = useActivityStore();
  const isUploading = useStore(activityStore, (s: ActivitySlice) => s.isUploading);
  const uploadError = useStore(activityStore, (s: ActivitySlice) => s.uploadError);
  const uploadActivityFile = useStore(activityStore, (s: ActivitySlice) => s.uploadActivityFile);

  const recordCount = activeRound?.activity?.records.length ?? 0;
  const disabled = !activeRoundId || isUploading;

  async function handleUpload() {
    if (!activeRoundId) return;

    const selected = await open({
      multiple: false,
      filters: [
        {
          name: "Activity data",
          extensions: ["csv", "xlsx", "xls"],
        },
      ],
      title: "Select activity data file",
    });

    if (typeof selected !== "string") return;

    const format = inferFormat(selected);
    await uploadActivityFile(activeRoundId, selected, format);
  }

  return (
    <div className="space-y-2" aria-label={t("activityUpload.panelAriaLabel")}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-full text-xs"
        onClick={() => void handleUpload()}
        disabled={disabled}
        aria-busy={isUploading}
        aria-label={isUploading ? t("activityUpload.uploadingAriaLabel") : t("activityUpload.browseAriaLabel")}
      >
        <Upload size={12} aria-hidden="true" className="mr-1.5" />
        {isUploading ? t("activityUpload.uploadingBtn") : t("activityUpload.browseBtn")}
      </Button>

      {recordCount > 0 && (
        <p
          className="text-caption text-muted-foreground"
          aria-live="polite"
          role="status"
        >
          {t("activityUpload.recordsLoaded", { count: recordCount })}
        </p>
      )}

      {uploadError && (
        <div
          role="alert"
          className="rounded-md bg-destructive/10 px-3 py-2 text-caption text-destructive"
        >
          {uploadError}
        </div>
      )}
    </div>
  );
}
