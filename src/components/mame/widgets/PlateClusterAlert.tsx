/**
 * PlateClusterAlert — 인접 well 동시 실패(clustered failure) 경고 컴포넌트.
 *
 * wells 배열에서 동일 행 연속 열 위치에 FAIL/LOWDEPTH 판정이 2개 이상 연속으로 나타나는
 * 패턴을 감지하고, 감지 시 좌측 패널에 경고 메시지를 표시한다.
 *
 * 예: B03(FAIL) + B04(FAIL) → "B03-B04 may indicate a pipetting issue"
 *
 * [source: v5-audit.md §GAP P2 — MAME/Analyze/Plate clustered-failure pattern alert]
 */

import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { WellEntry } from "@/types/mame/models";

type VerdictClass = WellEntry["verdict"];

const FAIL_VERDICTS: Set<VerdictClass> = new Set(["LOWDEPTH", "FRAMESHIFT", "MANY", "WRONG_AA"]);

type ClusterGroup = {
  wells: string[];
  row: string;
};

/**
 * 96-well 좌표를 행 문자(A-H)와 열 번호(1-12)로 파싱.
 * 유효하지 않으면 null 반환.
 */
function parseWellCoord(well: string): { row: string; col: number } | null {
  const match = /^([A-H])(\d{1,2})$/.exec(well.trim().toUpperCase());
  if (!match) return null;
  const col = parseInt(match[2], 10);
  if (col < 1 || col > 12) return null;
  return { row: match[1], col };
}

/**
 * wells 목록에서 인접 실패 클러스터를 감지.
 * 반환: 클러스터 그룹 배열 (각 그룹은 동일 행 연속 실패 well 목록).
 */
export function detectFailClusters(wells: WellEntry[]): ClusterGroup[] {
  // 실패 well만 필터
  const failWells = wells.filter((w) => FAIL_VERDICTS.has(w.verdict));

  // 행별로 그룹화 후 열 번호 정렬
  const byRow = new Map<string, number[]>();
  for (const w of failWells) {
    const coord = parseWellCoord(w.well);
    if (!coord) continue;
    const cols = byRow.get(coord.row) ?? [];
    cols.push(coord.col);
    byRow.set(coord.row, cols);
  }

  const clusters: ClusterGroup[] = [];

  for (const [row, cols] of byRow) {
    const sorted = [...new Set(cols)].sort((a, b) => a - b);
    let runStart = 0;

    while (runStart < sorted.length) {
      let runEnd = runStart;
      // 연속 구간 탐색
      while (runEnd + 1 < sorted.length && sorted[runEnd + 1] === sorted[runEnd] + 1) {
        runEnd++;
      }
      const runLen = runEnd - runStart + 1;
      if (runLen >= 2) {
        const wellNames = sorted
          .slice(runStart, runEnd + 1)
          .map((c) => `${row}${String(c).padStart(2, "0")}`);
        clusters.push({ wells: wellNames, row });
      }
      runStart = runEnd + 1;
    }
  }

  return clusters;
}

/** 클러스터 그룹을 사람이 읽기 좋은 범위 문자열로 변환. 예: ["B03","B04"] → "B03-B04" */
function formatClusterRange(group: ClusterGroup): string {
  if (group.wells.length === 0) return "";
  if (group.wells.length === 1) return group.wells[0];
  return `${group.wells[0]}-${group.wells[group.wells.length - 1]}`;
}

export function PlateClusterAlert() {
  const { t } = useTranslation();
  const wells = useMameAppStore((s) => s.wells);

  if (wells.length === 0) return null;

  const clusters = detectFailClusters(wells);
  if (clusters.length === 0) return null;

  return (
    <div
      role="alert"
      aria-label={t("mame.qc.plate.clusterAlertAriaLabel")}
      className="flex items-start gap-2 rounded border border-warning/40 bg-warning/8 px-3 py-2 text-xs"
    >
      <AlertTriangle
        size={13}
        className="mt-0.5 shrink-0 text-warning"
        aria-hidden="true"
      />
      <div className="min-w-0 space-y-1">
        <p className="font-semibold text-warning">
          {t("mame.qc.plate.clusterAlertTitle")}
        </p>
        {clusters.map((group) => (
          <p key={`${group.row}-${group.wells[0]}`} className="text-muted-foreground">
            {t("mame.qc.plate.clusterAlertDesc", {
              wells: formatClusterRange(group),
            })}
          </p>
        ))}
      </div>
    </div>
  );
}
