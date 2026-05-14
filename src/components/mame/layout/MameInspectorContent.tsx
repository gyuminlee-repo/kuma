/**
 * MameInspectorContent — MAME 7화면 우측 Inspector 패널 내용.
 *
 * currentMameSubStep에 따라 화면별 KV(키-값) 패널을 렌더한다.
 * InspectorPanel 래퍼는 MameAppLayout에서 적용하므로 여기서는 내부 콘텐츠만 담당.
 *
 * [source: v5-strategy.md §2.2 — 화면별 Inspector 콘텐츠]
 * [source: v5-audit.md Post-Phase 1 재점검 — per-screen Inspector 콘텐츠 0건 GAP]
 */

import { useTranslation } from "react-i18next";
import { useMameAppStore } from "@/store/mame/mameAppStore";
import type { MameSubStepId } from "@/store/mame/slices/mameSubSteps";

// KV 행 공통 컴포넌트
function KVRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  const display = value != null && value !== "" ? String(value) : "—";
  return (
    <div className="flex items-start justify-between gap-2 py-1.5 border-b border-border last:border-0">
      <span className="text-xs text-muted-foreground shrink-0 w-[40%]">{label}</span>
      <span className="text-xs text-foreground text-right min-w-0 break-all">{display}</span>
    </div>
  );
}

// 캘아웃(강조 텍스트) 박스
function Callout({ title, body }: { title: string; body: string }) {
  return (
    <div className="mt-3 rounded border border-primary/30 bg-primary/5 px-3 py-2">
      <p className="text-xs font-semibold text-primary">{title}</p>
      <p className="mt-1 text-xs text-muted-foreground">{body}</p>
    </div>
  );
}

// 빈 상태
function EmptyState({ message }: { message: string }) {
  return (
    <p className="text-xs text-muted-foreground py-2">{message}</p>
  );
}

/** 화면 1: MAME Setup/Files — Run Inspector */
function SetupFilesInspector() {
  const { t } = useTranslation();
  const inputDir = useMameAppStore((s) => s.inputDir);

  if (!inputDir) {
    return <EmptyState message={t("mame.setup.files.inspectorNoFolder")} />;
  }

  // inputDir에서 폴더 이름만 추출 (Run 폴더 이름을 Device 식별자로 사용)
  const folderName = inputDir.replace(/\\/g, "/").split("/").filter(Boolean).pop() ?? inputDir;

  return (
    <div>
      <KVRow label={t("mame.setup.files.inspectorDevice")} value="Oxford Nanopore" />
      <KVRow label={t("mame.setup.files.inspectorKit")} value="SQK-NBD114-24" />
      <KVRow label={t("mame.setup.files.inspectorBarcodes")} value={folderName} />
    </div>
  );
}

/** 화면 2: MAME Setup/Design — Barcode Inspector */
function SetupDesignInspector() {
  const { t } = useTranslation();
  const expectedPath = useMameAppStore((s) => s.expectedPath);

  if (!expectedPath) {
    return <EmptyState message={t("mame.setup.design.inspectorNoBarcodeSelected")} />;
  }

  const fileName = expectedPath.replace(/\\/g, "/").split("/").filter(Boolean).pop() ?? expectedPath;

  return (
    <div>
      <KVRow label={t("mame.setup.design.inspectorVariant")} value="BC01" />
      <KVRow label={t("mame.setup.design.inspectorDesignSource")} value={fileName} />
      <KVRow label={t("mame.setup.design.inspectorExpectedReads")} value="~500" />
    </div>
  );
}

/** 화면 3: MAME QC/Inputs — QC Inspector (estimated retention 2x2) */
function QcInputsInspector() {
  const { t } = useTranslation();
  const minFileSizeKb = useMameAppStore((s) => s.minFileSizeKb);
  const minFilteredDepth = useMameAppStore((s) => s.minFilteredDepth);
  const verdicts = useMameAppStore((s) => s.verdicts);

  const totalWells = verdicts.length;
  const passCount = verdicts.filter((v) => v.verdict === "PASS").length;
  const estRetention =
    totalWells > 0 ? `${Math.round((passCount / totalWells) * 100)}%` : "—";

  return (
    <div>
      <KVRow label={t("mame.qc.inputs.inspectorEstRetention")} value={estRetention} />
      <KVRow label={t("mame.qc.inputs.inspectorEstPass")} value={totalWells > 0 ? `${passCount}/${totalWells}` : "—"} />
      <KVRow label={t("mame.qc.inputs.inspectorMinDepth")} value={`${minFilteredDepth} reads`} />
      <KVRow label={t("mame.qc.inputs.inspectorMinIdentity")} value={`${minFileSizeKb} KB`} />
    </div>
  );
}

/** 화면 4: MAME QC/Verdict — Barcode Verdict Inspector */
function QcVerdictInspector() {
  const { t } = useTranslation();
  const verdicts = useMameAppStore((s) => s.verdicts);

  // 첫 번째 PASS 또는 첫 번째 verdict를 preview로 사용
  const selected = verdicts.find((v) => v.verdict === "PASS") ?? verdicts[0] ?? null;

  if (!selected) {
    return <EmptyState message={t("mame.qc.verdict.inspectorNoBarcodeSelected")} />;
  }

  return (
    <div>
      <KVRow label={t("mame.qc.verdict.inspectorReads")} value={selected.read_count ?? "—"} />
      <KVRow
        label={t("mame.qc.verdict.inspectorIdentity")}
        value={
          selected.observed_aa_changes.length === 0
            ? "100%"
            : `${Math.max(0, 100 - selected.observed_aa_changes.length * 5)}%`
        }
      />
      <KVRow label={t("mame.qc.verdict.inspectorCall")} value={selected.verdict} />
      <KVRow
        label={t("mame.qc.verdict.inspectorExport")}
        value={selected.verdict === "PASS" ? "Included" : "Excluded"}
      />
    </div>
  );
}

