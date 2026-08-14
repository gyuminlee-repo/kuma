/**
 * RunQcSection, the collapsed QC drawer on the analyze review screen (2.2).
 *
 * The verdict table and the plate map are what an operator came to 2.2 for, so
 * everything here stays behind a disclosure that starts closed. What it holds is
 * measurement the run already produced and nothing on screen was reading:
 *
 *  - the five `RunHealthPanel` sections other than the verdict breakdown, which
 *    2.2 already draws beside the plate. Until now `RUN_HEALTH_QC_SECTIONS` had
 *    no mount anywhere in the app, so file-size, throughput, pore yield, barcode
 *    distribution and cross-talk were computed and dropped.
 *
 * Two rules this file keeps, both inherited from `ContaminationPanel`:
 *
 *  - A missing measurement states its REASON. "No data" and 0 are different
 *    readings and one must never be drawn as the other.
 *  - Nothing here grades. `run_quality.ts` says so of every field it carries
 *    (`enforced: false` throughout), so there are no severity colours and no
 *    threshold badges in this file.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AdvancedSection } from "@/components/ui/AdvancedSection";
import {
  RUN_HEALTH_QC_SECTIONS,
  RunHealthPanel,
} from "@/components/mame/widgets/RunHealthPanel";
import type { RunHealthData } from "@/types/mame/models";

/** A block heading plus either its content or the reason it has none. */
export function QcBlock({
  testId,
  title,
  reason,
  children,
}: {
  testId: string;
  title: string;
  /** Set when the measurement is absent. Rendered instead of `children`. */
  reason?: string;
  children?: React.ReactNode;
}) {
  return (
    <section
      data-testid={testId}
      data-state={reason === undefined ? "present" : "unavailable"}
      className="border-t border-border/60 pt-2 first:border-t-0 first:pt-0"
    >
      <h3 className="text-caption font-semibold uppercase tracking-widest text-muted-foreground">
        {title}
      </h3>
      {reason === undefined ? (
        <div className="mt-1.5">{children}</div>
      ) : (
        <p className="mt-1 text-caption text-muted-foreground">{reason}</p>
      )}
    </section>
  );
}

interface RunQcSectionProps {
  /** Null when the run produced no health block. Reported, not hidden. */
  runHealth: RunHealthData | null;
}

export function RunQcSection({ runHealth }: RunQcSectionProps) {
  const { t } = useTranslation();
  // Collapsed by default: the disclosure exists so that the table and the plate
  // keep the screen. AdvancedSection is controlled and renders children only
  // while open.
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3">
      <AdvancedSection
        title={t("mame.runHealth.qcSectionTitle")}
        ariaLabel={t("mame.runHealth.qcSectionAriaLabel")}
        id="mame-run-qc-panel"
        open={open}
        onToggle={() => setOpen((v) => !v)}
      >
        <div data-testid="run-qc-section" className="flex flex-col gap-3">
          <QcBlock
            testId="run-qc-health"
            title={t("mame.runHealth.qcHealthTitle")}
            reason={runHealth === null ? t("mame.runHealth.qcHealthAbsent") : undefined}
          >
            {runHealth !== null && (
              <RunHealthPanel
                health={runHealth}
                sections={RUN_HEALTH_QC_SECTIONS}
                className="p-0"
              />
            )}
          </QcBlock>
        </div>
      </AdvancedSection>
    </div>
  );
}
