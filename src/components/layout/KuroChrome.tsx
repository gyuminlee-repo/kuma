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
import type { SubStepId } from "@/store/slices/navigationSlice";
import {
  SourceInspector,
  VariantInspector,
  ParameterInspector,
  CurrentMutationInspector,
  PrimerInspector,
  ExportInspector,
} from "@/components/inspectors/kuro";

// ---------------------------------------------------------------------------
// (KvRow, Callout, MetricCards primitives moved to inspectors/kuro/shared/)
// ---------------------------------------------------------------------------

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
    <div className="flex min-w-0 items-center gap-2 py-0.5 text-[11px]">
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
 *
 * Delegates to per-screen inspector components in inspectors/kuro/.
 * VariantInspector and PrimerInspector accept an optional `selected` prop;
 * until row-selection state is added to the store they render empty states.
 */
export function KuroInspector() {
  const currentSubStep = useAppStore((s) => s.currentSubStep);
  const { designResults, plateMappings } = useAppStore(
    useShallow((s) => ({
      designResults: s.designResults,
      plateMappings: s.plateMappings,
    })),
  );

  switch (currentSubStep) {
    case "design.load":
      return <SourceInspector />;
    case "design.mutation":
      return <VariantInspector />;
    case "design.params":
      return <ParameterInspector />;
    case "design.submit":
      return <CurrentMutationInspector />;
    case "output.summary":
      return (
        <PrimerInspector
          selected={designResults[0] ?? null}
          plateMappings={plateMappings}
        />
      );
    case "export.all":
      return <ExportInspector />;
    default:
      return null;
  }
}
