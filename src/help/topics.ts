import type { KuroSubStepId } from "../components/steps/constants";
import type { MameSubStepId } from "../store/mame/slices/mameSubSteps";

export interface HelpGroup {
  /** i18n key for the group heading. */
  labelKey: string;
  topics: string[];
}

export const HELP_GROUPS: HelpGroup[] = [
  { labelKey: "help.panel.group.start", topics: ["kuro-index", "mame-index"] },
  {
    labelKey: "help.panel.group.kuro",
    topics: [
      "kuro-01-load",
      "kuro-02-mutation",
      "kuro-03-params",
      "kuro-04-submit",
      "kuro-05-output",
      "kuro-06-export",
    ],
  },
  {
    labelKey: "help.panel.group.mame",
    topics: ["mame-01-setup", "mame-02-review", "mame-03-janus", "mame-04-activity"],
  },
  { labelKey: "help.panel.group.deeper", topics: ["mame-pipeline"] },
];

export const ALL_TOPIC_IDS: string[] = HELP_GROUPS.flatMap((g) => g.topics);

/**
 * Step id to topic. The Record type makes tsc reject a missing or an extra key,
 * so the keys are exactly KuroSubStepId (src/components/steps/constants.ts)
 * plus MameSubStepId (src/store/mame/slices/mameSubSteps.ts), including the
 * MAME legacy ids that MameWorkflowRail still renders as aliases.
 */
export const STEP_TO_TOPIC: Record<KuroSubStepId | MameSubStepId, string> = {
  "design.load": "kuro-01-load",
  "design.mutation": "kuro-02-mutation",
  "design.params": "kuro-03-params",
  "design.submit": "kuro-04-submit",
  "output.summary": "kuro-05-output",
  "export.all": "kuro-06-export",
  "setup.files": "mame-01-setup",
  "setup.design": "mame-01-setup",
  "analyze.inputs": "mame-01-setup",
  "analyze.review": "mame-02-review",
  "analyze.verdict": "mame-02-review",
  "analyze.plate": "mame-02-review",
  "janus.settings": "mame-03-janus",
  "activity.ingest": "mame-04-activity",
  "activity.signals": "mame-04-activity",
  "activity.mergeExport": "mame-04-activity",
};

function isMappedStep(step: string): step is KuroSubStepId | MameSubStepId {
  return Object.prototype.hasOwnProperty.call(STEP_TO_TOPIC, step);
}

/** An unmapped step opens an index rather than nothing. */
export function topicForStep(step: string | null | undefined): string {
  if (step && isMappedStep(step)) return STEP_TO_TOPIC[step];
  return step?.startsWith("design.") || step?.startsWith("output.") || step?.startsWith("export.")
    ? "kuro-index"
    : "mame-index";
}
