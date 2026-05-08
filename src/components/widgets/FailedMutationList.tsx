/**
 * §18 Warning vs Error Standardisation — uses StatusBadge error colour tokens
 * so failed mutation chips are visually consistent with the rest of the app.
 *
 * §8 A11y: when colorblind assist is enabled, shape prefix (✗) is shown
 * so the error state is not conveyed by colour alone.
 */

import type { FailedMutation } from "../../types/models";
import { StatusBadge } from "../ui/StatusBadge";
import { useColorblindMode } from "../../hooks/useColorblindMode";

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
  const colorblindMode = useColorblindMode();

  return (
    <div className="font-mono flex flex-wrap gap-1">
      {failedMutations.map((f) => {
        const baseTitle = `#${f.rank} | ${f.reason}`;
        const title = disabled && disabledHint ? `${baseTitle}\n${disabledHint}` : baseTitle;
        if (disabled) {
          return (
            <span
              key={f.mutation}
              title={title}
              aria-disabled="true"
              className="opacity-60 cursor-not-allowed"
            >
              <StatusBadge
                status="error"
                label={`#${f.rank} ${f.mutation}`}
                showShape={colorblindMode}
              />
            </span>
          );
        }
        return (
          <span
            key={f.mutation}
            title={title}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(f)}
            onKeyDown={(e) => e.key === "Enter" && onSelect(f)}
            className="cursor-pointer hover:opacity-80"
          >
            <StatusBadge
              status="error"
              label={`#${f.rank} ${f.mutation}`}
              showShape={colorblindMode}
            />
          </span>
        );
      })}
    </div>
  );
}