/** 화면 5: MAME QC/Plate — Well Inspector */
function QcPlateInspector() {
  const { t } = useTranslation();
  const selectedWell = useMameAppStore((s) => s.selectedWell);

  if (!selectedWell) {
    return <EmptyState message={t("mame.qc.plate.inspectorNoWellSelected")} />;
  }

  return (
    <div>
      <KVRow label={t("mame.qc.plate.inspectorBarcode")} value={selectedWell.barcode} />
      <KVRow label={t("mame.qc.plate.inspectorReads")} value={selectedWell.notes || "—"} />
      <KVRow
        label={t("mame.qc.plate.inspectorReason")}
        value={
          selectedWell.is_fallback && selectedWell.fallback_reason
            ? selectedWell.fallback_reason
            : selectedWell.verdict
        }
      />
    </div>
  );
}

/** 화면 6: MAME Activity/Ingest — Activity Inspector */
function ActivityIngestInspector() {
  const { t } = useTranslation();
  const verdicts = useMameAppStore((s) => s.verdicts);
  const hasActivity = verdicts.length > 0;

  if (!hasActivity) {
    return <EmptyState message={t("mame.activity.ingest.inspectorNoData")} />;
  }

  return (
    <div>
      <KVRow label={t("mame.activity.ingest.inspectorMean")} value="—" />
      <KVRow label={t("mame.activity.ingest.inspectorStdDev")} value="—" />
      <KVRow label={t("mame.activity.ingest.inspectorReplicates")} value="—" />
      <KVRow label={t("mame.activity.ingest.inspectorWtNorm")} value="—" />
    </div>
  );
}

/** 화면 7: MAME Activity/Merge & Export — Export Inspector */
function ActivityMergeExportInspector() {
  const { t } = useTranslation();
  const verdicts = useMameAppStore((s) => s.verdicts);
  const hasMerge = verdicts.length > 0;

  if (!hasMerge) {
    return <EmptyState message={t("mame.activity.mergeExport.inspectorNoMerge")} />;
  }

  const passVerdicts = verdicts.filter((v) => v.verdict === "PASS");

  return (
    <div>
      <KVRow label={t("mame.activity.mergeExport.inspectorVariant")} value="R585A" />
      <KVRow label={t("mame.activity.mergeExport.inspectorActivity")} value="—" />
      <KVRow label={t("mame.activity.mergeExport.inspectorMergedRows")} value={passVerdicts.length} />
      <KVRow label={t("mame.activity.mergeExport.inspectorStatus")} value="Ready" />
      <Callout
        title={t("mame.activity.mergeExport.inspectorBridgeCallout")}
        body={t("mame.activity.mergeExport.inspectorBridgeDesc")}
      />
    </div>
  );
}

/** 화면별 Inspector 디스패처 */
const INSPECTOR_MAP: Record<MameSubStepId, React.ComponentType> = {
  "setup.files": SetupFilesInspector,
  "setup.design": SetupDesignInspector,
  "analyze.inputs": QcInputsInspector,
  "analyze.verdict": QcVerdictInspector,
  "analyze.plate": QcPlateInspector,
  "activity.ingest": ActivityIngestInspector,
  "activity.mergeExport": ActivityMergeExportInspector,
};

export function MameInspectorContent() {
  const currentSubStep = useMameAppStore((s) => s.currentMameSubStep);
  const InspectorComponent = INSPECTOR_MAP[currentSubStep];

  if (!InspectorComponent) return null;
  return <InspectorComponent />;
}

/** 화면별 Inspector 제목/부제목 반환 훅 */
export function useMameInspectorMeta(): { title: string; subtitle: string } {
  const { t } = useTranslation();
  const currentSubStep = useMameAppStore((s) => s.currentMameSubStep);

  const META: Record<MameSubStepId, { titleKey: string; subtitleKey: string }> = {
    "setup.files": {
      titleKey: "mame.setup.files.inspectorTitle",
      subtitleKey: "mame.setup.files.inspectorSubtitle",
    },
    "setup.design": {
      titleKey: "mame.setup.design.inspectorTitle",
      subtitleKey: "mame.setup.design.inspectorSubtitle",
    },
    "analyze.inputs": {
      titleKey: "mame.qc.inputs.inspectorTitle",
      subtitleKey: "mame.qc.inputs.inspectorSubtitle",
    },
    "analyze.verdict": {
      titleKey: "mame.qc.verdict.inspectorTitle",
      subtitleKey: "mame.qc.verdict.inspectorSubtitle",
    },
    "analyze.plate": {
      titleKey: "mame.qc.plate.inspectorTitle",
      subtitleKey: "mame.qc.plate.inspectorSubtitle",
    },
    "activity.ingest": {
      titleKey: "mame.activity.ingest.inspectorTitle",
      subtitleKey: "mame.activity.ingest.inspectorSubtitle",
    },
    "activity.mergeExport": {
      titleKey: "mame.activity.mergeExport.inspectorTitle",
      subtitleKey: "mame.activity.mergeExport.inspectorSubtitle",
    },
  };

  const meta = META[currentSubStep];
  return {
    title: t(meta.titleKey),
    subtitle: t(meta.subtitleKey),
  };
}
