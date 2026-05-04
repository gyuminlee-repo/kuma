/**
 * ActivityUploadPanel — 활성 데이터 파일 업로드 패널
 *
 * - CSV/Excel 파일을 Tauri open dialog로 선택
 * - format select: long_csv | long_xlsx
 * - uploadActivityFile RPC 호출
 * - 업로드 결과 (n records) 및 오류 표시
 *
 * Spec: notes/specs/2026-05-04-mame-activity-integration.md §4.4
 */

import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useActivityStore, type ActivitySlice } from "@/store/mame/activitySlice";
import { useRoundStore } from "@/store/round/roundSlice";
import { useStore } from "zustand";
import { Upload } from "lucide-react";

type ActivityFormat = "long_csv" | "long_xlsx";

const FORMAT_LABELS: Record<ActivityFormat, string> = {
  long_csv: "Long CSV",
  long_xlsx: "Long Excel",
};

export function ActivityUploadPanel() {
  const [format, setFormat] = useState<ActivityFormat>("long_csv");

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

    const extensions = format === "long_csv" ? ["csv"] : ["xlsx", "xls"];
    const selected = await open({
      multiple: false,
      filters: [
        {
          name: format === "long_csv" ? "CSV files" : "Excel files",
          extensions,
        },
      ],
      title: "Select activity data file",
    });

    if (typeof selected !== "string") return;

    await uploadActivityFile(activeRoundId, selected, format);
  }

  return (
    <div className="space-y-2" aria-label="Activity data upload">
      <div className="space-y-1">
        <Label
          htmlFor="activity-format-select"
          className="text-caption font-medium uppercase tracking-wide text-muted-foreground"
        >
          Format
        </Label>
        <Select
          value={format}
          onValueChange={(v) => setFormat(v as ActivityFormat)}
        >
          <SelectTrigger
            id="activity-format-select"
            className="h-8 min-w-0 text-xs"
            aria-label="Activity file format"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(["long_csv", "long_xlsx"] as const).map((f) => (
              <SelectItem key={f} value={f} className="text-xs">
                {FORMAT_LABELS[f]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-full text-xs"
        onClick={() => void handleUpload()}
        disabled={disabled}
        aria-busy={isUploading}
        aria-label={isUploading ? "Uploading activity data…" : "Browse & Upload activity file"}
      >
        <Upload size={12} aria-hidden="true" className="mr-1.5" />
        {isUploading ? "Uploading…" : "Browse & Upload"}
      </Button>

      {recordCount > 0 && (
        <p
          className="text-caption text-muted-foreground"
          aria-live="polite"
          role="status"
        >
          {recordCount} wells loaded
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
