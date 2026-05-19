/**
 * DesignSummaryCard — design.submit step 상단 "현재 입력 요약" 카드.
 *
 * [source: spec §0.1 #1 #15 — wizard 내부 변경값이 다음 step 에서 stale 표시되는 문제]
 *
 * 사용자가 이전 substep(MutationInput, ParameterPanel 등)에서 바꾼 핵심 설정을
 * design.submit(=run design) 직전에 한눈에 보이도록 한다.
 *
 * 표시 항목 (4 + sequence):
 *   1. Sequence            seqInfo.header / seq_length          (Not loaded)
 *   2. Mutation source     mutationInputMode                    (single | evolvepro)
 *   3. Selection mode      pipelineMode ? Pipeline (failover) : Top-N only
 *   4. Variant count       evolveproTotalCount (mutationInputMode=single → parsedMutations.length)
 *   5. Polymerase / codon  selectedPolymerase · codonStrategy · tmFwdTarget · maxPrimers
 *
 * Memoization: zustand 개별 selector 호출 (참조 안정). 별도 useMemo 불필요.
 */

import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";

export function DesignSummaryCard() {
  const { t } = useTranslation();

  const seqInfo = useAppStore((s) => s.seqInfo);
  const mutationInputMode = useAppStore((s) => s.mutationInputMode);
  const evolveproMode = useAppStore((s) => s.evolveproMode);
  const evolveproTotalCount = useAppStore((s) => s.evolveproTotalCount);
  const parsedMutationCount = useAppStore((s) => s.parsedMutations.length);
  const selectedPolymerase = useAppStore((s) => s.selectedPolymerase);
  const codonStrategy = useAppStore((s) => s.codonStrategy);
  const tmFwdTarget = useAppStore((s) => s.tmFwdTarget);
  const maxPrimers = useAppStore((s) => s.maxPrimers);

  const sequenceText = seqInfo
    ? `${seqInfo.header || t("phaseE.summary.sequence.unnamed")} (${seqInfo.seq_length} nt)`
    : t("phaseE.summary.sequence.empty");

  const selectionText = evolveproMode !== "topN"
    ? t("phaseE.summary.selectionMode.pipeline")
    : t("phaseE.summary.selectionMode.topN");

  const variantCount =
    mutationInputMode === "text" ? parsedMutationCount : evolveproTotalCount;

  const rows: Array<[string, string]> = [
    [t("phaseE.summary.sequence.label"), sequenceText],
    [t("phaseE.summary.mutation.label"), mutationInputMode],
    [t("phaseE.summary.selectionMode.label"), selectionText],
    [t("phaseE.summary.variants.label"), String(variantCount)],
    [
      t("phaseE.summary.polymerase.label"),
      `${selectedPolymerase || "—"} · ${codonStrategy} · Tm ${tmFwdTarget}°C · max ${maxPrimers}`,
    ],
  ];

  return (
    <div
      data-testid="design-summary-card"
      className="rounded-md border border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-900 px-4 py-3 mb-4"
    >
      <div className="text-xs uppercase tracking-wide text-neutral-500 dark:text-neutral-400 mb-2">
        {t("phaseE.summary.heading")}
      </div>
      <dl className="grid grid-cols-[max-content,1fr] gap-x-3 gap-y-1 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-neutral-500 dark:text-neutral-400">{label}</dt>
            <dd
              className="text-neutral-900 dark:text-neutral-100 font-medium truncate"
              data-testid={`design-summary-${label.toLowerCase().replace(/\s+/g, "-")}`}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
