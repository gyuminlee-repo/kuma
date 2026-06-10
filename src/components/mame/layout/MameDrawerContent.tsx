/**
 * MameDrawerContent — MAME 7화면 하단 DrawerStrip 3-슬롯 콘텐츠.
 *
 * currentMameSubStep에 따라 mockup의 3-슬롯 컨트랙트를 반환한다.
 * Left: minirow (상태 요약), Center: log, Right: shortcut/next hint.
 *
 * Rules of Hooks 준수: 모든 슬롯 데이터는 최상위에서 선택자로 읽고,
 * 화면별 분기는 순수 함수에서 처리한다.
 *
 * [source: v5-strategy.md §6.2 MAME 7화면 contract matrix]
 */

import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";
import type { DrawerStripProps } from "@/components/widgets/DrawerStrip";

function StatLine({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-1 text-[11px]">
      <span className="text-muted-foreground">{label}:</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}

function LogLine({ text }: { text: string }) {
  return (
    <p className="truncate text-[11px] font-mono text-muted-foreground">{text}</p>
  );
}

type SlotProps = DrawerStripProps;

/** 단일 훅에서 모든 상태를 읽고 sub-step별 SlotProps를 순수 함수로 계산 */
export function useMameDrawerProps(): SlotProps {
  const { t } = useTranslation();

  // 모든 상태를 최상위에서 선언 (훅 순서 고정)
  const currentSubStep = useMameAppStore((s) => s.currentMameSubStep);
  const inputDir = useMameAppStore((s) => s.inputDir);
  const expectedPath = useMameAppStore((s) => s.expectedPath);
  const isAnalyzing = useMameAppStore((s) => s.isAnalyzing);
  const analyzeMessage = useMameAppStore((s) => s.analyzeMessage);
  const verdicts = useMameAppStore((s) => s.verdicts);
  const summary = useMameAppStore((s) => s.summary);
  const wells = useMameAppStore((s) => s.wells);
  const selectedWell = useMameAppStore((s) => s.selectedWell);

  // 파생 값
  const runFolderName = inputDir
    ? (inputDir.replace(/\\/g, "/").split("/").filter(Boolean).pop() ?? inputDir)
    : "—";
  const kuroFileName = expectedPath
    ? (expectedPath.replace(/\\/g, "/").split("/").filter(Boolean).pop() ?? expectedPath)
    : "—";
  const passCount = verdicts.filter((v) => v.verdict === "PASS").length;
  const selectedCount = wells.filter((w) => w.selected).length;

  const MAP: Record<MameSubStepId, SlotProps> = {
    "setup.files": {
      left: {
        title: t("mame.setup.files.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine label={t("mame.drawer.stat.folder")} value={runFolderName} />
            <StatLine label={t("mame.drawer.stat.status")} value={inputDir ? t("mame.drawer.value.ready") : t("mame.drawer.value.notSet")} />
          </div>
        ),
      },
      center: {
        title: t("mame.setup.files.drawerCenter"),
        children: (
          <div className="space-y-0.5">
            <LogLine
              text={
                inputDir
                  ? `[INFO] Scanned: ${runFolderName}`
                  : "[WAIT] Select a run folder"
              }
            />
            <LogLine text="[INFO] fastq_pass/ pattern detection active" />
          </div>
        ),
      },
      right: {
        title: t("mame.setup.files.drawerRight"),
        children: <LogLine text={t("mame.setup.files.drawerRightDesc")} />,
      },
    },

    "setup.design": {
      left: {
        title: t("mame.setup.design.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine label={t("mame.drawer.stat.file")} value={kuroFileName} />
            <StatLine label={t("mame.drawer.stat.status")} value={expectedPath ? t("mame.drawer.value.loaded") : t("mame.drawer.value.notSet")} />
          </div>
        ),
      },
      center: {
        title: t("mame.setup.design.drawerCenter"),
        children: (
          <div className="space-y-0.5">
            <LogLine
              text={
                expectedPath
                  ? `[INFO] Mapped: ${kuroFileName}`
                  : "[WAIT] Load KURO xlsx"
              }
            />
            <LogLine text="[INFO] Barcode-variant mapping ready" />
          </div>
        ),
      },
      right: {
        title: t("mame.setup.design.drawerRight"),
        children: <LogLine text={t("mame.setup.design.drawerRightDesc")} />,
      },
    },

    "analyze.inputs": {
      left: {
        title: t("mame.qc.inputs.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine
              label={t("mame.drawer.stat.queued")}
              value={verdicts.length > 0 ? verdicts.length : "—"}
            />
            <StatLine label={t("mame.drawer.stat.status")} value={isAnalyzing ? t("mame.drawer.value.running") : t("mame.drawer.value.idle")} />
          </div>
        ),
      },
      center: {
        title: t("mame.qc.inputs.drawerCenter"),
        children: (
          <div className="space-y-0.5">
            <LogLine
              text={
                analyzeMessage ||
                (isAnalyzing ? "[RUN] Analysis in progress..." : "[WAIT] Ready to run")
              }
            />
            <LogLine text="[INFO] Pre-flight check will run on start" />
          </div>
        ),
      },
      right: {
        title: t("mame.qc.inputs.drawerRight"),
        children: <LogLine text={t("mame.qc.inputs.drawerRightDesc")} />,
      },
    },

    "analyze.review": {
      left: {
        title: t("mame.qc.review.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine label={t("mame.drawer.stat.total")} value={summary?.total ?? verdicts.length} />
            <StatLine label={t("mame.drawer.stat.pass")} value={summary?.pass_count ?? 0} />
            <StatLine label={t("mame.drawer.stat.selected")} value={selectedCount} />
          </div>
        ),
      },
      center: {
        title: t("mame.qc.review.drawerCenter"),
        children: (
          <div className="space-y-0.5">
            <LogLine
              text={
                verdicts.length > 0
                  ? `[DONE] ${verdicts.length} barcodes processed`
                  : "[WAIT] No results yet"
              }
            />
            <LogLine
              text={
                selectedWell
                  ? `[SEL] ${selectedWell.well}: ${selectedWell.verdict}`
                  : "[INFO] Click a well to inspect"
              }
            />
          </div>
        ),
      },
      right: {
        title: t("mame.qc.review.drawerRight"),
        children: <LogLine text={t("mame.qc.review.drawerRightDesc")} />,
      },
    },

    // Legacy ids retained so MAP lookup never returns undefined during redirect.
    "analyze.verdict": {
      left: { title: t("mame.qc.review.drawerLeft"), children: null },
      center: { title: t("mame.qc.review.drawerCenter"), children: null },
      right: { title: t("mame.qc.review.drawerRight"), children: null },
    },

    "analyze.plate": {
      left: {
        title: t("mame.qc.plate.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine label={t("mame.drawer.stat.selected")} value={selectedCount} />
            <StatLine label={t("mame.drawer.stat.totalWells")} value={wells.length} />
          </div>
        ),
      },
      center: {
        title: t("mame.qc.plate.drawerCenter"),
        children: (
          <div className="space-y-0.5">
            <LogLine
              text={
                selectedWell
                  ? `[SEL] ${selectedWell.well}: ${selectedWell.verdict}`
                  : "[INFO] Click a well to inspect"
              }
            />
            <LogLine text={`[INFO] ${selectedCount} wells selected for pick`} />
          </div>
        ),
      },
      right: {
        title: t("mame.qc.plate.drawerRight"),
        children: <LogLine text={t("mame.qc.plate.drawerRightDesc")} />,
      },
    },

    "activity.ingest": {
      left: {
        title: t("mame.activity.ingest.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine
              label={t("mame.drawer.stat.wells")}
              value={verdicts.length > 0 ? verdicts.length : "—"}
            />
            <StatLine label={t("mame.drawer.stat.loaded")} value={verdicts.length > 0 ? t("mame.drawer.value.yes") : t("mame.drawer.value.no")} />
          </div>
        ),
      },
      center: {
        title: t("mame.activity.ingest.drawerCenter"),
        children: (
          <div className="space-y-0.5">
            <LogLine text="[INFO] Upload CSV/Excel with activity measurements" />
            <LogLine text="[INFO] Required columns: well, replicate, value" />
          </div>
        ),
      },
      right: {
        title: t("mame.activity.ingest.drawerRight"),
        children: <LogLine text={t("mame.activity.ingest.drawerRightDesc")} />,
      },
    },

    "activity.mergeExport": {
      left: {
        title: t("mame.activity.mergeExport.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine label={t("mame.drawer.stat.passRows")} value={passCount} />
            <StatLine label={t("mame.drawer.stat.evolveproXlsx")} value={passCount > 0 ? t("mame.drawer.value.ready") : "—"} />
          </div>
        ),
      },
      center: {
        title: t("mame.activity.mergeExport.drawerCenter"),
        children: (
          <div className="space-y-0.5">
            <LogLine
              text={
                passCount > 0
                  ? `[DONE] ${passCount} rows merged`
                  : "[WAIT] Merge not performed yet"
              }
            />
            <LogLine text="[INFO] Bidirectional bridge to KURO" />
          </div>
        ),
      },
      right: {
        title: t("mame.activity.mergeExport.drawerRight"),
        children: <LogLine text={t("mame.activity.mergeExport.drawerRightDesc")} />,
      },
    },
  };

  return MAP[currentSubStep] ?? {};
}
