/**
 * ManifestDiffDialog — §12 Reproducibility: 두 run manifest diff 뷰어
 *
 * 사용 흐름:
 *   1. 파일 메뉴 "Compare run manifests..." 또는 2개 .run.json 동시 드롭
 *   2. 두 manifest 로드 완료 후 이 모달 열림
 *   3. 4개 탭(meta / inputs / params / timing) 으로 diff 를 표 형식으로 표시
 *   4. status 별 색상: added=green, removed=red, changed=yellow, same=muted
 *   5. "Same" 항목 토글 (기본 숨김)
 *
 * 관련: src/lib/manifestDiff.ts
 */

import { useState, useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { type RunManifest } from "@/lib/runManifest";
import {
  diffManifests,
  type DiffEntry,
  type DiffStatus,
} from "@/lib/manifestDiff";

// ── 타입 ─────────────────────────────────────────────────────────────────────

export interface ManifestDiffDialogProps {
  open: boolean;
  manifestA: RunManifest | null;
  manifestB: RunManifest | null;
  onClose: () => void;
}

// ── status 별 스타일 ──────────────────────────────────────────────────────────

const STATUS_CLASSES: Record<DiffStatus, string> = {
  added: "bg-green-500/10 text-green-700 dark:text-green-400",
  removed: "bg-red-500/10 text-red-700 dark:text-red-400",
  changed: "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400",
  same: "text-muted-foreground",
};

const STATUS_BADGE_CLASSES: Record<DiffStatus, string> = {
  added: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400",
  removed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400",
  changed: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400",
  same: "bg-muted text-muted-foreground",
};

const STATUS_LABEL: Record<DiffStatus, string> = {
  added: "added",
  removed: "removed",
  changed: "changed",
  same: "same",
};

// ── 헬퍼: 값 렌더 ────────────────────────────────────────────────────────────

function renderValue(value: unknown): React.ReactNode {
  if (value === undefined) {
    return <span className="italic text-muted-foreground/60">—</span>;
  }
  if (value === null) {
    return <span className="italic text-muted-foreground/60">null</span>;
  }
  if (typeof value === "object" || Array.isArray(value)) {
    return (
      <pre className="text-xs whitespace-pre-wrap break-all max-w-xs overflow-x-auto rounded bg-muted px-1.5 py-1">
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  return <span className="font-mono text-xs">{String(value)}</span>;
}

// ── 탭 배지: 변경 건수 ────────────────────────────────────────────────────────

function changedCount(entries: DiffEntry[]): number {
  return entries.filter((e) => e.status !== "same").length;
}

// ── 섹션 헤더 ─────────────────────────────────────────────────────────────────

function SectionHeader({
  label,
  count,
}: {
  label: string;
  count: number;
}) {
  return (
    <div className="flex items-center gap-2 mb-1">
      <span className="font-medium text-sm text-foreground">{label}</span>
      {count > 0 && (
        <span
          className="inline-flex items-center rounded-full bg-yellow-100 dark:bg-yellow-900/40 px-2 py-0.5 text-xs font-medium text-yellow-700 dark:text-yellow-400"
          aria-label={`${count}개 변경`}
        >
          {count}
        </span>
      )}
    </div>
  );
}

// ── diff 표 컴포넌트 ──────────────────────────────────────────────────────────

interface DiffTableProps {
  entries: DiffEntry[];
  showSame: boolean;
}

function DiffTable({ entries, showSame }: DiffTableProps) {
  const visible = showSame ? entries : entries.filter((e) => e.status !== "same");

  if (visible.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        {showSame ? "항목 없음" : "변경된 항목 없음"}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-sm" aria-label="Manifest diff table">
        <thead>
          <tr className="border-b border-border bg-muted/40">
            <th
              scope="col"
              className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground w-48 min-w-0"
            >
              Path
            </th>
            <th
              scope="col"
              className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground"
            >
              A (before)
            </th>
            <th
              scope="col"
              className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground"
            >
              B (after)
            </th>
            <th
              scope="col"
              className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground w-24"
            >
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {visible.map((entry) => (
            <tr
              key={entry.path}
              className={`border-b border-border/50 last:border-b-0 ${STATUS_CLASSES[entry.status]}`}
            >
              <td className="px-3 py-2 font-mono text-xs break-all max-w-[12rem] min-w-0">
                {entry.path}
              </td>
              <td className="px-3 py-2 max-w-[16rem]">{renderValue(entry.left)}</td>
              <td className="px-3 py-2 max-w-[16rem]">{renderValue(entry.right)}</td>
              <td className="px-3 py-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE_CLASSES[entry.status]}`}
                >
                  {STATUS_LABEL[entry.status]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── 헤더 요약 카드 ────────────────────────────────────────────────────────────

interface ManifestSummaryCardProps {
  label: string;
  manifest: RunManifest;
}

function ManifestSummaryCard({ label, manifest }: ManifestSummaryCardProps) {
  return (
    <div className="flex-1 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs space-y-0.5">
      <p className="font-semibold text-foreground">{label}</p>
      <p className="text-muted-foreground">
        <span className="text-foreground/70">Method</span>{" "}
        <span className="font-mono">{manifest.method}</span>
      </p>
      <p className="text-muted-foreground">
        <span className="text-foreground/70">Version</span>{" "}
        <span className="font-mono">{manifest.kuma_version}</span>
      </p>
      <p className="text-muted-foreground">
        <span className="text-foreground/70">Started</span>{" "}
        <span className="font-mono">{manifest.started_at}</span>
      </p>
    </div>
  );
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────

export function ManifestDiffDialog({
  open,
  manifestA,
  manifestB,
  onClose,
}: ManifestDiffDialogProps) {
  const [showSame, setShowSame] = useState(false);

  const diff = useMemo(() => {
    if (!manifestA || !manifestB) return null;
    return diffManifests(manifestA, manifestB);
  }, [manifestA, manifestB]);

  if (!manifestA || !manifestB || !diff) return null;

  const totalChanged =
    changedCount(diff.meta) +
    changedCount(diff.inputs) +
    changedCount(diff.params) +
    changedCount(diff.timing);

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent
        className="max-w-3xl max-h-[90vh] flex flex-col"
        aria-label="Manifest diff dialog"
      >
        <DialogHeader>
          <DialogTitle>Run manifest 비교</DialogTitle>
          <DialogDescription>
            두 manifest 파일의 파라미터와 입력 파일 차이를 확인합니다.
            {totalChanged > 0
              ? ` 총 ${totalChanged}개 항목이 다릅니다.`
              : " 두 manifest 가 동일합니다."}
          </DialogDescription>
        </DialogHeader>

        {/* 두 manifest 요약 헤더 */}
        <div className="flex gap-3">
          <ManifestSummaryCard label="A (before)" manifest={manifestA} />
          <ManifestSummaryCard label="B (after)" manifest={manifestB} />
        </div>

        {/* "Same 항목 표시" 토글 */}
        <div className="flex items-center justify-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowSame((prev) => !prev)}
            aria-pressed={showSame}
            className="text-xs h-7 px-2"
          >
            {showSame ? "Same 숨기기" : "Same 표시"}
          </Button>
        </div>

        {/* diff 탭 */}
        <Tabs defaultValue="params" className="flex-1 overflow-hidden flex flex-col">
          <TabsList className="shrink-0">
            <TabsTrigger value="params">
              Params
              {changedCount(diff.params) > 0 && (
                <span className="ml-1.5 inline-flex items-center rounded-full bg-yellow-100 dark:bg-yellow-900/40 px-1.5 py-0.5 text-xs font-medium text-yellow-700 dark:text-yellow-400">
                  {changedCount(diff.params)}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="inputs">
              Inputs
              {changedCount(diff.inputs) > 0 && (
                <span className="ml-1.5 inline-flex items-center rounded-full bg-yellow-100 dark:bg-yellow-900/40 px-1.5 py-0.5 text-xs font-medium text-yellow-700 dark:text-yellow-400">
                  {changedCount(diff.inputs)}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="meta">
              Meta
              {changedCount(diff.meta) > 0 && (
                <span className="ml-1.5 inline-flex items-center rounded-full bg-yellow-100 dark:bg-yellow-900/40 px-1.5 py-0.5 text-xs font-medium text-yellow-700 dark:text-yellow-400">
                  {changedCount(diff.meta)}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="timing">
              Timing
              {changedCount(diff.timing) > 0 && (
                <span className="ml-1.5 inline-flex items-center rounded-full bg-yellow-100 dark:bg-yellow-900/40 px-1.5 py-0.5 text-xs font-medium text-yellow-700 dark:text-yellow-400">
                  {changedCount(diff.timing)}
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto mt-2">
            <TabsContent value="params" className="mt-0">
              <SectionHeader
                label="Parameters"
                count={changedCount(diff.params)}
              />
              <DiffTable entries={diff.params} showSame={showSame} />
            </TabsContent>

            <TabsContent value="inputs" className="mt-0">
              <SectionHeader
                label="Input files"
                count={changedCount(diff.inputs)}
              />
              <DiffTable entries={diff.inputs} showSame={showSame} />
            </TabsContent>

            <TabsContent value="meta" className="mt-0">
              <SectionHeader
                label="Metadata"
                count={changedCount(diff.meta)}
              />
              <DiffTable entries={diff.meta} showSame={showSame} />
            </TabsContent>

            <TabsContent value="timing" className="mt-0">
              <SectionHeader
                label="Timing"
                count={changedCount(diff.timing)}
              />
              <DiffTable entries={diff.timing} showSame={showSame} />
            </TabsContent>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
