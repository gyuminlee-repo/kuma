/**
 * KuroChrome — KURO 6-screen widget chrome provider.
 *
 * Supplies per-screen WorkflowRail / ContextHeader / DrawerStrip / InspectorPanel
 * content based on the current sub-step. Called by AppLayout to wire inspector
 * and sidebar props on AppShell.
 *
 * [source: v5-strategy.md §6.1 — KURO 6-screen contract matrix]
 * [source: notes/specs/phase4-5-namespacing.md §1.2 — kuro.* i18n prefix]
 * [source: v5-audit.md — inspector slot gap P0]
 *
 * Mockup progress values:
 *   design.load      16%
 *   design.mutation  34%   (nominate in v5 terminology)
 *   design.params    52%
 *   design.submit    72%
 *   output.summary   84%
 *   export.all      100%
 */

import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { useShallow } from "zustand/react/shallow";
import { WorkflowRail, type WorkflowStep } from "@/components/widgets/WorkflowRail";
import { ContextHeader } from "@/components/widgets/ContextHeader";
import { DrawerStrip } from "@/components/widgets/DrawerStrip";
import { InspectorPanel } from "@/components/widgets/InspectorPanel";
import type { SubStepId } from "@/store/slices/navigationSlice";

// ---------------------------------------------------------------------------
// KV Row primitive
// ---------------------------------------------------------------------------

function KvRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-x-2 py-1.5 text-[12px]" style={{ gridTemplateColumns: "92px 1fr" }}>
      <dt className="truncate font-medium text-muted-foreground">{label}</dt>
      <dd className="truncate text-foreground">{value}</dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Callout box primitive
// ---------------------------------------------------------------------------

