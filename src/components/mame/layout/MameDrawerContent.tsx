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
            <StatLine label="Folder" value={runFolderName} />
            <StatLine label="Status" value={inputDir ? "Ready" : "Not set"} />
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
            <StatLine label="File" value={kuroFileName} />
            <StatLine label="Status" value={expectedPath ? "Loaded" : "Not set"} />
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
              label="Queued"
              value={verdicts.length > 0 ? verdicts.length : "—"}
            />
            <StatLine label="Status" value={isAnalyzing ? "Running" : "Idle"} />
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

    "analyze.verdict": {
      left: {
        title: t("mame.qc.verdict.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine label="Total" value={summary?.total ?? verdicts.length} />
            <StatLine label="PASS" value={summary?.pass_count ?? 0} />
          </div>
        ),
      },
      center: {
        title: t("mame.qc.verdict.drawerCenter"),
        children: (
          <div className="space-y-0.5">
            <LogLine
              text={
                verdicts.length > 0
                  ? `[DONE] ${verdicts.length} barcodes processed`
                  : "[WAIT] No results yet"
              }
            />
            <LogLine text="[INFO] Consensus called per barcode" />
          </div>
        ),
      },
      right: {
        title: t("mame.qc.verdict.drawerRight"),
        children: <LogLine text={t("mame.qc.verdict.drawerRightDesc")} />,
      },
    },

    "analyze.plate": {
      left: {
        title: t("mame.qc.plate.drawerLeft"),
        children: (
          <div className="space-y-0.5">
            <StatLine label="Selected" value={selectedCount} />
            <StatLine label="Total wells" value={wells.length} />
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
              label="Wells"
              value={verdicts.length > 0 ? verdicts.length : "—"}
            />
            <StatLine label="Loaded" value={verdicts.length > 0 ? "Yes" : "No"} />
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
            <StatLine label="PASS rows" value={passCount} />
            <StatLine label="EVOLVEpro xlsx" value={passCount > 0 ? "Ready" : "—"} />
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
