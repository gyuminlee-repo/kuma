import { type ReactNode } from "react";

export type WorkflowStepState = "done" | "active" | "lock" | "default";

export type WorkflowStep = {
  num: string | number;
  title: string;
  hint?: string;
  state: WorkflowStepState;
  /** Short right-aligned label, e.g. "now", "next" */
  mini?: string;
};

export type WorkflowRailProps = {
  title: string;
  /** 0-100 */
  progressPercent: number;
  steps: WorkflowStep[];
  sideCard?: { title: string; body: string };
  onStepClick?: (index: number) => void;
};

type StepNumProps = {
  children: ReactNode;
  state: WorkflowStepState;
};

function StepNum({ children, state }: StepNumProps) {
  const base =
    "flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full text-[11px] font-bold";
  const cls =
    state === "done"
      ? `${base} bg-emerald-600 text-white`
      : state === "active"
        ? `${base} bg-primary text-primary-foreground`
        : `${base} bg-muted text-muted-foreground`;
  return <span className={cls}>{children}</span>;
}

/**
 * WorkflowRail — sidebar workflow step list with progress bar.
 * Matches mockup `.rail-head` + `.steps` + `.side-card` pattern (CSS line 95-113).
 */
export function WorkflowRail({
  title,
  progressPercent,
  steps,
  sideCard,
  onStepClick,
}: WorkflowRailProps) {
  const clampedPct = Math.min(100, Math.max(0, progressPercent));

  return (
    <nav className="flex h-full flex-col overflow-hidden" aria-label={title}>
      {/* rail-head */}
      <div className="shrink-0 border-b border-border px-[13px] py-[14px]">
        <div className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          {title}
        </div>
        <div
          className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-valuenow={clampedPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Workflow progress: ${clampedPct}%`}
        >
          <i
            className="block h-full rounded-full bg-gradient-to-r from-primary to-accent transition-[width] duration-300"
            style={{ width: `${clampedPct}%` }}
            aria-hidden="true"
          />
        </div>
      </div>

      {/* steps */}
      <div className="min-h-0 flex-1 overflow-y-auto p-[9px]">
        <ul role="list" className="space-y-1">
          {steps.map((step, i) => {
            const isClickable =
              step.state === "done" || step.state === "default";
            const baseRow =
              "grid w-full items-start gap-2 rounded-lg px-[9px] py-[9px] text-left";
            const stateRow =
              step.state === "active"
                ? `${baseRow} bg-accent outline outline-1 outline-ring`
                : step.state === "lock"
                  ? `${baseRow} opacity-55 cursor-not-allowed`
                  : isClickable
                    ? `${baseRow} hover:bg-muted/60 cursor-pointer`
                    : baseRow;

            return (
              <li key={i}>
                <button
                  type="button"
                  className={stateRow}
                  style={{ gridTemplateColumns: "26px 1fr auto" }}
                  disabled={!isClickable}
                  aria-current={step.state === "active" ? "step" : undefined}
                  onClick={isClickable ? () => onStepClick?.(i) : undefined}
                >
                  <StepNum state={step.state}>
                    {step.state === "done" ? (
                      <svg
                        width="10"
                        height="10"
                        viewBox="0 0 10 10"
                        fill="none"
                        aria-hidden="true"
                      >
                        <path
                          d="M2 5.5L4 7.5L8 3"
                          stroke="currentColor"
                          strokeWidth="1.6"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    ) : (
                      step.num
                    )}
                  </StepNum>

                  <div className="min-w-0">
                    <span className="block truncate text-[13px] font-medium leading-snug text-foreground">
                      {step.title}
                    </span>
                    {step.hint && (
                      <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                        {step.hint}
                      </span>
                    )}
                  </div>

                  {step.mini && (
                    <span className="shrink-0 self-start text-[10px] font-medium text-muted-foreground">
                      {step.mini}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {/* side-card */}
      {sideCard && (
        <div className="mx-2.5 mb-2.5 mt-auto shrink-0 rounded-lg border border-border bg-muted/50 p-2.5">
          <div className="text-[12px] font-bold text-foreground">
            {sideCard.title}
          </div>
          <p className="mt-0.5 text-[12px] leading-snug text-muted-foreground">
            {sideCard.body}
          </p>
        </div>
      )}
    </nav>
  );
}
