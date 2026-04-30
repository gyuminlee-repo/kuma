import type { FailedMutation } from "../../types/models";

export function FailedMutationList({
  failedMutations,
  onSelect,
  disabled = false,
  disabledHint,
}: {
  failedMutations: FailedMutation[];
  onSelect: (failed: FailedMutation) => void;
  /** When true, items render as non-interactive (no click, no keyboard). */
  disabled?: boolean;
  /** Tooltip suffix shown when disabled to explain why retry is unavailable. */
  disabledHint?: string;
}) {
  return (
    <div className="text-caption text-destructive font-mono flex flex-wrap gap-1">
      {failedMutations.map((f) => {
        const baseTitle = `#${f.rank} | ${f.reason}`;
        const title = disabled && disabledHint ? `${baseTitle}\n${disabledHint}` : baseTitle;
        if (disabled) {
          return (
            <span
              key={f.mutation}
              className="bg-destructive/10 px-1.5 py-0.5 rounded opacity-60 cursor-not-allowed"
              title={title}
              aria-disabled="true"
            >
              #{f.rank} {f.mutation}
            </span>
          );
        }
        return (
          <span
            key={f.mutation}
            className="bg-destructive/10 px-1.5 py-0.5 rounded cursor-pointer hover:bg-destructive/20"
            title={title}
            onClick={() => onSelect(f)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && onSelect(f)}
          >
            #{f.rank} {f.mutation}
          </span>
        );
      })}
    </div>
  );
}