function Callout({ text }: { text: string }) {
  return (
    <div
      className="mt-3 rounded-md border border-ring/30 bg-accent/20 px-3 py-2 text-[11px] leading-snug text-muted-foreground"
      role="note"
    >
      {text}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metric card 2x2 grid primitive
// ---------------------------------------------------------------------------

function MetricCards({
  cards,
}: {
  cards: { label: string; value: string; variant?: "default" | "warn" | "ok" }[];
}) {
  const variantCls: Record<string, string> = {
    default: "text-foreground",
    warn: "text-warning",
    ok: "text-success",
  };
  return (
    <div className="grid grid-cols-2 gap-2">
      {cards.map(({ label, value, variant = "default" }) => (
        <div
          key={label}
          className="rounded-md border border-border bg-muted/30 px-3 py-2"
        >
          <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </div>
          <div className={`mt-0.5 text-[18px] font-bold tabular-nums ${variantCls[variant]}`}>
            {value}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Log line primitive (terminal-style)
// ---------------------------------------------------------------------------

function LogLine({
  level,
  text,
}: {
  level: "ok" | "warn" | "err" | "dim";
  text: string;
}) {
  const cls =
    level === "ok"
      ? "text-success"
      : level === "warn"
        ? "text-warning"
        : level === "err"
          ? "text-destructive"
          : "text-muted-foreground";
  return (
    <div className={`font-mono text-[10px] leading-snug ${cls}`}>{text}</div>
  );
}

// ---------------------------------------------------------------------------
// Mini-row primitive (drawer left/right slot)
// ---------------------------------------------------------------------------

function MiniRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 py-0.5 text-[11px]">
      <span className="shrink-0 font-medium text-muted-foreground">{label}:</span>
      <span className="truncate text-foreground">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// WorkflowRail steps for KURO
// ---------------------------------------------------------------------------

function buildKuroSteps(t: (key: string) => string, current: SubStepId): WorkflowStep[] {
  const order: SubStepId[] = [
    "design.load",
    "design.mutation",
    "design.params",
    "design.submit",
    "output.summary",
    "export.all",
  ];

  const labels: Record<SubStepId, string> = {
    "design.load": t("phaseC.subSteps.design.load"),
    "design.mutation": t("phaseC.subSteps.design.mutation"),
    "design.params": t("phaseC.subSteps.design.params"),
    "design.submit": "Submit Design",
    "output.summary": t("phaseC.subSteps.output.summary") || "Output",
    "export.all": t("phaseC.subSteps.export.all"),
  };

  const currentIdx = order.indexOf(current);

  return order.map((id, i): WorkflowStep => {
    const state =
      i < currentIdx ? "done" : i === currentIdx ? "active" : "lock";
    return {
      num: i + 1,
      title: labels[id] ?? id,
      state,
    };
  });
}

// ---------------------------------------------------------------------------
// Progress percent per sub-step (mockup §3.2)
// ---------------------------------------------------------------------------

const PROGRESS_MAP: Record<SubStepId, number> = {
  "design.load": 16,
  "design.mutation": 34,
  "design.params": 52,
  "design.submit": 72,
  "output.summary": 84,
  "export.all": 100,
};

// ---------------------------------------------------------------------------
// Public exports
// ---------------------------------------------------------------------------

/**
 * KuroWorkflowRail — sidebar slot for AppLayout.
 * Renders WorkflowRail with current KURO progress + side-card hint.
 */
export function KuroWorkflowRail() {
  const { t } = useTranslation();
  const currentSubStep = useAppStore((s) => s.currentSubStep);
  const setSubStep = useAppStore((s) => s.setSubStep);

  const steps = buildKuroSteps(t, currentSubStep);
  const progressPercent = PROGRESS_MAP[currentSubStep] ?? 0;

  // Side-card body from namespaced i18n keys
  const sideCardBodyKey = `kuro.${currentSubStep.split(".")[1]}.sideCardBody`;

  return (
    <WorkflowRail
      title="KURO Workflow"
      progressPercent={progressPercent}
      steps={steps}
      sideCard={{
        title: "Tip",
        body: t(sideCardBodyKey),
      }}
      onStepClick={(idx) => {
        const order: SubStepId[] = [
          "design.load",
          "design.mutation",
          "design.params",
          "design.submit",
          "output.summary",
          "export.all",
        ];
        const target = order[idx];
        if (target) setSubStep(target);
      }}
    />
  );
}

/**
 * KuroContextHeader — context header for the current sub-step.
 */
export function KuroContextHeader() {
  const { t } = useTranslation();
  const currentSubStep = useAppStore((s) => s.currentSubStep);

  const screenKey = currentSubStep.split(".")[1] as string;
  const title = t(`phaseC.subSteps.${currentSubStep}`) || screenKey;
  const subtitle = t(`phaseE.descriptions.${currentSubStep}`) || "";

  return <ContextHeader title={title} subtitle={subtitle} />;
}

/**
 * KuroDrawerStrip — drawer strip content per sub-step.
 */
export function KuroDrawerStrip() {
  const { t } = useTranslation();
  const currentSubStep = useAppStore((s) => s.currentSubStep);
  const { statusMessage } = useAppStore(
    useShallow((s) => ({ statusMessage: s.statusMessage })),
  );

  const logText = statusMessage ?? "Sidecar ready";

  switch (currentSubStep) {
    case "design.load":
      return (
        <DrawerStrip
          left={{
            title: t("kuro.load.drawerRecent"),
            children: (
              <MiniRow label="Last" value="mame_round3_export.csv" />
            ),
          }}
          center={{
            title: "Sidecar log",
            children: <LogLine level="dim" text={logText} />,
          }}
          right={{
            title: t("kuro.load.drawerAutosave"),
            children: <MiniRow label="Saved" value="just now" />,
          }}
        />
      );
    case "design.mutation":
      return (
        <DrawerStrip
          left={{
            title: t("kuro.nominate.drawerActions"),
            children: (
              <>
                <MiniRow label="Selected" value="0 variants" />
                <MiniRow label="Blocked" value="0" />
              </>
            ),
          }}
          center={{
            title: "Trace log",
            children: <LogLine level="dim" text={logText} />,
          }}
          right={{
            title: t("kuro.nominate.drawerAutosave"),
            children: <MiniRow label="Saved" value="just now" />,
          }}
        />
      );
    case "design.params":
      return (
        <DrawerStrip
          left={{
            title: t("kuro.params.drawerEstimate"),
            children: (
              <>
                <MiniRow label="Primers" value="--" />
                <MiniRow label="Plates" value="--" />
              </>
            ),
          }}
          center={{
            title: "Validation log",
            children: <LogLine level="dim" text={logText} />,
          }}
          right={{
            title: t("kuro.params.drawerShortcut"),
            children: (
              <>
                <MiniRow label="Run" value="Ctrl+D" />
                <MiniRow label="Reset" value="Ctrl+Shift+R" />
              </>
            ),
          }}
        />
      );
    case "design.submit":
      return (
        <DrawerStrip
          left={{
            title: t("kuro.submit.drawerJobQueue"),
            children: <MiniRow label="Queue" value="idle" />,
          }}
          center={{
            title: "Sidecar log",
            children: <LogLine level="dim" text={logText} />,
          }}
          right={{
            title: t("kuro.submit.drawerRecovery"),
            children: <MiniRow label="Autosave" value="ready" />,
          }}
        />
      );
    case "output.summary":
      return (
        <DrawerStrip
          left={{
            title: t("kuro.output.drawerDesignReport"),
            children: <MiniRow label="Status" value="complete" />,
          }}
          center={{
            title: "Finish log",
            children: <LogLine level="ok" text={logText} />,
          }}
          right={{
            title: t("kuro.output.drawerNext"),
            children: <MiniRow label="Next" value="Export" />,
          }}
        />
      );
    case "export.all":
      return (
        <DrawerStrip
          left={{
            title: t("kuro.export.drawerExportQueue"),
            children: <MiniRow label="Queue" value="idle" />,
          }}
          center={{
            title: "Output log",
            children: <LogLine level="dim" text={logText} />,
          }}
          right={{
            title: t("kuro.export.drawerNext"),
            children: <MiniRow label="Done" value="all targets" />,
          }}
        />
      );
    default:
      return null;
  }
}

/**
 * KuroInspector — inspector panel content per sub-step.
 * Returns null for sub-steps without inspector content (none in KURO).
 */
export function KuroInspector() {
  const { t } = useTranslation();
  const currentSubStep = useAppStore((s) => s.currentSubStep);

  // Retrieve store values needed for inspector panels
  const { designResults } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
    })),
  );

  switch (currentSubStep) {
    case "design.load":
      return (
        <InspectorPanel title={t("kuro.load.inspectorTitle")}>
          <dl>
            <KvRow label={t("kuro.load.artifactLabel")} value="mame_round3_export.csv" />
            <KvRow label="Source" value="MAME round 3" />
            <KvRow label="Variants" value="128" />
            <KvRow label="Format" value="EVOLVEpro CSV" />
          </dl>
          <Callout text={t("kuro.load.intentCallout")} />
        </InspectorPanel>
      );

    case "design.mutation":
      return (
        <InspectorPanel title={t("kuro.nominate.inspectorTitle")}>
          <dl>
            <KvRow label={t("kuro.nominate.kvActivity")} value="0.82" />
            <KvRow label={t("kuro.nominate.kvReads")} value="4 120" />
            <KvRow label={t("kuro.nominate.kvDomain")} value="kinase" />
            <KvRow label={t("kuro.nominate.kvMameLink")} value="BC04" />
          </dl>
          <Callout text={t("kuro.nominate.calloutText")} />
        </InspectorPanel>
      );

    case "design.params": {
      const primerCount = designResults.length;
      return (
        <InspectorPanel title={t("kuro.params.inspectorTitle")}>
          <MetricCards
            cards={[
              { label: t("kuro.params.metricPrimers"), value: primerCount > 0 ? String(primerCount) : "--" },
              { label: t("kuro.params.metricPlates"), value: "--" },
              { label: t("kuro.params.metricWarn"), value: "0", variant: "ok" },
              { label: t("kuro.params.metricRuntime"), value: "~2 min" },
            ]}
          />
          <Callout text={t("kuro.params.calloutText")} />
        </InspectorPanel>
      );
    }

    case "design.submit":
      return (
        <InspectorPanel title={t("kuro.submit.inspectorTitle")}>
          <dl>
            <KvRow label={t("kuro.submit.kvMutation")} value="R585A" />
            <KvRow label={t("kuro.submit.kvProgress")} value="--" />
            <KvRow label={t("kuro.submit.kvPartialSave")} value="pending" />
          </dl>
          <Callout text={t("kuro.submit.contractCallout")} />
        </InspectorPanel>
      );

    case "output.summary": {
      const firstResult = designResults[0];
      return (
        <InspectorPanel title={t("kuro.output.inspectorTitle")}>
          <dl>
            <KvRow label={t("kuro.output.kvFwd")} value={firstResult ? "ATCG..." : "--"} />
            <KvRow label={t("kuro.output.kvRev")} value={firstResult ? "CGTA..." : "--"} />
            <KvRow label={t("kuro.output.kvTm")} value={firstResult ? `${firstResult.tm_no_fwd.toFixed(1)} / ${firstResult.tm_no_rev.toFixed(1)} °C` : "--"} />
            <KvRow label={t("kuro.output.kvStatus")} value={firstResult ? (firstResult.warnings.length > 0 ? "warn" : "ok") : "--"} />
          </dl>
        </InspectorPanel>
      );
    }

    case "export.all":
      return (
        <InspectorPanel title={t("kuro.export.inspectorTitle")}>
          <dl>
            <KvRow label={t("kuro.export.kvDestination")} value="IDT + Twist + MAME" />
            <KvRow label={t("kuro.export.kvPrefills")} value="3 targets" />
            <KvRow label={t("kuro.export.kvStaleness")} value="fresh" />
          </dl>
          <Callout text={t("kuro.export.handoffCallout")} />
        </InspectorPanel>
      );

    default:
      return null;
  }
}
